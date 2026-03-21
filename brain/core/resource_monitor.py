"""
brain/core/resource_monitor.py

Монитор ресурсов системы (аналог Гипоталамуса — гомеостаз).

Принципы:
  - Фоновый daemon-поток: сэмплирует CPU/RAM каждые N секунд.
  - Публикует SystemEvent через EventBus при смене политики деградации.
  - Предоставляет thread-safe check() → ResourceState для Scheduler.
  - Поддерживает эмуляцию нагрузки (для тестирования без реального CPU).

Политики деградации:
  NORMAL    (CPU < 70%, RAM < 22 GB) → tick=100ms, все модули активны
  DEGRADED  (CPU 70–85%, RAM 22–28 GB) → tick=500ms, soft_blocked=True
  CRITICAL  (CPU > 85%, RAM 28–30 GB) → tick=2000ms, ring2_allowed=False
  EMERGENCY (RAM > 30 GB)             → tick=5000ms, все тяжёлые пути отключены
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from .contracts import ResourceState
from .event_bus import EventBus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Политика деградации
# ---------------------------------------------------------------------------

class DegradationPolicy(str, Enum):
    """
    Текущая политика деградации системы.
    Определяет tick interval и доступность тяжёлых модулей.
    """
    NORMAL    = "normal"     # CPU < 70%, RAM < 22 GB
    DEGRADED  = "degraded"   # CPU 70–85%, RAM 22–28 GB
    CRITICAL  = "critical"   # CPU > 85%, RAM 28–30 GB
    EMERGENCY = "emergency"  # RAM > 30 GB


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

@dataclass
class ResourceMonitorConfig:
    """Параметры монитора ресурсов."""
    sample_interval_s: float = 5.0      # интервал сэмплирования (секунды)
    cpu_degraded_pct: float  = 70.0     # порог DEGRADED по CPU
    cpu_critical_pct: float  = 85.0     # порог CRITICAL по CPU
    ram_degraded_gb: float   = 22.0     # порог DEGRADED по RAM (GB)
    ram_critical_gb: float   = 28.0     # порог CRITICAL по RAM (GB)
    ram_emergency_gb: float  = 30.0     # порог EMERGENCY по RAM (GB)
    # Гистерезис: снятие флагов при снижении нагрузки
    cpu_soft_block_off_pct: float  = 60.0   # soft_blocked снимается при CPU <= 60%
    cpu_ring2_off_pct: float       = 75.0   # ring2_allowed восстанавливается при CPU <= 75%
    # Количество ядер для ОС (резерв)
    os_reserved_threads: int = 4


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------

@dataclass
class ResourceMonitorStats:
    """Накопленная статистика монитора."""
    samples_taken: int       = 0
    policy_changes: int      = 0
    degraded_events: int     = 0
    critical_events: int     = 0
    emergency_events: int    = 0


# ---------------------------------------------------------------------------
# Монитор ресурсов
# ---------------------------------------------------------------------------

class ResourceMonitor:
    """
    Фоновый монитор CPU/RAM с graceful degradation.

    Использование:
        bus = EventBus()
        monitor = ResourceMonitor(bus)
        monitor.start()

        # В основном цикле:
        state = monitor.check()
        interval = scheduler.get_tick_interval(state)

        monitor.stop()

    Тестирование (без реального psutil):
        monitor.inject_state(ResourceState(cpu_pct=90.0))  # эмуляция high load
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: Optional[ResourceMonitorConfig] = None,
    ) -> None:
        self._bus    = event_bus
        self._config = config or ResourceMonitorConfig()
        self._stats  = ResourceMonitorStats()
        self._lock   = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Текущее состояние (обновляется фоновым потоком)
        self._state  = self._make_initial_state()
        self._policy = DegradationPolicy.NORMAL

        # Флаги гистерезиса (для плавного снятия ограничений)
        self._soft_blocked_active  = False
        self._ring2_blocked_active = False

        # Инъекция состояния для тестов (None = использовать psutil)
        self._injected_state: Optional[ResourceState] = None

        logger.info(
            "[ResourceMonitor] Инициализирован. psutil=%s interval=%.1fs",
            _PSUTIL_AVAILABLE,
            self._config.sample_interval_s,
        )

    # ------------------------------------------------------------------
    # Запуск / остановка
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Запустить фоновый daemon-поток сэмплирования."""
        if self._running:
            logger.warning("[ResourceMonitor] Уже запущен.")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._sample_loop,
            name="ResourceMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("[ResourceMonitor] Фоновый поток запущен.")

    def stop(self) -> None:
        """Остановить фоновый поток (ждёт завершения текущего сэмпла)."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._config.sample_interval_s + 1.0)
        logger.info("[ResourceMonitor] Остановлен.")

    # ------------------------------------------------------------------
    # Основной API
    # ------------------------------------------------------------------

    def check(self) -> ResourceState:
        """
        Вернуть текущий снимок ресурсного состояния (thread-safe).
        Если монитор не запущен — выполняет немедленный сэмпл.
        """
        if not self._running:
            self._do_sample()
        with self._lock:
            return ResourceState(
                cpu_pct=self._state.cpu_pct,
                ram_pct=self._state.ram_pct,
                ram_used_mb=self._state.ram_used_mb,
                ram_total_mb=self._state.ram_total_mb,
                available_threads=self._state.available_threads,
                ring2_allowed=self._state.ring2_allowed,
                soft_blocked=self._state.soft_blocked,
            )

    def get_policy(self) -> DegradationPolicy:
        """Вернуть текущую политику деградации."""
        with self._lock:
            return self._policy

    # ------------------------------------------------------------------
    # Инъекция состояния (для тестов)
    # ------------------------------------------------------------------

    def inject_state(self, state: ResourceState) -> None:
        """
        Принудительно установить ResourceState (для тестирования).
        Вызывает пересчёт политики деградации.
        """
        self._injected_state = state
        self._apply_state(state)
        logger.debug(
            "[ResourceMonitor] inject_state: cpu=%.1f%% ram=%.1f%% policy=%s",
            state.cpu_pct,
            state.ram_pct,
            self._policy.value,
        )

    def clear_injection(self) -> None:
        """Снять инъекцию — вернуться к реальным данным psutil."""
        self._injected_state = None

    # ------------------------------------------------------------------
    # Фоновый цикл
    # ------------------------------------------------------------------

    def _sample_loop(self) -> None:
        """Фоновый поток: сэмплирует ресурсы каждые sample_interval_s секунд."""
        logger.debug("[ResourceMonitor] Цикл сэмплирования запущен.")
        while self._running:
            try:
                self._do_sample()
            except Exception:
                logger.exception("[ResourceMonitor] Ошибка сэмплирования.")
            # Спим с возможностью прерывания
            deadline = time.monotonic() + self._config.sample_interval_s
            while self._running and time.monotonic() < deadline:
                time.sleep(0.1)
        logger.debug("[ResourceMonitor] Цикл сэмплирования завершён.")

    def _do_sample(self) -> None:
        """Выполнить один сэмпл ресурсов и обновить состояние."""
        if self._injected_state is not None:
            self._apply_state(self._injected_state)
            return

        state = self._read_psutil()
        self._apply_state(state)
        self._stats.samples_taken += 1

    def _read_psutil(self) -> ResourceState:
        """Прочитать реальные данные CPU/RAM через psutil."""
        if not _PSUTIL_AVAILABLE:
            # Fallback: нулевые значения (безопасный режим)
            return ResourceState(
                cpu_pct=0.0,
                ram_pct=0.0,
                ram_used_mb=0.0,
                ram_total_mb=0.0,
                available_threads=4,
                ring2_allowed=True,
                soft_blocked=False,
            )

        cpu = psutil.cpu_percent(interval=0.5)
        vm  = psutil.virtual_memory()
        total_threads = psutil.cpu_count(logical=True) or 1
        available_threads = max(1, total_threads - self._config.os_reserved_threads)

        return ResourceState(
            cpu_pct=float(cpu),
            ram_pct=float(vm.percent),
            ram_used_mb=float(vm.used / 1024 / 1024),
            ram_total_mb=float(vm.total / 1024 / 1024),
            available_threads=available_threads,
            ring2_allowed=True,   # будет пересчитано в _apply_state
            soft_blocked=False,   # будет пересчитано в _apply_state
        )

    def _apply_state(self, raw: ResourceState) -> None:
        """
        Применить новое состояние: пересчитать политику и флаги деградации.
        Публикует SystemEvent при смене политики.
        """
        cfg = self._config
        cpu = raw.cpu_pct
        ram_gb = raw.ram_used_mb / 1024.0

        # ── Флаг soft_blocked (гистерезис) ──────────────────────────────
        if cpu >= cfg.cpu_degraded_pct:
            self._soft_blocked_active = True
        elif cpu <= cfg.cpu_soft_block_off_pct:
            self._soft_blocked_active = False

        # ── Флаг ring2_allowed (гистерезис) ─────────────────────────────
        if cpu >= cfg.cpu_critical_pct:
            self._ring2_blocked_active = True
        elif cpu <= cfg.cpu_ring2_off_pct:
            self._ring2_blocked_active = False

        # ── Политика деградации ──────────────────────────────────────────
        if ram_gb >= cfg.ram_emergency_gb:
            new_policy = DegradationPolicy.EMERGENCY
        elif cpu >= cfg.cpu_critical_pct or ram_gb >= cfg.ram_critical_gb:
            new_policy = DegradationPolicy.CRITICAL
        elif cpu >= cfg.cpu_degraded_pct or ram_gb >= cfg.ram_degraded_gb:
            new_policy = DegradationPolicy.DEGRADED
        else:
            new_policy = DegradationPolicy.NORMAL

        # ── Обновить состояние (thread-safe) ────────────────────────────
        new_state = ResourceState(
            cpu_pct=raw.cpu_pct,
            ram_pct=raw.ram_pct,
            ram_used_mb=raw.ram_used_mb,
            ram_total_mb=raw.ram_total_mb,
            available_threads=raw.available_threads,
            ring2_allowed=not self._ring2_blocked_active,
            soft_blocked=self._soft_blocked_active,
        )

        old_policy = self._policy
        with self._lock:
            self._state  = new_state
            self._policy = new_policy

        # ── Публикуем событие при смене политики ────────────────────────
        if new_policy != old_policy:
            self._stats.policy_changes += 1
            self._on_policy_change(old_policy, new_policy, new_state)

    def _on_policy_change(
        self,
        old: DegradationPolicy,
        new: DegradationPolicy,
        state: ResourceState,
    ) -> None:
        """Публикует SystemEvent при смене политики деградации."""
        # BrainLogger использует "WARN" (не "WARNING")
        brain_level_map = {
            DegradationPolicy.NORMAL:    "INFO",
            DegradationPolicy.DEGRADED:  "WARN",
            DegradationPolicy.CRITICAL:  "ERROR",
            DegradationPolicy.EMERGENCY: "CRITICAL",
        }
        # Python stdlib logging использует "WARNING"
        python_level_map = {
            DegradationPolicy.NORMAL:    "INFO",
            DegradationPolicy.DEGRADED:  "WARNING",
            DegradationPolicy.CRITICAL:  "ERROR",
            DegradationPolicy.EMERGENCY: "CRITICAL",
        }
        brain_level  = brain_level_map.get(new, "WARN")
        python_level = python_level_map.get(new, "WARNING")

        if new == DegradationPolicy.DEGRADED:
            self._stats.degraded_events += 1
        elif new == DegradationPolicy.CRITICAL:
            self._stats.critical_events += 1
        elif new == DegradationPolicy.EMERGENCY:
            self._stats.emergency_events += 1

        logger.log(
            logging.getLevelName(python_level),
            "[ResourceMonitor] Политика: %s → %s (cpu=%.1f%% ram=%.1fMB)",
            old.value, new.value, state.cpu_pct, state.ram_used_mb,
        )

        self._bus.publish(
            "resource_policy_changed",
            {
                "old_policy": old.value,
                "new_policy": new.value,
                "level": brain_level,          # совместимо с BrainLogger ("WARN", не "WARNING")
                "cpu_pct": state.cpu_pct,
                "ram_pct": state.ram_pct,
                "ram_used_mb": state.ram_used_mb,
                "soft_blocked": state.soft_blocked,
                "ring2_allowed": state.ring2_allowed,
            },
            trace_id="resource-monitor",
        )

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _make_initial_state(self) -> ResourceState:
        """Начальное состояние до первого сэмпла."""
        return ResourceState(
            cpu_pct=0.0,
            ram_pct=0.0,
            ram_used_mb=0.0,
            ram_total_mb=0.0,
            available_threads=4,
            ring2_allowed=True,
            soft_blocked=False,
        )

    # ------------------------------------------------------------------
    # Статистика и диагностика
    # ------------------------------------------------------------------

    @property
    def stats(self) -> ResourceMonitorStats:
        """Снимок текущей статистики."""
        s = self._stats
        return ResourceMonitorStats(
            samples_taken=s.samples_taken,
            policy_changes=s.policy_changes,
            degraded_events=s.degraded_events,
            critical_events=s.critical_events,
            emergency_events=s.emergency_events,
        )

    def status(self) -> Dict[str, Any]:
        """Словарь для логирования/observability."""
        state = self.check()
        s = self._stats
        return {
            "running": self._running,
            "psutil_available": _PSUTIL_AVAILABLE,
            "policy": self._policy.value,
            "cpu_pct": state.cpu_pct,
            "ram_pct": state.ram_pct,
            "ram_used_mb": state.ram_used_mb,
            "ram_total_mb": state.ram_total_mb,
            "available_threads": state.available_threads,
            "soft_blocked": state.soft_blocked,
            "ring2_allowed": state.ring2_allowed,
            "samples_taken": s.samples_taken,
            "policy_changes": s.policy_changes,
        }

    def __repr__(self) -> str:
        state = self.check()
        return (
            f"ResourceMonitor(policy={self._policy.value}, "
            f"cpu={state.cpu_pct:.1f}%, "
            f"ram={state.ram_used_mb:.0f}MB, "
            f"soft_blocked={state.soft_blocked}, "
            f"ring2={state.ring2_allowed})"
        )

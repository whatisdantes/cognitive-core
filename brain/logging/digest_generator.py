"""
brain/logging/digest_generator.py

DigestGenerator — генератор человекочитаемых дайджестов по циклам мышления.

Дайджест — краткая сводка одного когнитивного цикла:
  - что было на входе
  - какая память использована
  - как рассуждала система
  - какое решение принято
  - метрики (время, CPU, RAM, confidence)

Файлы дайджестов:
  brain/data/logs/digests/YYYY-MM-DD.txt   — дайджест за день
  brain/data/logs/digests/session_<id>.txt — дайджест по сессии
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# CycleInfo — входные данные для генерации дайджеста
# ---------------------------------------------------------------------------

@dataclass
class CycleInfo:
    """
    Информация об одном когнитивном цикле для генерации дайджеста.

    Все поля опциональны — дайджест генерируется из того, что есть.
    """
    cycle_id: str = ""
    session_id: str = ""
    trace_id: str = ""
    timestamp: str = ""                    # ISO timestamp начала цикла

    # Вход
    goal: str = ""                         # "answer_question('Что такое нейрон?')"
    input_text: str = ""                   # текст входного запроса
    input_modality: str = "text"           # text / image / audio / fused
    input_source: str = ""                 # "user_input" / "file:doc.pdf"
    input_quality: float = 1.0            # 0.0–1.0

    # Память
    memory_used: List[str] = field(default_factory=list)
    # ["semantic:нейрон (conf=0.87)", "episodic:ep_001"]
    sources_used: List[str] = field(default_factory=list)
    # ["user_input (trust=0.80)", "wikipedia.org (trust=0.65)"]

    # Рассуждение
    reasoning_chain: List[str] = field(default_factory=list)
    # ["нейрон", "→", "клетка", "→", "нервная система"]
    reasoning_type: str = ""               # "associative" / "causal" / "deductive"
    contradiction: str = ""               # "" если нет, иначе описание
    hypotheses_count: int = 0             # сколько гипотез проверялось

    # Решение
    confidence: float = 0.0               # 0.0–1.0
    action: str = ""                      # "respond" / "respond_hedged" / "ask_clarification"
    response_preview: str = ""            # первые 120 символов ответа

    # Метрики
    duration_ms: float = 0.0
    cpu_pct: float = 0.0
    ram_gb: float = 0.0

    # Обучение
    learning_updates: List[str] = field(default_factory=list)
    # ["association(нейрон↔клетка) += 0.01"]

    # Дополнительно
    notes: str = ""


# ---------------------------------------------------------------------------
# DigestGenerator
# ---------------------------------------------------------------------------

class DigestGenerator:
    """
    Генератор человекочитаемых дайджестов по когнитивным циклам.

    Параметры:
        digest_dir — директория для файлов дайджестов
    """

    def __init__(self, digest_dir: str = "brain/data/logs/digests") -> None:
        self._dir = Path(digest_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def generate_cycle_digest(self, info: CycleInfo) -> str:
        """
        Сгенерировать дайджест одного цикла.

        Возвращает строку дайджеста и записывает её в файл дня.
        """
        text = self._format_cycle(info)
        self._append_to_day_file(info, text)
        return text

    def generate_session_digest(
        self,
        session_id: str,
        cycles: List[CycleInfo],
    ) -> str:
        """
        Сгенерировать сводный дайджест по всей сессии.

        Параметры:
            session_id — ID сессии
            cycles     — список CycleInfo всех циклов сессии
        """
        text = self._format_session(session_id, cycles)
        self._write_session_file(session_id, text)
        return text

    def format_cycle(self, info: CycleInfo) -> str:
        """Только форматирование, без записи в файл."""
        return self._format_cycle(info)

    # ------------------------------------------------------------------
    # Форматирование
    # ------------------------------------------------------------------

    def _format_cycle(self, info: CycleInfo) -> str:
        """Форматировать один цикл в читаемый текст."""
        ts = info.timestamp or _now_str()
        lines: List[str] = []

        # Заголовок
        cycle_label = info.cycle_id or "cycle_?"
        lines.append(f"Cycle {cycle_label}  [{ts}]")

        if info.session_id:
            lines.append(f"  Session:      {info.session_id}")
        if info.trace_id:
            lines.append(f"  Trace:        {info.trace_id}")

        # Цель
        if info.goal:
            lines.append(f"  Goal:         {info.goal}")

        # Вход
        if info.input_text or info.input_source:
            src = info.input_source or "unknown"
            q = f", quality={info.input_quality:.2f}" if info.input_quality < 1.0 else ""
            preview = _truncate(info.input_text, 80)
            if preview:
                lines.append(f"  Input:        {info.input_modality} ({src}{q}) — \"{preview}\"")
            else:
                lines.append(f"  Input:        {info.input_modality} ({src}{q})")

        # Память
        if info.memory_used:
            lines.append(f"  Memory used:  {', '.join(info.memory_used)}")
        else:
            lines.append(f"  Memory used:  —")

        # Источники
        if info.sources_used:
            lines.append(f"  Sources:      {', '.join(info.sources_used)}")

        # Рассуждение
        if info.reasoning_chain:
            chain_str = " ".join(info.reasoning_chain)
            rtype = f" [{info.reasoning_type}]" if info.reasoning_type else ""
            lines.append(f"  Reasoning:{rtype}  {chain_str}")
        if info.hypotheses_count > 0:
            lines.append(f"  Hypotheses:   {info.hypotheses_count} проверено")

        # Противоречие
        if info.contradiction:
            lines.append(f"  Contradiction: {info.contradiction}")
        else:
            lines.append(f"  Contradiction: none")

        # Уверенность и действие
        conf_label = _confidence_label(info.confidence)
        lines.append(f"  Confidence:   {info.confidence:.2f} ({conf_label})")
        if info.action:
            lines.append(f"  Action:       {info.action}")

        # Ответ
        if info.response_preview:
            preview = _truncate(info.response_preview, 120)
            lines.append(f"  Response:     \"{preview}\"")

        # Метрики
        metrics_parts = []
        if info.duration_ms > 0:
            metrics_parts.append(f"{info.duration_ms:.0f}ms")
        if info.cpu_pct > 0:
            metrics_parts.append(f"CPU: {info.cpu_pct:.0f}%")
        if info.ram_gb > 0:
            metrics_parts.append(f"RAM: {info.ram_gb:.1f} GB")
        if metrics_parts:
            lines.append(f"  Duration:     {' | '.join(metrics_parts)}")

        # Обучение
        if info.learning_updates:
            lines.append(f"  Learning:     {', '.join(info.learning_updates)}")

        # Заметки
        if info.notes:
            lines.append(f"  Notes:        {info.notes}")

        lines.append("")  # пустая строка-разделитель
        return "\n".join(lines)

    def _format_session(self, session_id: str, cycles: List[CycleInfo]) -> str:
        """Форматировать сводку по сессии."""
        lines: List[str] = []
        ts = _now_str()

        lines.append("=" * 60)
        lines.append(f"SESSION DIGEST: {session_id}")
        lines.append(f"Generated:      {ts}")
        lines.append(f"Total cycles:   {len(cycles)}")
        lines.append("=" * 60)
        lines.append("")

        if not cycles:
            lines.append("  (нет циклов)")
            return "\n".join(lines)

        # Агрегированные метрики
        confidences = [c.confidence for c in cycles if c.confidence > 0]
        durations = [c.duration_ms for c in cycles if c.duration_ms > 0]
        contradictions = [c for c in cycles if c.contradiction]
        actions: Dict[str, int] = {}
        for c in cycles:
            if c.action:
                actions[c.action] = actions.get(c.action, 0) + 1

        if confidences:
            avg_conf = sum(confidences) / len(confidences)
            lines.append(f"  Avg confidence:    {avg_conf:.2f}")
        if durations:
            avg_dur = sum(durations) / len(durations)
            lines.append(f"  Avg cycle time:    {avg_dur:.0f}ms")
        if contradictions:
            lines.append(f"  Contradictions:    {len(contradictions)}")
        if actions:
            action_str = ", ".join(f"{k}×{v}" for k, v in sorted(actions.items()))
            lines.append(f"  Actions:           {action_str}")

        lines.append("")
        lines.append("─" * 60)
        lines.append("CYCLES:")
        lines.append("─" * 60)
        lines.append("")

        for info in cycles:
            lines.append(self._format_cycle(info))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Запись в файлы
    # ------------------------------------------------------------------

    def _append_to_day_file(self, info: CycleInfo, text: str) -> None:
        """Дописать дайджест цикла в файл текущего дня."""
        date_str = _today_str()
        path = self._dir / f"{date_str}.txt"
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)

    def _write_session_file(self, session_id: str, text: str) -> None:
        """Записать (перезаписать) дайджест сессии."""
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        path = self._dir / f"session_{safe_id}.txt"
        with self._lock:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    def __repr__(self) -> str:
        return f"DigestGenerator(digest_dir={self._dir!r})"


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _now_str() -> str:
    """Текущее время в читаемом формате."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _today_str() -> str:
    """Текущая дата YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _truncate(text: str, max_len: int) -> str:
    """Обрезать строку до max_len символов с '...'."""
    if not text:
        return ""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _confidence_label(conf: float) -> str:
    """Текстовая метка уверенности."""
    if conf >= 0.85:
        return "high"
    if conf >= 0.60:
        return "medium"
    if conf >= 0.35:
        return "low"
    return "very low"

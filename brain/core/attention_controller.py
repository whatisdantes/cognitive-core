"""
brain/core/attention_controller.py

Контроллер внимания — распределение вычислительного бюджета по модальностям.

Этап H: Attention & Resource Control.

AttentionController выбирает AttentionBudget на основе:
  1. Состояния ресурсов (CPU/RAM → политика деградации)
  2. Типа цели (answer_question / explore_topic / verify_claim / learn_fact)
  3. Оценки значимости (SalienceScore → boost к cognition)

Пресеты бюджетов:
  text_focused      — стандартный текстовый запрос (CPU < 70%, RAM < 22 GB)
  multimodal        — мультимодальный ввод (vision + audio)
  memory_intensive  — глубокий поиск в памяти (explore_topic / verify_claim)
  degraded          — CPU 70–85% или RAM 22–28 GB
  critical          — CPU > 85% или RAM 28–30 GB
  emergency         — RAM > 30 GB (аварийный режим, выгрузить модели)

Использование:
    controller = AttentionController()
    budget = controller.compute_budget(
        goal_type="explore_topic",
        resource_state=state,
        salience=salience_score,
        cycle_id="cycle_42",
    )
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from brain.core.contracts import ContractMixin, ResourceState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AttentionBudget — бюджет вычислений по модальностям
# ---------------------------------------------------------------------------


@dataclass
class AttentionBudget(ContractMixin):
    """
    Бюджет вычислительных ресурсов по модальностям и подсистемам.

    Все значения — доли [0.0, 1.0]. Сумма не обязана равняться 1.0
    (каждая подсистема получает свою долю независимо).

    Атрибуты:
        text      — доля для текстовой обработки
        vision    — доля для визуальной обработки
        audio     — доля для аудио-обработки
        memory    — доля для операций с памятью
        cognition — доля для reasoning loop
        learning  — доля для обучения/сохранения
        logging   — доля для логирования/трассировки
        policy    — название политики (ключ пресета)
        reason    — текстовое объяснение выбора бюджета
        cycle_id  — идентификатор цикла для трассировки
        created_at — время создания (ISO 8601 UTC)
    """

    text: float = 0.50
    vision: float = 0.05
    audio: float = 0.00
    memory: float = 0.25
    cognition: float = 0.12
    learning: float = 0.05
    logging: float = 0.03
    policy: str = "normal"
    reason: str = ""
    cycle_id: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# Пресеты бюджетов
# ---------------------------------------------------------------------------

PRESET_BUDGETS: Dict[str, AttentionBudget] = {
    "text_focused": AttentionBudget(
        text=0.50,
        vision=0.05,
        audio=0.00,
        memory=0.25,
        cognition=0.12,
        learning=0.05,
        logging=0.03,
        policy="normal",
        reason="стандартный текстовый запрос",
    ),
    "multimodal": AttentionBudget(
        text=0.25,
        vision=0.25,
        audio=0.15,
        memory=0.15,
        cognition=0.12,
        learning=0.05,
        logging=0.03,
        policy="normal",
        reason="мультимодальный ввод (vision + audio)",
    ),
    "memory_intensive": AttentionBudget(
        text=0.20,
        vision=0.05,
        audio=0.00,
        memory=0.50,
        cognition=0.15,
        learning=0.07,
        logging=0.03,
        policy="normal",
        reason="глубокий поиск в памяти (explore_topic / verify_claim)",
    ),
    "degraded": AttentionBudget(
        text=0.65,
        vision=0.00,
        audio=0.00,
        memory=0.20,
        cognition=0.10,
        learning=0.00,
        logging=0.05,
        policy="degraded",
        reason="CPU > 70% или RAM > 22 GB — снижена нагрузка",
    ),
    "critical": AttentionBudget(
        text=0.75,
        vision=0.00,
        audio=0.00,
        memory=0.15,
        cognition=0.07,
        learning=0.00,
        logging=0.03,
        policy="critical",
        reason="CPU > 85% или RAM > 28 GB — минимальный режим",
    ),
    "emergency": AttentionBudget(
        text=0.80,
        vision=0.00,
        audio=0.00,
        memory=0.10,
        cognition=0.07,
        learning=0.00,
        logging=0.03,
        policy="emergency",
        reason="RAM > 30 GB — аварийный режим, выгрузить модели",
    ),
}


# ---------------------------------------------------------------------------
# AttentionController — контроллер внимания
# ---------------------------------------------------------------------------


class AttentionController:
    """
    Контроллер внимания — выбирает AttentionBudget для текущего цикла.

    Логика выбора:
      1. Определить политику деградации по ResourceState (CPU/RAM)
      2. Если NORMAL — скорректировать по типу цели
      3. Применить boost от SalienceScore (если overall > 0.5)

    Пороги синхронизированы с ResourceMonitorConfig:
      CPU_DEGRADED_PCT = 70.0
      CPU_CRITICAL_PCT = 85.0
      RAM_DEGRADED_GB  = 22.0
      RAM_CRITICAL_GB  = 28.0
      RAM_EMERGENCY_GB = 30.0

    Использование:
        controller = AttentionController()
        budget = controller.compute_budget(
            goal_type="explore_topic",
            resource_state=state,
            salience=score,
            cycle_id="cycle_42",
        )
    """

    # Пороги ресурсов (синхронизированы с ResourceMonitorConfig)
    CPU_DEGRADED_PCT: float = 70.0
    CPU_CRITICAL_PCT: float = 85.0
    RAM_DEGRADED_GB: float = 22.0
    RAM_CRITICAL_GB: float = 28.0
    RAM_EMERGENCY_GB: float = 30.0

    # Типы целей, требующие memory_intensive бюджета
    MEMORY_INTENSIVE_GOALS: frozenset = frozenset({"explore_topic", "verify_claim"})

    def compute_budget(
        self,
        goal_type: str,
        resource_state: Optional[ResourceState] = None,
        salience: Optional[Any] = None,
        cycle_id: str = "",
    ) -> AttentionBudget:
        """
        Вычислить AttentionBudget для текущего цикла.

        Args:
            goal_type:      тип цели ("answer_question" | "explore_topic" | ...)
            resource_state: текущее состояние ресурсов (CPU/RAM)
            salience:       оценка значимости стимула (SalienceScore)
            cycle_id:       идентификатор цикла для трассировки

        Returns:
            AttentionBudget — копия пресета с применёнными корректировками.
        """
        # 1. Выбрать базовый пресет по ресурсам
        preset_key = self._select_preset(resource_state)

        # 2. Если ресурсы в норме — скорректировать по типу цели
        if preset_key == "text_focused" and goal_type in self.MEMORY_INTENSIVE_GOALS:
            preset_key = "memory_intensive"

        # 3. Создать копию пресета (не мутировать оригинал)
        budget = copy.copy(PRESET_BUDGETS[preset_key])
        budget.cycle_id = cycle_id
        budget.created_at = datetime.now(timezone.utc).isoformat()

        # 4. Применить boost от SalienceScore
        if salience is not None:
            budget = self._apply_salience_boost(budget, salience)

        logger.debug(
            "[AttentionController] goal=%s preset=%s cognition=%.2f policy=%s",
            goal_type,
            preset_key,
            budget.cognition,
            budget.policy,
        )

        return budget

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _select_preset(self, resource_state: Optional[ResourceState]) -> str:
        """
        Выбрать ключ пресета по состоянию ресурсов.

        Пороги синхронизированы с ResourceMonitorConfig.
        """
        if resource_state is None:
            return "text_focused"

        ram_gb = resource_state.ram_used_mb / 1024.0
        cpu = resource_state.cpu_pct

        if ram_gb >= self.RAM_EMERGENCY_GB:
            return "emergency"
        if cpu >= self.CPU_CRITICAL_PCT or ram_gb >= self.RAM_CRITICAL_GB:
            return "critical"
        if cpu >= self.CPU_DEGRADED_PCT or ram_gb >= self.RAM_DEGRADED_GB:
            return "degraded"
        return "text_focused"

    def _apply_salience_boost(
        self,
        budget: AttentionBudget,
        salience: Any,
    ) -> AttentionBudget:
        """
        Применить boost к cognition при высокой значимости стимула.

        Если salience.overall > 0.5:
          boost = min(0.05, (overall - 0.5) × 0.10)
          cognition += boost  (max 0.30)
          learning  -= boost  (min 0.00)
        """
        overall = getattr(salience, "overall", 0.0)
        if overall <= 0.5:
            return budget

        boost = min(0.05, (overall - 0.5) * 0.10)
        new_cognition = min(0.30, budget.cognition + boost)
        new_learning = max(0.00, budget.learning - boost)

        boosted = copy.copy(budget)
        boosted.cognition = round(new_cognition, 4)
        boosted.learning = round(new_learning, 4)
        boosted.reason = f"{budget.reason} [salience_boost={boost:.3f}]"

        return boosted

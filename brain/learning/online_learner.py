"""
brain/learning/online_learner.py

Онлайн-обучение на основе результатов когнитивного цикла (Этап I.1).

OnlineLearner обновляет память после каждого цикла:
  - Подтверждает факты при action == "learn" (confidence += delta)
  - Опровергает факты при action == "contradict" (confidence -= delta)
  - Обновляет ассоциации (Хеббовское обучение: Δweight = lr × confidence)
  - Обновляет доверие к источникам через SourceMemory.update_trust()

Важно: deny_fact() срабатывает ТОЛЬКО при явном противоречии
(action == "contradict"), а не при низком confidence retrieval.
Низкий confidence при поиске ≠ «факт ложный».
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from brain.core.contracts import CognitiveResult, ContractMixin
from brain.memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Результат одного цикла обучения
# ---------------------------------------------------------------------------

@dataclass
class OnlineLearningUpdate(ContractMixin):
    """
    Результат одного цикла онлайн-обучения.

    Поля:
        cycle_id            — ID когнитивного цикла
        facts_confirmed     — список подтверждённых концептов
        facts_denied        — список опровергнутых концептов
        associations_updated — список обновлённых ассоциаций [{a, b, delta}]
        sources_updated     — список обновлённых источников [{source, confirmed}]
        duration_ms         — время выполнения в мс
    """
    cycle_id: str
    facts_confirmed: List[str] = field(default_factory=list)
    facts_denied: List[str] = field(default_factory=list)
    associations_updated: List[Dict[str, Any]] = field(default_factory=list)
    sources_updated: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Онлайн-обучение
# ---------------------------------------------------------------------------

class OnlineLearner:
    """
    Онлайн-обучение на основе результатов когнитивного цикла.

    Принимает CognitiveResult и обновляет память:
      - action == "learn"      → confirm_fact() для всех memory_refs
      - action == "contradict" → deny_fact() для всех memory_refs
      - confidence > 0.7       → усилить ассоциации (Хеббовское обучение)
      - confidence < 0.3       → no-op (низкий confidence ≠ ложный факт)

    Параметры:
        memory          — MemoryManager (фасад всей системы памяти)
        learning_rate   — скорость обучения для Хеббовских ассоциаций (0.01)
        confirm_delta   — прирост confidence при подтверждении (0.05)
        deny_delta      — снижение confidence при опровержении (0.1)
    """

    def __init__(
        self,
        memory: MemoryManager,
        learning_rate: float = 0.01,
        confirm_delta: float = 0.05,
        deny_delta: float = 0.1,
    ) -> None:
        self._memory = memory
        self._learning_rate = learning_rate
        self._confirm_delta = confirm_delta
        self._deny_delta = deny_delta

        # Статистика
        self._update_count: int = 0
        self._total_confirmed: int = 0
        self._total_denied: int = 0
        self._total_associations: int = 0

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def update(self, result: CognitiveResult) -> OnlineLearningUpdate:
        """
        Обновить память на основе результата когнитивного цикла.

        Логика:
          1. confidence < 0.3 → no-op (не учим из слабых результатов)
          2. action == "learn"      → confirm_fact() для memory_refs
          3. action == "contradict" → deny_fact() для memory_refs
          4. confidence > 0.7      → Хеббовское обучение по концептам goal
          5. source_refs           → update_trust() для каждого источника

        Returns:
            OnlineLearningUpdate с деталями всех изменений
        """
        t0 = time.perf_counter()
        cycle_id = result.cycle_id or uuid.uuid4().hex[:8]
        update = OnlineLearningUpdate(cycle_id=cycle_id)

        # --- Пропускаем слабые результаты ---
        if result.confidence < 0.3:
            logger.debug(
                "[OnlineLearner] пропуск: confidence=%.3f < 0.3 (action=%s, cycle=%s)",
                result.confidence, result.action, cycle_id,
            )
            update.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            return update

        # --- Подтверждение фактов (action == "learn") ---
        if result.action == "learn":
            for ref in result.memory_refs:
                concept = ref.ref_id
                self.confirm_fact(concept, source_ref=ref.note)
                update.facts_confirmed.append(concept)

        # --- Опровержение фактов (action == "contradict") ---
        elif result.action == "contradict":
            for ref in result.memory_refs:
                concept = ref.ref_id
                self.deny_fact(concept, source_ref=ref.note)
                update.facts_denied.append(concept)

        # --- Хеббовское обучение (confidence > 0.7) ---
        if result.confidence > 0.7 and result.goal:
            concepts = self._extract_concepts(result.goal)
            if len(concepts) >= 2:
                assoc_updates = self._update_associations(concepts, result.confidence)
                update.associations_updated.extend(assoc_updates)

        # --- Обновление доверия к источникам ---
        confirmed_action = result.action in ("learn", "answer", "respond")
        for ref in result.source_refs:
            if ref.ref_id:
                self._update_source_trust(ref.ref_id, confirmed=confirmed_action)
                update.sources_updated.append({
                    "source": ref.ref_id,
                    "confirmed": confirmed_action,
                })

        # --- Статистика ---
        self._update_count += 1
        self._total_confirmed += len(update.facts_confirmed)
        self._total_denied += len(update.facts_denied)
        self._total_associations += len(update.associations_updated)

        update.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.debug(
            "[OnlineLearner] update: confirmed=%d denied=%d assoc=%d %.1fms",
            len(update.facts_confirmed),
            len(update.facts_denied),
            len(update.associations_updated),
            update.duration_ms,
        )
        return update

    def confirm_fact(self, concept: str, source_ref: str = "") -> None:
        """
        Подтвердить факт — повысить confidence в семантической памяти.

        Args:
            concept:    ключевое слово/понятие
            source_ref: источник подтверждения (опционально)
        """
        if not concept:
            return
        try:
            self._memory.semantic.confirm_fact(concept, delta=self._confirm_delta)
            if source_ref:
                self._update_source_trust(source_ref, confirmed=True)
        except Exception as exc:
            logger.warning("[OnlineLearner] confirm_fact('%s') error: %s", concept, exc)

    def deny_fact(self, concept: str, source_ref: str = "") -> None:
        """
        Опровергнуть факт — снизить confidence в семантической памяти.

        Вызывается ТОЛЬКО при явном противоречии (action == "contradict").
        Низкий confidence при retrieval ≠ ложный факт — не вызывать здесь.

        Args:
            concept:    ключевое слово/понятие
            source_ref: источник опровержения (опционально)
        """
        if not concept:
            return
        try:
            self._memory.semantic.deny_fact(concept, delta=self._deny_delta)
            if source_ref:
                self._update_source_trust(source_ref, confirmed=False)
        except Exception as exc:
            logger.warning("[OnlineLearner] deny_fact('%s') error: %s", concept, exc)

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _update_associations(
        self,
        concepts: List[str],
        confidence: float,
    ) -> List[Dict[str, Any]]:
        """
        Хеббовское обучение: усилить связи между совместно активированными концептами.

        Δweight = learning_rate × confidence

        Args:
            concepts:   список концептов (≥ 2)
            confidence: уверенность результата (0.0–1.0)

        Returns:
            Список обновлённых ассоциаций [{a, b, delta}]
        """
        updates: List[Dict[str, Any]] = []
        delta = round(self._learning_rate * confidence, 4)

        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                a, b = concepts[i], concepts[j]
                try:
                    self._memory.semantic.add_relation(
                        concept_a=a,
                        concept_b=b,
                        weight=delta,
                        rel_type="related",
                        confidence=confidence,
                        bidirectional=True,
                    )
                    updates.append({"a": a, "b": b, "delta": delta})
                except Exception as exc:
                    logger.debug(
                        "[OnlineLearner] add_relation('%s','%s') error: %s", a, b, exc
                    )

        return updates

    def _update_source_trust(self, source_ref: str, confirmed: bool) -> None:
        """
        Обновить доверие к источнику через SourceMemory.update_trust().

        Args:
            source_ref: ID источника
            confirmed:  True = подтверждение, False = опровержение
        """
        if not source_ref:
            return
        try:
            self._memory.source.update_trust(source_ref, confirmed=confirmed)
        except Exception as exc:
            logger.debug(
                "[OnlineLearner] source trust update('%s') error: %s", source_ref, exc
            )

    @staticmethod
    def _extract_concepts(text: str) -> List[str]:
        """
        Извлечь ключевые слова из текста (простая токенизация).

        Фильтрует стоп-слова и слова короче 4 символов.
        Возвращает не более 5 концептов.
        """
        _STOP_WORDS = {
            "что", "как", "это", "для", "при", "или", "и", "в", "на",
            "с", "по", "из", "к", "о", "не", "но", "а", "то", "же",
            "бы", "ли", "если", "когда", "где", "кто", "чем", "так",
        }
        words = text.lower().split()
        concepts = [
            w.strip(".,!?;:\"'()[]{}") for w in words
            if len(w) > 3 and w.strip(".,!?;:\"'()[]{}") not in _STOP_WORDS
        ]
        # Дедупликация с сохранением порядка
        seen: set[str] = set()
        unique: List[str] = []
        for c in concepts:
            if c and c not in seen:
                seen.add(c)
                unique.append(c)
        return unique[:5]

    # ------------------------------------------------------------------
    # Статус и repr
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Статус онлайн-обучения."""
        return {
            "update_count": self._update_count,
            "total_confirmed": self._total_confirmed,
            "total_denied": self._total_denied,
            "total_associations": self._total_associations,
            "learning_rate": self._learning_rate,
            "confirm_delta": self._confirm_delta,
            "deny_delta": self._deny_delta,
        }

    def __repr__(self) -> str:
        return (
            f"OnlineLearner("
            f"updates={self._update_count} | "
            f"confirmed={self._total_confirmed} | "
            f"denied={self._total_denied} | "
            f"assoc={self._total_associations})"
        )

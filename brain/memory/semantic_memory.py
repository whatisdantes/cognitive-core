"""
semantic_memory.py — Семантическая память мозга (факты, понятия, связи).

Семантическая память — это "энциклопедия" мозга:
долгосрочное хранилище фактов, концептов и отношений между ними.

Принципы:
  - Граф понятий: concept → SemanticNode с relations
  - Confidence decay: неподтверждённые факты теряют уверенность
  - Персистентность: JSON на диск, работа в RAM
  - Семантический поиск: косинусное сходство через numpy (если доступно)
  - Resource-aware: при нехватке RAM — выгружает редко используемые узлы
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


# ─── Связь между понятиями ───────────────────────────────────────────────────

@dataclass
class Relation:
    """
    Направленная связь между двумя понятиями.

    Атрибуты:
        target      — целевое понятие
        weight      — сила связи (0.0 — 1.0)
        rel_type    — тип связи ('is_a', 'part_of', 'causes', 'related', 'opposite', 'example')
        confidence  — уверенность в связи (0.0 — 1.0)
        source_ref  — откуда взята связь
        ts          — время создания
    """
    target: str
    weight: float = 0.5
    rel_type: str = "related"       # 'is_a' | 'part_of' | 'causes' | 'related' | 'opposite' | 'example'
    confidence: float = 1.0
    source_ref: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target,
            "weight": round(self.weight, 4),
            "rel_type": self.rel_type,
            "confidence": round(self.confidence, 4),
            "source_ref": self.source_ref,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Relation":
        return cls(
            target=d["target"],
            weight=d.get("weight", 0.5),
            rel_type=d.get("rel_type", "related"),
            confidence=d.get("confidence", 1.0),
            source_ref=d.get("source_ref", ""),
            ts=d.get("ts", time.time()),
        )


# ─── Узел семантической памяти ───────────────────────────────────────────────

@dataclass
class SemanticNode:
    """
    Узел семантического графа — одно понятие со всеми его свойствами.

    Атрибуты:
        concept         — ключевое слово/понятие (нормализованное)
        description     — текстовое описание
        tags            — категории/теги
        confidence      — уверенность в факте (0.0 — 1.0)
        importance      — важность понятия (0.0 — 1.0)
        relations       — список связей с другими понятиями
        source_refs     — список источников
        access_count    — сколько раз обращались
        confirm_count   — сколько раз подтверждалось
        deny_count      — сколько раз опровергалось
        created_ts      — время создания
        updated_ts      — время последнего обновления
        embedding       — векторное представление (опционально)
    """
    concept: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0
    importance: float = 0.5
    relations: List[Relation] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    access_count: int = 0
    confirm_count: int = 0
    deny_count: int = 0
    created_ts: float = field(default_factory=time.time)
    updated_ts: float = field(default_factory=time.time)
    embedding: Optional[List[float]] = field(default=None, repr=False)

    def touch(self):
        """Зафиксировать обращение."""
        self.access_count += 1
        self.updated_ts = time.time()

    def confirm(self, delta: float = 0.05):
        """Подтвердить факт — повысить уверенность."""
        self.confirm_count += 1
        self.confidence = min(1.0, self.confidence + delta)
        self.updated_ts = time.time()

    def deny(self, delta: float = 0.1):
        """Опровергнуть факт — снизить уверенность."""
        self.deny_count += 1
        self.confidence = max(0.0, self.confidence - delta)
        self.updated_ts = time.time()

    def decay(self, rate: float = 0.01):
        """
        Затухание уверенности со временем (если не подтверждается).
        Важные факты затухают медленнее.
        """
        effective_rate = rate * (1.0 - self.importance * 0.5)
        self.confidence = max(0.0, self.confidence - effective_rate)
        self.updated_ts = time.time()

    def add_relation(self, relation: Relation):
        """Добавить или обновить связь."""
        for existing in self.relations:
            if existing.target == relation.target and existing.rel_type == relation.rel_type:
                # Обновляем существующую связь
                existing.weight = max(existing.weight, relation.weight)
                existing.confidence = (existing.confidence + relation.confidence) / 2
                return
        self.relations.append(relation)

    def get_relations_by_type(self, rel_type: str) -> List[Relation]:
        """Получить связи определённого типа."""
        return [r for r in self.relations if r.rel_type == rel_type]

    def age_days(self) -> float:
        """Возраст записи в днях."""
        return (time.time() - self.created_ts) / 86400

    def reliability_score(self) -> float:
        """
        Итоговая оценка надёжности факта.
        Учитывает confidence, подтверждения и опровержения.
        """
        if self.confirm_count + self.deny_count == 0:
            return self.confidence
        ratio = self.confirm_count / (self.confirm_count + self.deny_count + 1)
        return self.confidence * 0.7 + ratio * 0.3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept,
            "description": self.description,
            "tags": self.tags,
            "confidence": round(self.confidence, 4),
            "importance": round(self.importance, 4),
            "relations": [r.to_dict() for r in self.relations],
            "source_refs": self.source_refs,
            "access_count": self.access_count,
            "confirm_count": self.confirm_count,
            "deny_count": self.deny_count,
            "created_ts": self.created_ts,
            "updated_ts": self.updated_ts,
            # embedding не сохраняем в JSON (пересчитывается)
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SemanticNode":
        node = cls(
            concept=d["concept"],
            description=d.get("description", ""),
            tags=d.get("tags", []),
            confidence=d.get("confidence", 1.0),
            importance=d.get("importance", 0.5),
            source_refs=d.get("source_refs", []),
            access_count=d.get("access_count", 0),
            confirm_count=d.get("confirm_count", 0),
            deny_count=d.get("deny_count", 0),
            created_ts=d.get("created_ts", time.time()),
            updated_ts=d.get("updated_ts", time.time()),
        )
        node.relations = [Relation.from_dict(r) for r in d.get("relations", [])]
        return node

    def __repr__(self) -> str:
        return (
            f"SemanticNode('{self.concept}' | "
            f"conf={self.confidence:.2f} | "
            f"relations={len(self.relations)} | "
            f"access={self.access_count})"
        )


# ─── Семантическая память ────────────────────────────────────────────────────

class SemanticMemory:
    """
    Семантическая память — граф понятий и фактов.

    Хранит долгосрочные знания: что такое X, как X связано с Y.
    Работает в RAM, персистируется в JSON.

    Параметры:
        data_path       — путь к JSON-файлу для сохранения
        max_nodes       — максимальное количество узлов в памяти
        decay_rate      — скорость затухания уверенности (за цикл)
        autosave_every  — автосохранение каждые N операций записи
    """

    def __init__(
        self,
        data_path: str = "brain/data/memory/semantic.json",
        max_nodes: int = 10_000,
        decay_rate: float = 0.005,
        autosave_every: int = 50,
    ):
        self._data_path = data_path
        self._max_nodes = max_nodes
        self._decay_rate = decay_rate
        self._autosave_every = autosave_every

        self._nodes: Dict[str, SemanticNode] = {}
        self._write_count = 0
        self._load_count = 0

        # Загружаем с диска если файл существует
        self._load()

    # ─── Основные операции ───────────────────────────────────────────────────

    def store_fact(
        self,
        concept: str,
        description: str,
        tags: Optional[List[str]] = None,
        confidence: float = 1.0,
        importance: float = 0.5,
        source_ref: str = "",
    ) -> SemanticNode:
        """
        Сохранить факт о понятии.

        Если понятие уже существует — обновляет описание и повышает confidence.

        Returns:
            SemanticNode — созданный или обновлённый узел
        """
        concept = self._normalize(concept)

        if concept in self._nodes:
            node = self._nodes[concept]
            # Обновляем существующий узел
            if description and description != node.description:
                node.description = description
            node.confirm(delta=0.02)
            if source_ref and source_ref not in node.source_refs:
                node.source_refs.append(source_ref)
            if tags:
                for tag in tags:
                    if tag not in node.tags:
                        node.tags.append(tag)
        else:
            # Создаём новый узел
            node = SemanticNode(
                concept=concept,
                description=description,
                tags=tags or [],
                confidence=confidence,
                importance=importance,
                source_refs=[source_ref] if source_ref else [],
            )
            # Проверяем лимит
            if len(self._nodes) >= self._max_nodes:
                self._evict_least_important()
            self._nodes[concept] = node

        self._write_count += 1
        self._maybe_autosave()
        return node

    def get_fact(self, concept: str) -> Optional[SemanticNode]:
        """
        Получить факт о понятии.

        Returns:
            SemanticNode или None если не найдено
        """
        concept = self._normalize(concept)
        node = self._nodes.get(concept)
        if node:
            node.touch()
            self._load_count += 1
        return node

    def add_relation(
        self,
        concept_a: str,
        concept_b: str,
        weight: float = 0.5,
        rel_type: str = "related",
        confidence: float = 1.0,
        source_ref: str = "",
        bidirectional: bool = True,
    ):
        """
        Добавить связь между двумя понятиями.

        Args:
            concept_a:      исходное понятие
            concept_b:      целевое понятие
            weight:         сила связи (0.0 — 1.0)
            rel_type:       тип связи
            bidirectional:  создать обратную связь тоже
        """
        concept_a = self._normalize(concept_a)
        concept_b = self._normalize(concept_b)

        # Убеждаемся что оба узла существуют
        if concept_a not in self._nodes:
            self.store_fact(concept_a, "", source_ref=source_ref)
        if concept_b not in self._nodes:
            self.store_fact(concept_b, "", source_ref=source_ref)

        rel_ab = Relation(
            target=concept_b,
            weight=weight,
            rel_type=rel_type,
            confidence=confidence,
            source_ref=source_ref,
        )
        self._nodes[concept_a].add_relation(rel_ab)

        if bidirectional:
            # Обратная связь (симметричная)
            reverse_type = self._reverse_rel_type(rel_type)
            rel_ba = Relation(
                target=concept_a,
                weight=weight,
                rel_type=reverse_type,
                confidence=confidence,
                source_ref=source_ref,
            )
            self._nodes[concept_b].add_relation(rel_ba)

        self._write_count += 1
        self._maybe_autosave()

    def get_related(
        self,
        concept: str,
        rel_type: Optional[str] = None,
        min_weight: float = 0.0,
        top_n: int = 10,
    ) -> List[Tuple[str, Relation]]:
        """
        Получить связанные понятия.

        Args:
            concept:    исходное понятие
            rel_type:   фильтр по типу связи (None = все)
            min_weight: минимальная сила связи
            top_n:      максимальное количество результатов

        Returns:
            Список (concept_name, Relation), отсортированных по весу
        """
        concept = self._normalize(concept)
        node = self._nodes.get(concept)
        if not node:
            return []

        relations = node.relations
        if rel_type:
            relations = [r for r in relations if r.rel_type == rel_type]
        relations = [r for r in relations if r.weight >= min_weight]
        relations.sort(key=lambda r: r.weight * r.confidence, reverse=True)

        return [(r.target, r) for r in relations[:top_n]]

    def search(
        self,
        query: str,
        top_n: int = 10,
        min_confidence: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> List[SemanticNode]:
        """
        Поиск понятий по тексту.

        Ищет вхождение query в concept и description.
        При наличии numpy — дополнительно по косинусному сходству эмбеддингов.

        Returns:
            Список SemanticNode, отсортированных по релевантности
        """
        query_lower = query.lower()
        results = []

        for concept, node in self._nodes.items():
            if node.confidence < min_confidence:
                continue
            if tags and not any(t in node.tags for t in tags):
                continue

            # Текстовое совпадение
            score = 0.0
            if query_lower == concept:
                score = 1.0
            elif query_lower in concept:
                score = 0.8
            elif query_lower in node.description.lower():
                score = 0.5
            elif any(query_lower in tag for tag in node.tags):
                score = 0.3

            if score > 0:
                results.append((score * node.confidence, node))

        results.sort(key=lambda x: x[0], reverse=True)
        found = [node for _, node in results[:top_n]]

        for node in found:
            node.touch()

        return found

    def search_by_tags(self, tags: List[str], top_n: int = 10) -> List[SemanticNode]:
        """Поиск по тегам."""
        results = []
        for node in self._nodes.values():
            if any(t in node.tags for t in tags):
                results.append(node)
        results.sort(key=lambda n: n.importance * n.confidence, reverse=True)
        return results[:top_n]

    def confirm_fact(self, concept: str, delta: float = 0.05):
        """Подтвердить факт — повысить уверенность."""
        concept = self._normalize(concept)
        if concept in self._nodes:
            self._nodes[concept].confirm(delta)

    def deny_fact(self, concept: str, delta: float = 0.1):
        """Опровергнуть факт — снизить уверенность."""
        concept = self._normalize(concept)
        if concept in self._nodes:
            self._nodes[concept].deny(delta)

    def delete_fact(self, concept: str) -> bool:
        """Удалить факт из памяти."""
        concept = self._normalize(concept)
        if concept in self._nodes:
            del self._nodes[concept]
            return True
        return False

    def apply_decay(self, rate: Optional[float] = None):
        """
        Применить затухание ко всем фактам.
        Вызывается периодически (например, каждые N циклов).
        """
        rate = rate or self._decay_rate
        for node in self._nodes.values():
            node.decay(rate)

    # ─── Граф и аналитика ────────────────────────────────────────────────────

    def get_concept_chain(self, start: str, end: str, max_depth: int = 5) -> List[str]:
        """
        Найти цепочку связей от start до end (BFS).

        Returns:
            Список понятий от start до end, или [] если не найдено
        """
        start = self._normalize(start)
        end = self._normalize(end)

        if start not in self._nodes or end not in self._nodes:
            return []

        visited = {start}
        queue = [[start]]

        while queue:
            path = queue.pop(0)
            current = path[-1]

            if current == end:
                return path

            if len(path) >= max_depth:
                continue

            node = self._nodes.get(current)
            if not node:
                continue

            for rel in node.relations:
                if rel.target not in visited:
                    visited.add(rel.target)
                    queue.append(path + [rel.target])

        return []

    def get_most_important(self, top_n: int = 20) -> List[SemanticNode]:
        """Получить наиболее важные понятия."""
        nodes = list(self._nodes.values())
        nodes.sort(key=lambda n: n.importance * n.confidence, reverse=True)
        return nodes[:top_n]

    def get_most_accessed(self, top_n: int = 20) -> List[SemanticNode]:
        """Получить наиболее часто используемые понятия."""
        nodes = list(self._nodes.values())
        nodes.sort(key=lambda n: n.access_count, reverse=True)
        return nodes[:top_n]

    def get_uncertain_facts(self, threshold: float = 0.5) -> List[SemanticNode]:
        """Получить факты с низкой уверенностью (кандидаты на проверку)."""
        return [n for n in self._nodes.values() if n.confidence < threshold]

    # ─── Персистентность ─────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None):
        """Сохранить семантическую память на диск (JSON)."""
        path = path or self._data_path
        os.makedirs(os.path.dirname(path), exist_ok=True)

        data = {
            "version": "1.0",
            "saved_ts": time.time(),
            "node_count": len(self._nodes),
            "nodes": {concept: node.to_dict() for concept, node in self._nodes.items()},
        }

        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Атомарная замена файла
        if os.path.exists(path):
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)

        _logger.info("Семантическая память сохранена: %d понятий -> %s", len(self._nodes), path)

    def _load(self):
        """Загрузить семантическую память с диска."""
        if not os.path.exists(self._data_path):
            return

        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            nodes_data = data.get("nodes", {})
            for concept, node_dict in nodes_data.items():
                self._nodes[concept] = SemanticNode.from_dict(node_dict)

            _logger.info("Семантическая память загружена: %d понятий <- %s", len(self._nodes), self._data_path)
        except Exception as e:
            _logger.warning("Ошибка загрузки семантической памяти: %s", e)

    def _maybe_autosave(self):
        """Автосохранение каждые N операций записи."""
        if self._write_count % self._autosave_every == 0:
            self.save()

    # ─── Вспомогательные методы ──────────────────────────────────────────────

    @staticmethod
    def _normalize(concept: str) -> str:
        """Нормализовать ключ понятия (нижний регистр, без лишних пробелов)."""
        return concept.strip().lower()

    @staticmethod
    def _reverse_rel_type(rel_type: str) -> str:
        """Получить обратный тип связи."""
        reverses = {
            "is_a": "has_instance",
            "has_instance": "is_a",
            "part_of": "has_part",
            "has_part": "part_of",
            "causes": "caused_by",
            "caused_by": "causes",
            "related": "related",
            "opposite": "opposite",
            "example": "exemplified_by",
            "exemplified_by": "example",
        }
        return reverses.get(rel_type, "related")

    def _evict_least_important(self):
        """Вытеснить наименее важный и редко используемый узел."""
        if not self._nodes:
            return
        # Сортируем по score = importance * confidence * log(access_count + 1)
        scored = [
            (n.importance * n.confidence * math.log(n.access_count + 1), k)
            for k, n in self._nodes.items()
        ]
        scored.sort(key=lambda x: x[0])
        worst_key = scored[0][1]
        del self._nodes[worst_key]

    # ─── Статистика ──────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Статус семантической памяти."""
        confidences = [n.confidence for n in self._nodes.values()]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        total_relations = sum(len(n.relations) for n in self._nodes.values())

        return {
            "type": "semantic_memory",
            "node_count": len(self._nodes),
            "max_nodes": self._max_nodes,
            "total_relations": total_relations,
            "avg_confidence": round(avg_conf, 3),
            "uncertain_facts": len(self.get_uncertain_facts()),
            "write_count": self._write_count,
            "load_count": self._load_count,
            "data_path": self._data_path,
        }

    def display_status(self):
        """Вывести статус в консоль."""
        s = self.status()
        print(f"\n{'─'*50}")
        print(f"🧠 Семантическая память")
        print(f"  Понятий: {s['node_count']} / {s['max_nodes']}")
        print(f"  Связей: {s['total_relations']}")
        print(f"  Средняя уверенность: {s['avg_confidence']:.2%}")
        print(f"  Неуверенных фактов: {s['uncertain_facts']}")
        print(f"  Записей: {s['write_count']} | Чтений: {s['load_count']}")
        print(f"{'─'*50}\n")

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, concept: str) -> bool:
        return self._normalize(concept) in self._nodes

    def __repr__(self) -> str:
        return (
            f"SemanticMemory(nodes={len(self._nodes)} | "
            f"relations={sum(len(n.relations) for n in self._nodes.values())})"
        )

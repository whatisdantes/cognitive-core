"""
working_memory.py — Рабочая память мозга (аналог кратковременной памяти).

Рабочая память — это "стол" мозга: то, с чем он работает прямо сейчас.
Ограниченный размер (~7 чанков по Миллеру), быстрый доступ, только RAM.

Принципы:
  - Sliding window: новые элементы вытесняют старые
  - Importance-aware: важные элементы не вытесняются
  - Resource-aware: при нехватке RAM — уменьшает окно
  - Поиск по содержимому и тегам
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


# ─── Элемент рабочей памяти ──────────────────────────────────────────────────

@dataclass
class MemoryItem:
    """
    Один элемент рабочей памяти.

    Атрибуты:
        content     — содержимое (текст, факт, объект)
        modality    — тип данных ('text', 'image', 'audio', 'concept')
        ts          — время добавления (unix timestamp)
        importance  — важность (0.0 — 1.0); важные не вытесняются
        source_ref  — ссылка на источник (файл, URL, "user_input")
        tags        — теги для поиска
        access_count — сколько раз обращались к элементу
    """
    content: Any
    modality: str = "text"
    ts: float = field(default_factory=time.time)
    importance: float = 0.5
    source_ref: str = ""
    tags: List[str] = field(default_factory=list)
    access_count: int = 0

    def touch(self):
        """Зафиксировать обращение к элементу."""
        self.access_count += 1

    def age_seconds(self) -> float:
        """Возраст элемента в секундах."""
        return time.time() - self.ts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": str(self.content)[:500],  # обрезаем для сериализации
            "modality": self.modality,
            "ts": self.ts,
            "importance": self.importance,
            "source_ref": self.source_ref,
            "tags": self.tags,
            "access_count": self.access_count,
        }

    def __repr__(self) -> str:
        content_preview = str(self.content)[:60]
        return (
            f"MemoryItem('{content_preview}' | "
            f"mod={self.modality} | imp={self.importance:.2f} | "
            f"age={self.age_seconds():.1f}s)"
        )


# ─── Рабочая память ──────────────────────────────────────────────────────────

class WorkingMemory:
    """
    Рабочая память мозга — активный контекст текущего цикла.

    Параметры:
        max_size        — максимальное количество элементов (по умолчанию 20)
        importance_threshold — порог важности для защиты от вытеснения (0.8+)
        ram_limit_pct   — при превышении этого % RAM — уменьшить окно
    """

    DEFAULT_MAX_SIZE = 20
    IMPORTANCE_PROTECT_THRESHOLD = 0.8  # элементы выше этого порога не вытесняются
    RAM_LIMIT_PCT = 80.0                # % RAM, при котором сжимаем окно

    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        ram_limit_pct: float = RAM_LIMIT_PCT,
    ):
        self._max_size = max_size
        self._ram_limit_pct = ram_limit_pct
        self._items: Deque[MemoryItem] = deque()
        self._protected: List[MemoryItem] = []  # важные элементы (не вытесняются)
        self._push_count = 0
        self._evict_count = 0

    # ─── Основные операции ───────────────────────────────────────────────────

    def push(
        self,
        content: Any,
        modality: str = "text",
        importance: float = 0.5,
        source_ref: str = "",
        tags: Optional[List[str]] = None,
    ) -> MemoryItem:
        """
        Добавить элемент в рабочую память.

        Если память заполнена — вытесняет наименее важный старый элемент.
        Элементы с importance >= IMPORTANCE_PROTECT_THRESHOLD защищены.

        Returns:
            Созданный MemoryItem
        """
        item = MemoryItem(
            content=content,
            modality=modality,
            importance=importance,
            source_ref=source_ref,
            tags=tags or [],
        )

        # Адаптируем размер окна под доступную RAM
        effective_max = self._adaptive_max_size()

        # Защищённые элементы — в отдельный список
        if importance >= self.IMPORTANCE_PROTECT_THRESHOLD:
            self._protected.append(item)
            # Ограничиваем защищённые (не более 1/4 от max_size)
            max_protected = max(5, effective_max // 4)
            if len(self._protected) > max_protected:
                # Вытесняем наименее важный из защищённых
                self._protected.sort(key=lambda x: x.importance)
                self._protected.pop(0)
        else:
            # Обычные элементы — в sliding window
            while len(self._items) >= effective_max:
                self._evict_oldest()
            self._items.append(item)

        self._push_count += 1
        return item

    def get_context(self, n: int = 10) -> List[MemoryItem]:
        """
        Получить последние N элементов контекста.

        Returns:
            Список элементов (защищённые + обычные), отсортированных по времени
        """
        all_items = list(self._protected) + list(self._items)
        all_items.sort(key=lambda x: x.ts)
        result = all_items[-n:] if n > 0 else all_items
        for item in result:
            item.touch()
        return result

    def get_all(self) -> List[MemoryItem]:
        """Получить все элементы (защищённые + обычные)."""
        all_items = list(self._protected) + list(self._items)
        all_items.sort(key=lambda x: x.ts)
        return all_items

    def search(
        self,
        query: str,
        modality: Optional[str] = None,
        tags: Optional[List[str]] = None,
        top_n: int = 5,
    ) -> List[MemoryItem]:
        """
        Поиск по содержимому рабочей памяти.

        Args:
            query:    строка поиска (ищем вхождение в content)
            modality: фильтр по типу данных
            tags:     фильтр по тегам
            top_n:    максимальное количество результатов

        Returns:
            Список подходящих элементов, отсортированных по важности
        """
        query_lower = query.lower()
        all_items = self.get_all()
        results = []

        for item in all_items:
            content_str = str(item.content).lower()

            # Фильтр по тексту
            if query_lower and query_lower not in content_str:
                continue

            # Фильтр по модальности
            if modality and item.modality != modality:
                continue

            # Фильтр по тегам
            if tags and not any(t in item.tags for t in tags):
                continue

            results.append(item)

        # Сортируем по важности (убывание), затем по времени (убывание)
        results.sort(key=lambda x: (x.importance, x.ts), reverse=True)
        return results[:top_n]

    def peek_last(self) -> Optional[MemoryItem]:
        """Посмотреть последний добавленный элемент (без изменения счётчика)."""
        if self._items:
            return self._items[-1]
        if self._protected:
            return max(self._protected, key=lambda x: x.ts)
        return None

    def clear(self, keep_important: bool = True):
        """
        Очистить рабочую память.

        Args:
            keep_important: если True — сохранить защищённые элементы
        """
        self._items.clear()
        if not keep_important:
            self._protected.clear()
        self._evict_count = 0

    def remove(self, item: MemoryItem) -> bool:
        """Удалить конкретный элемент."""
        try:
            self._items.remove(item)
            return True
        except ValueError:
            pass
        try:
            self._protected.remove(item)
            return True
        except ValueError:
            pass
        return False

    # ─── Внутренние методы ───────────────────────────────────────────────────

    def _evict_oldest(self):
        """Вытеснить самый старый (и наименее важный) элемент."""
        if not self._items:
            return
        # Вытесняем с левого конца (самый старый)
        self._items.popleft()
        self._evict_count += 1

    def _adaptive_max_size(self) -> int:
        """
        Адаптировать максимальный размер окна под доступную RAM.

        При нехватке RAM — уменьшаем окно, чтобы освободить память.
        """
        if not _PSUTIL_AVAILABLE:
            return self._max_size

        try:
            ram = psutil.virtual_memory()
            ram_pct = ram.percent

            if ram_pct > self._ram_limit_pct:
                # RAM > 80% → уменьшаем окно до 50% (но не больше max_size)
                return min(self._max_size, max(2, self._max_size // 2))
            elif ram_pct > self._ram_limit_pct * 0.85:
                # RAM > 68% → уменьшаем окно до 75% (но не больше max_size)
                return min(self._max_size, max(3, int(self._max_size * 0.75)))
        except Exception:
            pass

        return self._max_size

    # ─── Статистика ──────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        """Текущее количество элементов (обычные + защищённые)."""
        return len(self._items) + len(self._protected)

    @property
    def max_size(self) -> int:
        return self._max_size

    def ram_usage_mb(self) -> float:
        """Примерное использование RAM рабочей памятью (МБ)."""
        if not _PSUTIL_AVAILABLE:
            return 0.0
        try:
            import sys
            total = sum(sys.getsizeof(item.content) for item in self.get_all())
            return total / (1024 * 1024)
        except Exception:
            return 0.0

    def status(self) -> Dict[str, Any]:
        """Статус рабочей памяти."""
        ram_info = {}
        if _PSUTIL_AVAILABLE:
            try:
                vm = psutil.virtual_memory()
                ram_info = {
                    "system_ram_pct": vm.percent,
                    "system_ram_available_gb": round(vm.available / (1024**3), 2),
                }
            except Exception:
                pass

        return {
            "type": "working_memory",
            "size": self.size,
            "normal_items": len(self._items),
            "protected_items": len(self._protected),
            "max_size": self._max_size,
            "effective_max": self._adaptive_max_size(),
            "push_count": self._push_count,
            "evict_count": self._evict_count,
            "ram_usage_mb": round(self.ram_usage_mb(), 3),
            **ram_info,
        }

    def display_status(self):
        """Вывести статус в консоль."""
        s = self.status()
        print(f"\n{'─'*50}")
        print(f"🧠 Рабочая память")
        print(f"  Элементов: {s['normal_items']} обычных + {s['protected_items']} защищённых")
        print(f"  Лимит: {s['effective_max']} (макс: {s['max_size']})")
        print(f"  Добавлено: {s['push_count']} | Вытеснено: {s['evict_count']}")
        if "system_ram_pct" in s:
            print(f"  RAM системы: {s['system_ram_pct']:.1f}% | Свободно: {s['system_ram_available_gb']} GB")
        print(f"{'─'*50}\n")

    # ─── Представление ───────────────────────────────────────────────────────

    def __len__(self) -> int:
        return self.size

    def __repr__(self) -> str:
        return (
            f"WorkingMemory(size={self.size}/{self._max_size} | "
            f"protected={len(self._protected)} | "
            f"evicted={self._evict_count})"
        )

    def __iter__(self):
        return iter(self.get_all())

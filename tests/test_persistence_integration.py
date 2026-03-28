"""
test_persistence_integration.py — Интеграционный тест персистентности.

P2-20: «сохранил → перезапустил → нашёл»

Проверяет полный цикл:
  1. Создать MemoryManager с временной директорией
  2. Сохранить факт + эпизод + источник
  3. save_all()
  4. Создать НОВЫЙ MemoryManager с тем же data_dir
  5. Проверить что данные загрузились и доступны через retrieve/get
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from brain.memory.memory_manager import MemoryManager


@pytest.fixture()
def tmp_data_dir():
    """Временная директория для данных памяти.

    На Windows SQLite может удерживать файл после close() —
    используем ignore_cleanup_errors для надёжности.
    """
    d = tempfile.mkdtemp(prefix="brain_persist_")
    yield d
    # Очистка с игнорированием ошибок блокировки (Windows SQLite WAL)
    shutil.rmtree(d, ignore_errors=True)


class TestPersistenceIntegration:
    """Интеграционные тесты: сохранение → перезагрузка → поиск."""

    def test_semantic_fact_survives_restart(self, tmp_data_dir: str):
        """Факт из семантической памяти доступен после перезапуска."""
        # --- Фаза 1: запись ---
        mm1 = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm1.start()

        node = mm1.store_fact(
            concept="нейрон",
            description="Нейрон — это основная клетка нервной системы.",
            tags=["биология", "нейронаука"],
            confidence=0.95,
            importance=0.8,
            source_ref="учебник_биологии",
        )
        assert node is not None
        assert node.concept == "нейрон"

        mm1.save_all()
        mm1.stop(save=False)  # уже сохранили

        # --- Фаза 2: перезагрузка ---
        mm2 = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm2.start()

        # Прямой доступ к факту
        loaded_node = mm2.get_fact("нейрон")
        assert loaded_node is not None, "Факт 'нейрон' не найден после перезагрузки"
        assert "клетка" in loaded_node.description.lower()
        assert loaded_node.confidence == pytest.approx(0.95, abs=0.01)

        mm2.stop(save=False)

    def test_episodic_memory_survives_restart(self, tmp_data_dir: str):
        """Эпизод доступен после перезапуска."""
        # --- Фаза 1: запись ---
        mm1 = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm1.start()

        ep = mm1.store_episode(
            content="Пользователь спросил про нейроны.",
            modality="text",
            source="user_input",
            importance=0.7,
            tags=["вопрос"],
            concepts=["нейрон"],
        )
        assert ep is not None
        episode_id = ep.episode_id

        mm1.save_all()
        mm1.stop(save=False)

        # --- Фаза 2: перезагрузка ---
        mm2 = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm2.start()

        # Поиск по тексту
        results = mm2.retrieve("нейрон", memory_types=["episodic"])
        assert results.episodic, "Эпизоды не найдены после перезагрузки"

        # Проверяем что наш эпизод среди результатов
        found_ids = [e.episode_id for e in results.episodic]
        assert episode_id in found_ids, f"Эпизод {episode_id} не найден среди {found_ids}"

        mm2.stop(save=False)

    def test_source_memory_survives_restart(self, tmp_data_dir: str):
        """Информация об источнике доступна после перезапуска."""
        # --- Фаза 1: запись ---
        mm1 = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm1.start()

        mm1.source.register("учебник_биологии", source_type="file")
        mm1.source.add_fact("учебник_биологии")
        mm1.source.add_fact("учебник_биологии")
        # Повышаем доверие через update_trust (SourceMemory API)
        mm1.source.update_trust("учебник_биологии", confirmed=True, delta=0.05)

        mm1.save_all()
        mm1.stop(save=False)

        # --- Фаза 2: перезагрузка ---
        mm2 = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm2.start()

        record = mm2.source.get_record("учебник_биологии")
        assert record is not None, "Источник не найден после перезагрузки"
        assert record.fact_count >= 2

        mm2.stop(save=False)

    def test_full_store_retrieve_cycle(self, tmp_data_dir: str):
        """Полный цикл: store → save → restart → retrieve → verify."""
        # --- Фаза 1: запись через единый API ---
        mm1 = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm1.start()

        result = mm1.store(
            content="синапс это соединение между нейронами",
            modality="text",
            importance=0.8,
            source_ref="учебник",
            tags=["биология"],
            concepts=["синапс", "нейрон"],
            auto_extract_facts=True,
        )
        # Должен быть хотя бы working + episodic
        assert "working" in result
        assert "episodic" in result

        mm1.save_all()
        mm1.stop(save=False)

        # --- Фаза 2: перезагрузка и поиск ---
        mm2 = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm2.start()

        search_result = mm2.retrieve("синапс")
        assert not search_result.is_empty(), "Поиск 'синапс' не дал результатов после перезагрузки"

        mm2.stop(save=False)

    def test_multiple_save_load_cycles(self, tmp_data_dir: str):
        """Несколько циклов сохранения/загрузки не теряют данные."""
        concepts = ["аксон", "дендрит", "миелин"]

        for i, concept in enumerate(concepts):
            mm = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
            mm.start()

            mm.store_fact(
                concept=concept,
                description=f"{concept} — элемент нервной системы #{i}",
                importance=0.7,
            )
            mm.save_all()
            mm.stop(save=False)

        # Финальная проверка — все 3 факта на месте
        mm_final = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm_final.start()

        for concept in concepts:
            node = mm_final.get_fact(concept)
            assert node is not None, f"Факт '{concept}' потерян после множественных циклов"

        mm_final.stop(save=False)

    def test_data_files_created(self, tmp_data_dir: str):
        """save_all() создаёт файлы/БД на диске."""
        mm = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
        mm.start()

        mm.store_fact(concept="тест", description="тестовый факт")
        mm.save_all()
        mm.stop(save=False)

        # Проверяем что что-то записалось на диск
        files = os.listdir(tmp_data_dir)
        assert len(files) > 0, f"Директория {tmp_data_dir} пуста после save_all()"

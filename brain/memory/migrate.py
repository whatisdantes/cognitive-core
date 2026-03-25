"""
migrate.py — Миграция JSON → SQLite для системы памяти.

Безопасная, идемпотентная миграция:
  - Backup JSON файлов перед миграцией
  - Marker в _meta после успешной миграции
  - При ошибке — не удаляет JSON, логирует
  - Повторный запуск безопасен (проверяет marker)

Использование (ручная утилита):
    python -m brain.memory.migrate brain/data/memory

Использование (программно):
    from brain.memory.migrate import migrate_json_to_sqlite
    migrate_json_to_sqlite("brain/data/memory")
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from typing import Any, Dict, Optional

from .storage import MemoryDatabase

_logger = logging.getLogger(__name__)


# ─── Маркер миграции ─────────────────────────────────────────────────────────

MIGRATION_MARKER_KEY = "json_migration_completed"


def is_migrated(db: MemoryDatabase) -> bool:
    """Проверить, была ли уже выполнена миграция."""
    val = db.get_meta(MIGRATION_MARKER_KEY)
    return val is not None


def _set_migration_marker(db: MemoryDatabase):
    """Установить маркер успешной миграции."""
    db.set_meta(MIGRATION_MARKER_KEY, str(time.time()))
    db.commit()


# ─── Backup ──────────────────────────────────────────────────────────────────

def _backup_json_files(data_dir: str) -> Optional[str]:
    """
    Создать backup JSON файлов перед миграцией.

    Returns:
        Путь к backup директории или None если нечего бэкапить
    """
    json_files = [
        f for f in os.listdir(data_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(data_dir, f))
    ]

    if not json_files:
        return None

    backup_dir = os.path.join(data_dir, f"backup_json_{int(time.time())}")
    os.makedirs(backup_dir, exist_ok=True)

    for fname in json_files:
        src = os.path.join(data_dir, fname)
        dst = os.path.join(backup_dir, fname)
        shutil.copy2(src, dst)

    _logger.info("Backup JSON: %d файлов → %s", len(json_files), backup_dir)
    return backup_dir


# ─── Загрузка JSON ───────────────────────────────────────────────────────────

def _load_json_safe(path: str) -> Optional[Dict[str, Any]]:
    """Безопасно загрузить JSON файл."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        _logger.warning("Не удалось загрузить %s: %s", path, e)
        return None


# ─── Миграция отдельных модулей ──────────────────────────────────────────────

def _migrate_semantic(db: MemoryDatabase, data_dir: str) -> int:
    """Мигрировать семантическую память."""
    path = os.path.join(data_dir, "semantic.json")
    data = _load_json_safe(path)
    if not data:
        return 0

    nodes = data.get("nodes", {})
    count = 0
    for concept, node_dict in nodes.items():
        db.upsert_semantic_node(concept, node_dict)
        # Связи
        for rel in node_dict.get("relations", []):
            db.upsert_relation(concept, rel["target"], rel)
        count += 1

    _logger.info("Мигрировано semantic: %d узлов", count)
    return count


def _migrate_episodes(db: MemoryDatabase, data_dir: str) -> int:
    """Мигрировать эпизодическую память."""
    path = os.path.join(data_dir, "episodes.json")
    data = _load_json_safe(path)
    if not data:
        return 0

    episodes = data.get("episodes", [])
    count = 0
    for ep_dict in episodes:
        episode_id = ep_dict.get("episode_id", "")
        if episode_id:
            db.upsert_episode(episode_id, ep_dict)
            count += 1

    _logger.info("Мигрировано episodes: %d эпизодов", count)
    return count


def _migrate_sources(db: MemoryDatabase, data_dir: str) -> int:
    """Мигрировать память об источниках."""
    path = os.path.join(data_dir, "sources.json")
    data = _load_json_safe(path)
    if not data:
        return 0

    sources = data.get("sources", {})
    count = 0
    for source_id, rec_dict in sources.items():
        db.upsert_source(source_id, rec_dict)
        count += 1

    _logger.info("Мигрировано sources: %d источников", count)
    return count


def _migrate_procedures(db: MemoryDatabase, data_dir: str) -> int:
    """Мигрировать процедурную память."""
    path = os.path.join(data_dir, "procedures.json")
    data = _load_json_safe(path)
    if not data:
        return 0

    procedures = data.get("procedures", {})
    count = 0
    for name, proc_dict in procedures.items():
        db.upsert_procedure(name, proc_dict)
        count += 1

    _logger.info("Мигрировано procedures: %d процедур", count)
    return count


# ─── Главная функция миграции ────────────────────────────────────────────────

def migrate_json_to_sqlite(
    data_dir: str,
    db_path: Optional[str] = None,
    backup: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Мигрировать все JSON файлы памяти в SQLite.

    Args:
        data_dir:   директория с JSON файлами
        db_path:    путь к SQLite файлу (по умолчанию data_dir/memory.db)
        backup:     создать backup JSON перед миграцией
        force:      выполнить даже если уже мигрировано

    Returns:
        Статистика миграции: {"semantic": N, "episodes": N, "sources": N, "procedures": N}
    """
    if db_path is None:
        db_path = os.path.join(data_dir, "memory.db")

    result = {
        "status": "skipped",
        "semantic": 0,
        "episodes": 0,
        "sources": 0,
        "procedures": 0,
        "backup_dir": None,
        "db_path": db_path,
    }

    # Проверяем что директория существует
    if not os.path.isdir(data_dir):
        _logger.warning("Директория не существует: %s", data_dir)
        result["status"] = "error"
        result["error"] = f"Directory not found: {data_dir}"
        return result

    # Проверяем наличие JSON файлов
    json_files = [
        f for f in os.listdir(data_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(data_dir, f))
    ]
    if not json_files:
        _logger.info("Нет JSON файлов для миграции в %s", data_dir)
        result["status"] = "no_json_files"
        return result

    # Открываем/создаём БД
    db = MemoryDatabase(db_path)

    try:
        # Проверяем маркер
        if not force and is_migrated(db):
            _logger.info("Миграция уже выполнена (marker найден). Пропускаем.")
            result["status"] = "already_migrated"
            return result

        # Backup
        if backup:
            backup_dir = _backup_json_files(data_dir)
            result["backup_dir"] = backup_dir

        # Миграция
        _logger.info("Начинаем миграцию JSON → SQLite: %s → %s", data_dir, db_path)

        db.begin()
        try:
            result["semantic"] = _migrate_semantic(db, data_dir)
            result["episodes"] = _migrate_episodes(db, data_dir)
            result["sources"] = _migrate_sources(db, data_dir)
            result["procedures"] = _migrate_procedures(db, data_dir)

            _set_migration_marker(db)
            db.commit()

            result["status"] = "success"
            total = sum(result[k] for k in ("semantic", "episodes", "sources", "procedures"))
            _logger.info(
                "Миграция завершена: %d записей (semantic=%d, episodes=%d, sources=%d, procedures=%d)",
                total, result["semantic"], result["episodes"],
                result["sources"], result["procedures"],
            )

        except Exception as e:
            db.rollback()
            result["status"] = "error"
            result["error"] = str(e)
            _logger.error("Ошибка миграции, откат: %s", e)
            raise

    finally:
        db.close()

    return result


# ─── Auto-migration (вызывается из MemoryManager) ────────────────────────────

def auto_migrate_if_needed(
    data_dir: str,
    db_path: Optional[str] = None,
) -> bool:
    """
    Автоматическая миграция при первом запуске.

    Вызывается из MemoryManager.__init__().
    Мигрирует только если:
    1. Есть JSON файлы в data_dir
    2. Нет маркера миграции в БД

    Returns:
        True если миграция была выполнена
    """
    if db_path is None:
        db_path = os.path.join(data_dir, "memory.db")

    # Быстрая проверка: есть ли JSON файлы?
    if not os.path.isdir(data_dir):
        return False

    json_files = [
        f for f in os.listdir(data_dir)
        if f.endswith(".json") and os.path.isfile(os.path.join(data_dir, f))
    ]
    if not json_files:
        return False

    # Проверяем маркер в БД (если БД уже существует)
    if os.path.exists(db_path):
        db = MemoryDatabase(db_path)
        try:
            if is_migrated(db):
                return False
        finally:
            db.close()

    # Выполняем миграцию
    try:
        result = migrate_json_to_sqlite(data_dir, db_path, backup=True, force=False)
        return result["status"] == "success"
    except Exception as e:
        _logger.error("Автомиграция не удалась: %s. JSON файлы сохранены.", e)
        return False


# ─── CLI entry point ─────────────────────────────────────────────────────────

def main():
    """CLI утилита для ручной миграции."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 2:
        print("Использование: python -m brain.memory.migrate <data_dir> [--force]")
        print("Пример: python -m brain.memory.migrate brain/data/memory")
        sys.exit(1)

    data_dir = sys.argv[1]
    force = "--force" in sys.argv

    result = migrate_json_to_sqlite(data_dir, force=force)

    print(f"\nРезультат миграции: {result['status']}")
    if result["status"] == "success":
        print(f"  Semantic:   {result['semantic']} узлов")
        print(f"  Episodes:   {result['episodes']} эпизодов")
        print(f"  Sources:    {result['sources']} источников")
        print(f"  Procedures: {result['procedures']} процедур")
        if result["backup_dir"]:
            print(f"  Backup:     {result['backup_dir']}")
        print(f"  DB:         {result['db_path']}")
    elif result.get("error"):
        print(f"  Ошибка: {result['error']}")


if __name__ == "__main__":
    main()

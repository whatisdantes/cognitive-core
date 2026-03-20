"""
logging — Система логирования и наблюдаемости.

Модули:
    jsonl_logger.py     — запись событий в JSONL формат (machine-readable)
    digest_generator.py — генерация человекочитаемых сводок по циклу
    trace_builder.py    — построение цепочки причинности (trace chain)
    metrics_collector.py — сбор и обновление KPI метрик
    dashboard.py        — текстовый live-дашборд метрик в терминале

Формат лога:
    {"ts": ..., "session_id": ..., "trace_id": ..., "module": ...,
     "event": ..., "input_refs": [...], "state": {"cpu_pct": ..., "ram_mb": ...},
     "decision": {...}, "latency_ms": ..., "notes": "..."}
"""

"""
core — Ядро автономного цикла мозга.

Модули:
    scheduler.py        — тик-планировщик (clock-driven + event-driven)
    event_bus.py        — publish/subscribe шина событий
    events.py           — dataclasses всех типов событий
    resource_monitor.py — мониторинг CPU/RAM, graceful degradation
    attention_controller.py — бюджет вычислений по модальностям
"""

"""
brain — Искусственный мультимодальный мозг.

Архитектура:
    core/       — always-on loop, scheduler, resource monitor, event bus
    perception/ — text/vision/audio ingestors, input router
    encoders/   — text/vision/audio/temporal encoders
    fusion/     — cross-modal fusion, entity linking, confidence calibration
    memory/     — working/episodic/semantic/procedural/source memory
    cognition/  — planner, reasoner, contradiction detector, uncertainty monitor
    learning/   — online learner, replay engine, self-supervised, hypothesis engine
    logging/    — JSONL logger, digest generator, metrics collector
    safety/     — source trust, conflict detector
    output/     — dialogue responder, action proposer, trace builder
    data/       — persistent storage (memory, weights, logs)
"""

__version__ = "0.3.0"

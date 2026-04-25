#!/usr/bin/env python3
"""
Bulk material ingestion for cognitive-core.

Reads supported documents, stores their chunks in MemoryManager, and can
optionally use an LLM provider to extract semantic facts.

Examples:
    python examples/ingest_material.py docs/BRAIN.md --data-dir brain/data/memory
    python examples/ingest_material.py materials/ --recursive --extract-facts-with-llm \
        --llm-provider blackbox --llm-model blackboxai/anthropic/claude-sonnet-4.6
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Iterable

from brain.bridges.llm_bridge import LLMProvider, LLMRequest
from brain.cli import _build_llm_provider, _load_dotenv
from brain.logging import BrainLogger
from brain.memory import MemoryManager
from brain.perception import InputRouter, InputType
from brain.perception.text_ingestor import TEXT_EXTENSIONS


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest-material",
        description="Import text documents into cognitive-core memory.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Files or directories to ingest.",
    )
    parser.add_argument(
        "--data-dir",
        default="brain/data/memory",
        help="Memory directory (default: brain/data/memory).",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Optional BrainLogger JSONL directory.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        help="BrainLogger minimum level.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into directories.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore router in-process deduplication.",
    )
    parser.add_argument(
        "--importance",
        type=float,
        default=0.65,
        help="Importance for stored chunks, 0..1 (default: 0.65).",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=0,
        help="Maximum chunks to ingest across all files (0 = unlimited).",
    )
    parser.add_argument(
        "--skip-chunks",
        type=int,
        default=0,
        help="Skip this many chunks before storing (useful for batch ingestion).",
    )
    parser.add_argument(
        "--no-auto-extract",
        action="store_true",
        help="Disable built-in fact-pattern extraction during chunk storage.",
    )
    parser.add_argument(
        "--extract-facts-with-llm",
        action="store_true",
        help="Ask an LLM to extract semantic facts from each chunk.",
    )
    parser.add_argument(
        "--llm-provider",
        default=None,
        choices=["openai", "anthropic", "blackbox", "mock"],
        help="LLM provider for --extract-facts-with-llm.",
    )
    parser.add_argument(
        "--llm-api-key",
        default=None,
        help="LLM API key. If omitted, provider-specific env vars/.env are used.",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model name.",
    )
    parser.add_argument(
        "--facts-per-chunk",
        type=int,
        default=5,
        help="Maximum semantic facts to request per chunk (default: 5).",
    )
    return parser


def iter_supported_files(paths: Iterable[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            if path.suffix.lower() in TEXT_EXTENSIONS:
                files.append(path)
            else:
                print(f"[skip] unsupported file type: {path}")
            continue
        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            for child in iterator:
                if child.is_file() and child.suffix.lower() in TEXT_EXTENSIONS:
                    files.append(child)
            continue
        print(f"[skip] path not found: {path}")
    return sorted(set(files))


def extract_facts(
    provider: LLMProvider,
    text: str,
    source: str,
    facts_per_chunk: int,
) -> list[tuple[str, str]]:
    prompt = (
        "Извлеки из материала только устойчивые факты для долговременной памяти.\n"
        "Формат каждой строки строго: Понятие — краткое описание.\n"
        f"Не больше {facts_per_chunk} строк. Если фактов нет, ответь NONE.\n\n"
        f"Источник: {source}\n"
        f"Материал:\n{text[:6000]}"
    )
    response = provider.complete(
        LLMRequest(
            prompt=prompt,
            system_prompt=(
                "Ты извлекаешь факты для семантической памяти. "
                "Не добавляй пояснений, списков с маркерами или markdown."
            ),
            max_tokens=512,
            temperature=0.1,
            metadata={"step": "ingest_material_extract_facts", "source": source},
        )
    )
    return parse_fact_lines(response.text)


def parse_fact_lines(text: str) -> list[tuple[str, str]]:
    facts: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*0123456789. ")
        if not line or line.upper() == "NONE":
            continue
        match = re.match(r"^(.{2,120}?)\s+[—-]\s+(.{5,800})$", line)
        if not match:
            continue
        concept = match.group(1).strip(" :;,.")
        description = match.group(2).strip()
        if concept and description:
            facts.append((concept, description))
    return facts


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    brain_log = BrainLogger(log_dir=args.log_dir, min_level=args.log_level) if args.log_dir else None
    llm: LLMProvider | None = None
    if args.extract_facts_with_llm:
        llm = _build_llm_provider(args.llm_provider, args.llm_api_key, args.llm_model)
        if llm is None or not llm.is_available():
            print("[error] --extract-facts-with-llm requires an available --llm-provider", file=sys.stderr)
            return 2

    files = iter_supported_files(args.paths, recursive=args.recursive)
    if not files:
        print("[done] no supported files found")
        return 0

    data_path = Path(args.data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    mm = MemoryManager(data_dir=str(data_path), brain_logger=brain_log)
    router = InputRouter(brain_logger=brain_log)

    chunks_seen = 0
    chunks_stored = 0
    facts_stored = 0
    files_done = 0

    mm.start()
    try:
        for file_path in files:
            events = router.route(
                str(file_path),
                force=args.force,
                input_type=InputType.FILE,
            )
            if not events:
                print(f"[skip] no events: {file_path}")
                continue

            files_done += 1
            for event in events:
                chunks_seen += 1
                if chunks_seen <= args.skip_chunks:
                    continue
                if args.max_chunks and chunks_stored >= args.max_chunks:
                    break

                stored = mm.store(
                    event.content,
                    modality=event.modality,
                    importance=args.importance,
                    source_ref=event.source,
                    tags=["ingested", file_path.suffix.lower().lstrip(".")],
                    trace_id=event.trace_id,
                    session_id=event.session_id,
                    auto_extract_facts=not args.no_auto_extract,
                )
                chunks_stored += 1
                if "semantic" in stored:
                    facts_stored += 1

                if llm is not None:
                    try:
                        facts = extract_facts(
                            provider=llm,
                            text=str(event.content),
                            source=event.source,
                            facts_per_chunk=args.facts_per_chunk,
                        )
                    except Exception as exc:
                        logger.warning("LLM fact extraction failed for %s: %s", event.source, exc)
                        facts = []
                    for concept, description in facts:
                        mm.store_fact(
                            concept=concept,
                            description=description,
                            tags=["llm_extracted", "ingested"],
                            confidence=0.75,
                            importance=args.importance,
                            source_ref=event.source,
                        )
                        facts_stored += 1

            print(f"[ok] {file_path} -> {len(events)} chunks")
            if args.max_chunks and chunks_stored >= args.max_chunks:
                break

        mm.save_all()
    finally:
        mm.stop(save=False)
        if brain_log:
            brain_log.flush()
            brain_log.close()

    print(
        "[done] files=%d chunks=%d skipped=%d semantic_facts=%d data_dir=%s"
        % (files_done, chunks_stored, min(args.skip_chunks, chunks_seen), facts_stored, data_path)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

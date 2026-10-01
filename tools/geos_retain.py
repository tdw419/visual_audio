#!/usr/bin/env python3
"""geos_retain.py — Operator CLI over archive retention (Glyph OS spine, SPINE-R2-WIREIN).

Built on tools.geos_archive (ArchiveRecord, RetentionPolicy, Eviction,
retention_plan, ArchiveStore) and tools.geos_registry.

Flags:
  --plan            Write a retention plan to disk and delete nothing.
  --apply           Apply retention by deleting evicted files (idempotent).
  --plan-file FILE  Path to write/read retention plan JSON file.
  --keep-last N     Keep at most N newest records globally (keep_total=N).
  --max-bytes B     Cap total retained archive size in bytes.
  --tag-exclude T   Evict records carrying tag T (repeatable or comma-separated).
  --archive-dir DIR Target archive directory containing images and sidecars.
  --registry-path P Path to WriteRegistry index JSONL file.
  --known-writers W Comma-separated list of known writer identifiers.

Exit codes:
  0: plan/apply succeeded.
  2: refused (registry cross-reference conflict or unknown writer).
     Reason written to plan file AND stderr; nothing is deleted.
  1: internal error.

Default is inert:
  --apply with no policy flag evicts nothing and says so.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.geos_archive import (
    ArchiveRecord,
    ArchiveStore,
    Eviction,
    RetentionPolicy,
)
from tools.geos_registry import RegistryEntry, WriteRegistry


def load_registry(index_path: str) -> WriteRegistry:
    """Load registry entries from index_path into a WriteRegistry instance."""
    entries: List[RegistryEntry] = []
    if os.path.isfile(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if isinstance(data, dict):
                            origin_id = data.get("origin_id")
                            write_id = data.get("write_id")
                            writer = data.get("writer")
                            image_path = data.get("image_path")
                            line_sha = data.get("line_sha")
                            written_at = data.get("written_at", "")
                            if (
                                isinstance(origin_id, str)
                                and isinstance(write_id, int)
                                and isinstance(writer, str)
                                and isinstance(image_path, str)
                                and isinstance(line_sha, str)
                            ):
                                entries.append(
                                    RegistryEntry(
                                        origin_id=origin_id,
                                        write_id=write_id,
                                        writer=writer,
                                        image_path=image_path,
                                        line_sha=line_sha,
                                        written_at=str(written_at or ""),
                                    )
                                )
                    except Exception:
                        continue
        except Exception:
            pass
    return WriteRegistry(index_path=index_path, entries=entries)


def check_refusal(
    store: ArchiveStore,
    evictions: Sequence[Eviction],
    known_writers: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Check if any eviction in the plan triggers refusal.

    Refusal triggers if:
    1. An eviction causes a registry cross-reference conflict (_registry_refusal).
    2. An eviction has an unknown or unattributed writer.
    """
    # 1. Check registry cross-reference conflict
    registry_refusal = store._registry_refusal(evictions)
    if registry_refusal:
        return registry_refusal

    # 2. Check unknown / unattributed writer
    for ev in evictions:
        writer = ev.record.writer
        if not writer or writer in ("unattributed", "unknown"):
            return (
                f"refusing to compact: record {ev.record.image_path} "
                f"has unknown/unattributed writer {writer!r}"
            )
        if known_writers is not None and writer not in known_writers:
            return (
                f"refusing to compact: record {ev.record.image_path} "
                f"has unknown writer {writer!r} (not in known writers)"
            )

    return None


def write_plan_file(
    plan_file: Union[str, Path],
    status: str,
    evictions: Sequence[Eviction],
    reason: Optional[str] = None,
) -> None:
    """Write plan data to plan_file in canonical JSON format."""
    plan_data: Dict[str, Any] = {
        "status": status,
        "reason": reason,
        "evictions": [
            {
                "write_id": e.record.write_id,
                "writer": e.record.writer,
                "image_path": e.record.image_path,
                "sidecar_path": e.record.sidecar_path,
                "bytes_len": e.record.bytes_len,
                "reason": e.reason,
            }
            for e in evictions
        ],
    }
    p = Path(plan_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2, sort_keys=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entrypoint. Returns exit code 0, 1, or 2."""
    parser = argparse.ArgumentParser(
        description="geos_retain — Operator CLI over archive retention."
    )
    parser.add_argument(
        "pos_archive_dir",
        nargs="?",
        default=None,
        help="Archive directory (positional fallback)",
    )
    parser.add_argument(
        "--archive-dir",
        dest="archive_dir",
        default=None,
        help="Archive directory containing images and sidecars",
    )
    parser.add_argument(
        "--registry-path",
        dest="registry_path",
        default=None,
        help="Path to WriteRegistry index JSONL file",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Generate and write a retention plan without deleting files",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply retention by deleting evicted files (idempotent)",
    )
    parser.add_argument(
        "--plan-file",
        dest="plan_file",
        default=None,
        help="Path to retention plan JSON file",
    )
    parser.add_argument(
        "--keep-last",
        dest="keep_last",
        type=int,
        default=None,
        help="Keep at most N newest records (keep_total=N)",
    )
    parser.add_argument(
        "--max-bytes",
        dest="max_bytes",
        type=int,
        default=0,
        help="Cap total retained archive size in bytes",
    )
    parser.add_argument(
        "--tag-exclude",
        dest="tag_exclude",
        action="append",
        default=[],
        help="Exclude records carrying this tag (repeatable or comma-separated)",
    )
    parser.add_argument(
        "--known-writers",
        dest="known_writers",
        default=None,
        help="Comma-separated list of known writers",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        archive_dir_str = (
            args.archive_dir
            or args.pos_archive_dir
            or os.environ.get("GEOS_ARCHIVE_DIR")
        )
        if not archive_dir_str:
            sys.stderr.write(
                "Error: archive directory must be specified via --archive-dir or positional argument.\n"
            )
            return 1

        archive_path = Path(archive_dir_str)
        if not archive_path.exists():
            sys.stderr.write(
                f"Error: archive directory does not exist: {archive_dir_str}\n"
            )
            return 1

        if not args.plan and not args.apply:
            sys.stderr.write("Error: either --plan or --apply must be specified.\n")
            return 1

        # Flatten tag excludes
        tags: List[str] = []
        for item in args.tag_exclude:
            if isinstance(item, str):
                for sub in item.split(","):
                    s = sub.strip()
                    if s:
                        tags.append(s)

        known_writers_list: Optional[List[str]] = None
        if args.known_writers:
            known_writers_list = [
                w.strip() for w in args.known_writers.split(",") if w.strip()
            ]

        has_policy = (
            args.keep_last is not None
            or args.max_bytes > 0
            or len(tags) > 0
        )

        plan_file = (
            Path(args.plan_file)
            if args.plan_file
            else archive_path / "retention_plan.json"
        )

        # Default is inert: --apply with no policy flags evicts nothing
        if args.apply and not has_policy and not (args.plan_file and Path(args.plan_file).is_file()):
            print("Default is inert: --apply with no policy flags evicts nothing.")
            return 0

        # Load registry
        reg_path_str = (
            args.registry_path
            or os.environ.get("GEOS_REGISTRY_PATH", "/tmp/glyph_spine_index.jsonl")
        )
        reg = load_registry(reg_path_str)
        store = ArchiveStore(archive_dir=str(archive_path), registry=reg)

        # Compute plan or load existing plan
        if has_policy or not (args.plan_file and Path(args.plan_file).is_file()):
            policy = RetentionPolicy(
                keep_total=args.keep_last,
                max_bytes=args.max_bytes,
                exclude_tags=tuple(tags),
            )
            evictions = store.plan(policy)
        else:
            plan_content = json.loads(Path(args.plan_file).read_text())
            if plan_content.get("status") == "refused":
                refusal_msg = plan_content.get("reason", "pre-existing plan refusal")
                sys.stderr.write(f"REFUSAL: {refusal_msg}\n")
                return 2
            evictions = [
                Eviction(
                    record=ArchiveRecord(
                        write_id=int(e["write_id"]),
                        writer=str(e["writer"]),
                        image_path=str(e["image_path"]),
                        sidecar_path=str(e["sidecar_path"]),
                        bytes_len=int(e.get("bytes_len", 0)),
                    ),
                    reason=str(e.get("reason", "planned")),
                )
                for e in plan_content.get("evictions", [])
            ]

        # Check refusal before any filesystem modification
        refusal = check_refusal(store, evictions, known_writers=known_writers_list)
        if refusal is not None:
            write_plan_file(
                plan_file, status="refused", evictions=evictions, reason=refusal
            )
            sys.stderr.write(f"REFUSAL: {refusal}\n")
            sys.stderr.flush()
            return 2

        if args.plan and not args.apply:
            write_plan_file(plan_file, status="ok", evictions=evictions)
            print(f"Plan written to {plan_file} ({len(evictions)} evictions planned).")
            return 0

        if args.apply:
            write_plan_file(plan_file, status="ok", evictions=evictions)
            compact_res = store.compact(evictions)
            print(
                f"Applied retention: {compact_res['deleted']} files deleted, "
                f"{compact_res['bytes']} bytes reclaimed."
            )
            return 0

        return 0

    except Exception as exc:
        if isinstance(exc, ValueError) and "refusing to compact" in str(exc):
            sys.stderr.write(f"REFUSAL: {exc}\n")
            sys.stderr.flush()
            return 2
        sys.stderr.write(f"Internal error: {type(exc).__name__}: {exc}\n")
        sys.stderr.flush()
        return 1


if __name__ == "__main__":
    sys.exit(main())

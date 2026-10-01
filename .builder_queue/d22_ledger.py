#!/usr/bin/env python3
"""Single append and recompute tool for DEFECT-22 ledger.

Usage:
  python3 .builder_queue/d22_ledger.py append --leg N --seed S --head H --crashes C --oom-kill-delta D --mem-peak B --verdict green|red [--note "..."]
  python3 .builder_queue/d22_ledger.py recompute [--ledger PATH]
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

DEFAULT_LEDGER_PATH = ".builder_queue/DEFECT-22_arc_legA_instability.json"


def parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO-8601 timestamp string. Refuse unparseable format."""
    try:
        return datetime.fromisoformat(ts_str)
    except Exception as e:
        raise ValueError(f"Unparseable ISO-8601 timestamp: {ts_str!r}") from e


def extract_result_objects(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract machine-readable result objects from ledger dictionary."""
    results = []
    for k, v in data.items():
        if isinstance(v, dict) and "verdict" in v and "leg" in v:
            results.append(v)
    results.sort(key=lambda x: int(x["leg"]))
    return results


def compute_derived_series_state(
    data: Dict[str, Any],
    fallback_updated: Optional[str] = None,
) -> Dict[str, Any]:
    """Derive series_state fields by counting result objects' verdict fields."""
    result_objects = extract_result_objects(data)
    legs_run = len(result_objects)

    consecutive_green = 0
    for obj in reversed(result_objects):
        if obj.get("verdict") == "green":
            consecutive_green += 1
        else:
            break

    last_red = data.get("series_state", {}).get("last_red", "pre-worker-scope (see earlier ledger)")
    for obj in reversed(result_objects):
        if obj.get("verdict") == "red":
            last_red = f"leg{obj['leg']}"
            break

    if result_objects and "ts" in result_objects[-1]:
        updated = result_objects[-1]["ts"]
    elif fallback_updated:
        updated = fallback_updated
    else:
        existing_updated = data.get("series_state", {}).get("updated")
        if existing_updated:
            try:
                parse_timestamp(existing_updated)
                updated = existing_updated
            except Exception:
                updated = datetime.now(timezone.utc).isoformat()
        else:
            updated = datetime.now(timezone.utc).isoformat()

    return {
        "legs_run": legs_run,
        "consecutive_worker_scope_green": consecutive_green,
        "last_red": last_red,
        "updated": updated,
    }


def recompute_ledger(ledger_path: str) -> Dict[str, Any]:
    """Recompute series_state in the given ledger file."""
    path = Path(ledger_path)
    if not path.exists():
        raise FileNotFoundError(f"Ledger file not found: {ledger_path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data["series_state"] = compute_derived_series_state(data)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return data["series_state"]


def append_leg(
    ledger_path: str,
    leg: int,
    seed: Any,
    head: str,
    crashes: int,
    oom_kill_delta: int,
    mem_peak: int,
    verdict: str,
    note: Optional[str] = None,
    ts: Optional[str] = None,
) -> Dict[str, Any]:
    """Append a machine-readable leg entry to the ledger."""
    # (1) Validate verdict
    if verdict not in ("green", "red"):
        raise ValueError(f"Verdict must be 'green' or 'red', got: {verdict!r}")

    # (2) Validate timestamp
    if ts is not None:
        parsed_dt = parse_timestamp(ts)
        ts_str = ts
    else:
        parsed_dt = datetime.now(timezone.utc)
        ts_str = parsed_dt.isoformat()

    # (3) Read ledger (read-only before checks)
    path = Path(ledger_path)
    if not path.exists():
        raise FileNotFoundError(f"Ledger file not found: {ledger_path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # (4) Idempotence check
    key = f"ledger_leg{leg}"
    if key in data:
        raise ValueError(f"Leg {leg} already present under key {key!r}")

    for k, v in data.items():
        if isinstance(v, dict) and v.get("leg") == leg:
            raise ValueError(f"Leg {leg} already present in {k!r}")

    # (5) Timestamp consistency check with prior result objects
    result_objects = extract_result_objects(data)
    if result_objects:
        last_obj = result_objects[-1]
        if "ts" in last_obj:
            try:
                last_dt = parse_timestamp(last_obj["ts"])
                if (parsed_dt.tzinfo is None) == (last_dt.tzinfo is None):
                    if parsed_dt < last_dt:
                        raise ValueError(
                            f"Inconsistent timestamp: {ts_str} is earlier than previous leg ({last_obj['ts']})"
                        )
            except ValueError:
                raise
            except Exception:
                pass

    # (6) Build machine-readable entry object (dict)
    entry = {
        "ts": ts_str,
        "leg": int(leg),
        "seed": int(seed) if str(seed).isdigit() else seed,
        "head": str(head),
        "crashes": int(crashes),
        "oom_kill_delta": int(oom_kill_delta),
        "mem_peak": int(mem_peak),
        "verdict": verdict,
    }
    if note is not None:
        entry["note"] = note

    data[key] = entry
    data["series_state"] = compute_derived_series_state(data, fallback_updated=ts_str)

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return entry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DEFECT-22 ledger manager")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # append subcommand
    p_append = subparsers.add_parser("append", help="Append a leg result to the ledger")
    p_append.add_argument("--leg", type=int, required=True, help="Leg number")
    p_append.add_argument("--seed", required=True, help="Random seed used for leg")
    p_append.add_argument("--head", required=True, help="Git commit head")
    p_append.add_argument("--crashes", type=int, required=True, help="Crash count")
    p_append.add_argument("--oom-kill-delta", type=int, required=True, help="OOM kill delta count")
    p_append.add_argument("--mem-peak", type=int, required=True, help="Memory peak in bytes")
    p_append.add_argument("--verdict", choices=["green", "red"], required=True, help="Verdict: green or red")
    p_append.add_argument("--note", type=str, default=None, help="Optional explanatory note")
    p_append.add_argument("--ts", "--timestamp", dest="ts", type=str, default=None, help="ISO-8601 timestamp")
    p_append.add_argument("--ledger", type=str, default=DEFAULT_LEDGER_PATH, help="Path to ledger JSON file")

    # recompute subcommand
    p_recompute = subparsers.add_parser("recompute", help="Rebuild derived streak fields from result objects")
    p_recompute.add_argument("--ledger", type=str, default=DEFAULT_LEDGER_PATH, help="Path to ledger JSON file")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.subcommand == "append":
            entry = append_leg(
                ledger_path=args.ledger,
                leg=args.leg,
                seed=args.seed,
                head=args.head,
                crashes=args.crashes,
                oom_kill_delta=args.oom_kill_delta,
                mem_peak=args.mem_peak,
                verdict=args.verdict,
                note=args.note,
                ts=args.ts,
            )
            print(f"appended ledger_leg{args.leg} -> verdict {entry['verdict']}")
            return 0

        elif args.subcommand == "recompute":
            state = recompute_ledger(args.ledger)
            print(
                f"recomputed -> legs_run {state['legs_run']} "
                f"consecutive_worker_scope_green {state['consecutive_worker_scope_green']}"
            )
            return 0

    except Exception as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

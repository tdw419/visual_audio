#!/usr/bin/env python3
"""
directive_executor.py -- Executes governance directives by invoking structures.

Reads governance logs, matches directives to structures, and invokes them
with va_container.py run, passing directive parameters.

This turns spatial governance from logging to actual execution.
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container


def parse_directive_target(log_name: str) -> tuple[str | None, tuple[int, int] | None]:
    """Parse structure name and coordinates from a governance log name.

    Example: governance_village_center_1786712687117335
             governance_ai_council_1786712687512201
    Returns: (structure_type, (x, y)) or (None, None) if unparseable
    """
    # Remove "governance_" prefix and timestamp suffix
    if not log_name.startswith("governance_"):
        return None, None

    inner = log_name[len("governance_"):]
    # Find timestamp (large number at end)
    parts = inner.rsplit("_", 1)
    if len(parts) != 2:
        return None, None

    name_part, _ = parts[0], parts[1]

    # Check if structure name has coordinates
    if "_" not in name_part:
        return name_part, None

    # Split into name and coordinate parts
    # Example: "village_center_8_8" -> ("village_center", (8, 8))
    coord_parts = name_part.rsplit("_", 2)
    if len(coord_parts) == 3:
        try:
            x, y = int(coord_parts[1]), int(coord_parts[2])
            return coord_parts[0], (x, y)
        except ValueError:
            pass

    # No coordinates found
    return name_part, None


def get_handler_for_structure(structure_type: str) -> str | None:
    """Map structure types to their handler scripts."""
    handlers = {
        "village_center": "tools/village_center_handler.py",
        "ai_council": "tools/ai_council_handler.py",
        "codec_adapter": None,  # Not implemented yet
        "cognitive_payload": None,  # Not implemented yet
        "neural_synthesis": None,  # Not implemented yet
        "flow_meter": None,  # Not implemented yet
    }

    return handlers.get(structure_type)


def execute_directive(container: Container, directive: Dict) -> bool:
    """Execute a governance directive by invoking the structure's handler."""
    target = directive.get("target")
    if not target:
        print(f"  ✗ No target in directive")
        return False

    # Parse structure type and coordinates from target
    # Example: "ai_council.py.2_7" -> ("ai_council", (2, 7))
    if "." not in target:
        print(f"  ✗ Cannot parse target: {target}")
        return False

    # Split off coordinate part
    coord_parts = target.rsplit(".", 1)
    if len(coord_parts) != 2:
        print(f"  ✗ Cannot parse target: {target}")
        return False

    name_part, coord_str = coord_parts
    coord_str = coord_str.replace(".py", "").replace(".json", "")

    # Try to parse coordinates
    try:
        x_str, y_str = coord_str.split("_")
        x, y = int(x_str), int(y_str)
    except ValueError:
        print(f"  ✗ Cannot parse coordinates from: {coord_str}")
        return False

    # Extract structure type (remove file extension)
    structure_type = name_part.replace(".py", "").replace(".json", "")

    handler = get_handler_for_structure(structure_type)
    if not handler:
        print(f"  ✗ No handler for structure type: {structure_type}")
        return False

    # Check if handler exists in container
    try:
        container.read(handler)
    except KeyError:
        print(f"  ✗ Handler not in container: {handler}")
        return False

    print(f"\n  Executing: {directive.get('action')} on {structure_type} at ({x}, {y})")

    # Invoke handler via va_container.py run, passing coordinates
    cmd = [
        sys.executable,
        "tools/va_container.py",
        "run",
        container.mkv_path if hasattr(container, "mkv_path") else "visual_audio.mkv",
        handler,
        "--directives",
        "--x", str(x),
        "--y", str(y)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        print(result.stdout)
        if result.stderr:
            print(f"  stderr: {result.stderr}")

        if result.returncode == 0:
            print(f"  ✓ Directive executed successfully")
            return True
        else:
            print(f"  ✗ Handler returned {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ✗ Handler timed out")
        return False
    except Exception as e:
        print(f"  ✗ Execution failed: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Execute governance directives")
    parser.add_argument("--container", default="visual_audio.mkv",
                       help="Container path")
    parser.add_argument("--all", action="store_true",
                       help="Execute all pending directives")
    parser.add_argument("--recent", type=int, default=10,
                       help="Execute N most recent directives")
    args = parser.parse_args()

    print("=== Directive Executor ===")

    with Container(args.container) as c:
        # Read governance logs
        gov_logs = c.list(filter_role="governance")

        if args.all:
            target_logs = gov_logs
        elif args.recent:
            target_logs = gov_logs[-args.recent:]
        else:
            target_logs = gov_logs[-10:]  # Default: last 10

        print(f"Found {len(gov_logs)} governance logs total")
        print(f"Targeting {len(target_logs)} for execution\n")

        executed = 0
        skipped = 0
        failed = 0

        for e in target_logs:
            # Check if this is a directive log (not a report/vote/etc)
            if "governance_" in e["name"] and "_log_" not in e["name"] and "vote_" not in e["name"]:
                try:
                    directive = json.loads(c.read_text(e["name"]))

                    # Check if already executed (look for corresponding report)
                    # Skip if we've already executed directives for this structure
                    # Simple heuristic: if we executed one for this structure type, skip others
                    # (in real system, would track execution state)

                    if execute_directive(c, directive):
                        executed += 1
                    else:
                        failed += 1

                except Exception as exc:
                    print(f"  ✗ Failed to process {e['name']}: {exc}")
                    failed += 1
            else:
                skipped += 1

        print(f"\n=== Execution Summary ===")
        print(f"Executed: {executed}")
        print(f"Skipped: {skipped}")
        print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
autonomous_seeder.py -- Autonomous faction expansion directive seeder.

Periodically issues build directives toward unclaimed frontier for each
faction. This is the "brain" that makes factions "play themselves" rather
than waiting for manual directive injection.

The seeder respects the cascade lock system (try_start_cascade), avoids
duplicate work, and stops when any faction reaches 51% victory threshold.

Usage:
    python3 tools/autonomous_seeder.py visual_audio.mkv [--once] [--interval 30]
"""

import json
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container
import faction_tracker

MAP_SIZE = 256
VICTORY_THRESHOLD = 0.51


def find_frontier_tile(state: Dict, faction: str, container: Container) -> Optional[Tuple[int, int]]:
    """Find an unclaimed tile near this faction's territory.

    Strategy:
    1. Look for empty tiles within a small radius (expansion)
    2. Bias toward directions with fewer existing structures (spread)
    3. Prefer tiles the faction's attention can reach efficiently

    Returns: (x, y) or None if no frontier found (map full or faction boxed in)
    """
    f = state["factions"][faction]
    ax, ay = f["attention_x"], f["attention_y"]

    # Get all occupied tiles from all faction structures
    occupied = set()
    for fac, fac_data in state["factions"].items():
        for struct in fac_data["structures"]:
            # Parse coordinate from structure name (e.g. "utility_shed.12_34")
            if "." in struct:
                try:
                    coord_str = struct.rsplit(".", 1)[1]
                    x_str, y_str = coord_str.split("_")
                    x, y = int(x_str), int(y_str)
                    occupied.add((x, y))
                except (ValueError, IndexError):
                    continue

    # Search radius - start small, expand if nothing found
    for radius in range(2, 20):
        candidates = []

        # Search in a ring around current attention position
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if abs(dx) == radius or abs(dy) == radius:  # Ring boundary
                    x, y = ax + dx, ay + dy

                    # Bounds check
                    if x < 0 or x >= MAP_SIZE or y < 0 or y >= MAP_SIZE:
                        continue

                    # Must be unclaimed
                    if (x, y) in occupied:
                        continue

                    # Calculate "goodness" score
                    score = 0

                    # Prefer tiles that don't race other factions
                    for other_fac, other_f in state["factions"].items():
                        if other_fac == faction:
                            continue
                        ox, oy = other_f["attention_x"], other_f["attention_y"]
                        dist_to_other = max(abs(x - ox), abs(y - oy))
                        if dist_to_other < 8:  # Too close to enemy
                            score -= 10

                    # Prefer expansion into open space
                    score -= max(abs(dx), abs(dy))  # Closer is better

                    # Add randomness to avoid getting stuck
                    score += random.uniform(-2, 2)

                    candidates.append((score, (x, y)))

        if candidates:
            # Pick best candidate
            candidates.sort(key=lambda t: t[0], reverse=True)
            return candidates[0][1]

    return None  # No frontier found


def has_pending_build(container: Container, faction: str, faction_state: Dict) -> bool:
    """Check if this faction already has a pending build directive in governance logs.

    This prevents issuing duplicate directives when the seeder runs repeatedly.
    """
    f = faction_state["factions"][faction]

    # Look for any governance log with this faction's village center as issuer/target
    all_gov = container.list(filter_role="governance")

    for e in all_gov[-50:]:  # Check recent logs
        try:
            content = json.loads(container.read_text(e["name"]))
            if content.get("consumed"):
                continue

            # Check if this is a build directive targeting this faction's village center
            target = content.get("target", "")
            if f"village_center.py.{f['home_x']}_{f['home_y']}" in target:
                if content.get("action") == "build":
                    return True
        except Exception:
            continue

    return False


def check_game_over(state: Dict) -> Optional[str]:
    """Check if any faction has reached victory threshold.

    Returns winning faction name or None if game continues.
    """
    for faction, f_data in state["factions"].items():
        structures = len(f_data["structures"])
        required = int(MAP_SIZE * MAP_SIZE * VICTORY_THRESHOLD)
        if structures >= required:
            return faction
    return None


def seed_directives(container: Container, state: Dict, dry_run: bool = False) -> Dict[str, int]:
    """Issue build directives for each faction toward frontier.

    Returns: {"directives_issued": N, "skipped_locked": M, "no_frontier": P}
    """
    results = {
        "directives_issued": 0,
        "skipped_locked": 0,
        "no_frontier": 0,
        "already_pending": 0,
    }

    print(f"=== Autonomous Seeder Pass ===")
    print(f"Factions: {list(state['factions'].keys())}")

    for faction in state["factions"]:
        f = state["factions"][faction]
        print(f"\n  [{faction}]")

        # Skip if already has pending build
        if has_pending_build(container, faction, state):
            print(f"    • Already has pending build directive")
            results["already_pending"] += 1
            continue

        # Find frontier target
        target = find_frontier_tile(state, faction, container)
        if target is None:
            print(f"    • No frontier available (boxed in or map full)")
            results["no_frontier"] += 1
            continue

        tx, ty = target

        # Try to claim cascade lock
        if not faction_tracker.try_start_cascade(state, faction, tx, ty):
            print(f"    • Cascade lock active, skipping")
            results["skipped_locked"] += 1
            continue

        # CRITICAL: persist the claim before issuing directive
        faction_tracker.save_factions(container, state)

        if dry_run:
            print(f"    • [DRY-RUN] Would issue build directive to ({tx}, {ty})")
        else:
            # Issue build directive to this faction's village center
            village_target = f"village_center.py.{f['home_x']}_{f['home_y']}"

            build_params = {
                "x": tx,
                "y": ty,
                "type": "utility_shed",  # Could vary by strategy
            }

            # Reuse village_center's issue_directive pattern
            directive = {
                "issuer": f"autonomous_seeder_{faction}",
                "target": village_target,
                "action": "build",
                "params": build_params,
                "timestamp": time.time(),
            }

            log_name = f"governance_autonomous_seeder_{faction}_{int(directive['timestamp']*1000)}"
            container.add(
                log_name,
                json.dumps(directive, indent=2).encode(),
                role="governance",
                note=f"Autonomous expansion directive for {faction}"
            )

            print(f"    • Issued build directive to ({tx}, {ty})")
            results["directives_issued"] += 1

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Autonomous faction expansion seeder")
    parser.add_argument("container", help="Container path (visual_audio.mkv)")
    parser.add_argument("--once", action="store_true",
                       help="Run once and exit")
    parser.add_argument("--interval", type=int, default=30,
                       help="Seconds between seeder passes (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without issuing directives")
    args = parser.parse_args()

    print("=== Autonomous Faction Seeder ===")
    print(f"Container: {args.container}")
    print(f"Interval: {args.interval}s")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")

    with Container(args.container) as c:
        pass_count = 0

        while True:
            pass_count += 1
            print(f"\n{'='*60}")
            print(f"PASS #{pass_count} at {time.strftime('%H:%M:%S')}")
            print(f"{'='*60}")

            # Load current state
            with Container(args.container) as c:
                state = faction_tracker.load_factions(c)

                if state is None:
                    print("No faction game in progress (faction_state not found)")
                    break

                # Check for victory
                winner = check_game_over(state)
                if winner:
                    print(f"\n🎊 GAME OVER: {winner.upper()} REACHED VICTORY! 🎊\n")
                    break

                # Seed directives
                results = seed_directives(c, state, dry_run=args.dry_run)

                print(f"\n  Pass results:")
                print(f"    Directives issued: {results['directives_issued']}")
                print(f"    Already pending: {results['already_pending']}")
                print(f"    Skipped (cascade locked): {results['skipped_locked']}")
                print(f"    No frontier: {results['no_frontier']}")

                # Show current territory
                print(f"\n  Territory status:")
                for faction, f_data in state["factions"].items():
                    structures = len(f_data["structures"])
                    pct = structures / (MAP_SIZE * MAP_SIZE)
                    print(f"    {faction}: {structures:,} tiles ({pct:.2%})")

            if args.once:
                print("\n--once flag: exiting after single pass")
                break

            print(f"\nSleeping {args.interval}s until next pass...")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
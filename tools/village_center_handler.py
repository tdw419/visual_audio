#!/usr/bin/env python3
"""
village_center.py -- Autonomous coordination hub for local structures.

When this structure receives governance directives, it executes them:
- coordinate: Calls status() on all structures in its biome
- build: Places new structure at specified location
- report: Writes governance report to spatial memory

Usage (from container):
    va_container.py run visual_audio.mkv tools/village_center.py --directives
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container
import faction_tracker


def find_local_structures(container: Container, my_x: int, my_y: int, radius: int = 4) -> List[Dict]:
    """Find all architecture structures within radius of this village center."""
    all_arch = container.list(filter_role="architecture")
    local = []

    for e in all_arch:
        # Parse coordinate from name
        if "." in e["name"]:
            parts = e["name"].rsplit(".", 1)
            coord_str = parts[1] if len(parts) > 1 else ""
        else:
            continue

        try:
            x_str, y_str = coord_str.split("_")
            x, y = int(x_str), int(y_str)
        except (ValueError, AttributeError):
            continue

        # Calculate distance
        dist = max(abs(x - my_x), abs(y - my_y))  # Manhattan distance
        if dist <= radius and (x, y) != (my_x, my_y):
            local.append({
                "name": e["name"],
                "x": x,
                "y": y,
                "distance": dist,
                "size": e["length"],
            })

    return local


def read_governance_directives(container: Container, my_x: int, my_y: int) -> List[Tuple[str, Dict]]:
    """Read unconsumed governance directives addressed to this village center.

    Returns (entry_name, content) pairs so callers can mark them consumed
    after execution -- without this, re-running the executor (e.g. in a
    scheduled loop) re-triggers every directive ever logged for this
    structure from scratch every time.
    """
    all_gov = container.list(filter_role="governance")
    directives = []

    for e in all_gov:
        # Read directive content
        try:
            content = json.loads(container.read_text(e["name"]))
        except Exception:
            continue

        if content.get("consumed"):
            continue

        # Check if directive targets this structure
        target = content.get("target", "")
        if f"village_center.py.{my_x}_{my_y}" in target or f"village_center_{my_x}_{my_y}" in target:
            if content.get("action") in ("coordinate", "build", "move_attention"):
                directives.append((e["name"], content))

    return directives


def mark_consumed(container: Container, name: str, content: Dict) -> None:
    """Mark a directive as executed so it won't be re-run on future passes."""
    content = dict(content)
    content["consumed"] = True
    content["consumed_at"] = time.time()
    container.update(name, json.dumps(content, indent=2).encode())

def issue_directive(container: Container, issuer_name: str, target: str, action: str, params: Dict):
    """Issue a new governance directive (cascading governance)."""
    directive = {
        "issuer": issuer_name,
        "target": target,
        "action": action,
        "params": params,
        "timestamp": __import__("time").time()
    }
    
    log_name = f"governance_{issuer_name}_{int(directive['timestamp']*1000)}"
    container.add(
        log_name,
        json.dumps(directive, indent=2).encode(),
        role="governance",
        note=f"Cascading directive issued by {issuer_name}"
    )
    print(f"    -> Issued cascading directive: {action} to {target}")


def execute_coordinate(container: Container, my_x: int, my_y: int) -> Dict:
    """Execute a coordinate directive: gather status from local structures."""
    print(f"  [village_center] Coordinating structures around ({my_x}, {my_y})...")

    local_structures = find_local_structures(container, my_x, my_y)
    print(f"    Found {len(local_structures)} local structures")

    # Simulate gathering status
    status_report = {
        "center": {"x": my_x, "y": my_y},
        "structures": [],
        "timestamp": __import__("time").time(),
    }

    for s in local_structures:
        # In real system, would invoke each structure's status() method
        # For now, simulate by reading their metadata
        status_report["structures"].append({
            "name": s["name"],
            "distance": s["distance"],
            "size": s["size"],
            "status": "active" if s["size"] > 100 else "idle",
        })

    # Write report to governance log
    report_name = f"coordination_report_{my_x}_{my_y}_{int(status_report['timestamp'])}"
    container.add(
        report_name,
        json.dumps(status_report, indent=2).encode(),
        role="governance",
        note=f"Coordination report from village center at ({my_x}, {my_y})"
    )

    # Cascading Governance: if local structures < 10, issue a build directive
    if len(local_structures) < 10:
        print(f"    [village_center] Infrastructure below optimal threshold ({len(local_structures)}). Issuing build directive.")
        issue_directive(
            container,
            f"village_center_{my_x}_{my_y}",
            f"village_center.py.{my_x}_{my_y}",
            "build",
            {"x": my_x + len(local_structures) + 1, "y": my_y + (len(local_structures) % 2), "type": "utility_shed"}
        )

    return status_report


def execute_build(container: Container, my_x: int, my_y: int, build_params: Dict) -> bool:
    """Execute a build directive: place new structure at specified location."""
    print(f"  [village_center] Building new structure...")

    # Parse build parameters
    target_x = build_params.get("x", my_x + 1)
    target_y = build_params.get("y", my_y)
    structure_type = build_params.get("type", "utility_shed")

    # Entropy War proximity guard: if a faction game is in progress and this
    # village center belongs to a faction, its build must be within
    # claim-radius of that faction's *attention* position, not just
    # possible from its home coordinates -- see [[faction_tracker.py]].
    # No faction_state entry at all means the game isn't in progress, so
    # this is a no-op and build works exactly as it did before.
    state = faction_tracker.load_factions(container)
    if state is not None:
        faction = faction_tracker.faction_at(state, my_x, my_y)
        if faction is not None:
            # Check if we own the cascade lock
            if not faction_tracker.try_start_cascade(state, faction, target_x, target_y):
                print(f"    [village_center] Another cascade active. Re-queueing build unmoved.")
                issue_directive(container, f"village_center_{my_x}_{my_y}", f"village_center.py.{my_x}_{my_y}", "build", build_params)
                return False

            # CRITICAL: persist the claim immediately. try_start_cascade only
            # mutates `state` in memory -- without saving here, every branch
            # below that returns without its own save_factions() call
            # silently drops the claim, and the next execute_build() call
            # reloads a fresh state showing no active cascade at all. That
            # was a real, reproduced regression (2026-08-14): it resurrected
            # the exact livelock the lock exists to prevent, byte-for-byte
            # (opposing targets oscillating 0->4->0->4 forever). See
            # [[entropy-war-game-design]].
            faction_tracker.save_factions(container, state)

            f = state["factions"][faction]
            dist = faction_tracker.chebyshev(f["attention_x"], f["attention_y"], target_x, target_y)
            if dist > faction_tracker.DEFAULT_CLAIM_RADIUS:
                print(f"    ✗ too_far: {faction}'s attention is at "
                      f"({f['attention_x']}, {f['attention_y']}), "
                      f"{dist} tiles from target ({target_x}, {target_y}) -- "
                      f"move_attention there first")
                
                # Autonomous Cascade: Move attention and retry build
                print(f"    [village_center] Cascading move_attention to ({target_x}, {target_y}) and re-queueing build.")
                issue_directive(
                    container,
                    f"village_center_{my_x}_{my_y}",
                    f"village_center.py.{my_x}_{my_y}",
                    "move_attention",
                    {"target_x": target_x, "target_y": target_y}
                )
                issue_directive(
                    container,
                    f"village_center_{my_x}_{my_y}",
                    f"village_center.py.{my_x}_{my_y}",
                    "build",
                    build_params
                )
                return False

            # Clash Resolution Check
            contesting = []
            for other_fac, other_f in state["factions"].items():
                if other_fac != faction:
                    other_dist = faction_tracker.chebyshev(other_f["attention_x"], other_f["attention_y"], target_x, target_y)
                    if other_dist <= faction_tracker.DEFAULT_CLAIM_RADIUS:
                        contesting.append(other_fac)
            
            if contesting:
                topic = f"Territory_Claim_{target_x}_{target_y}_by_{faction}"
                resolved = False
                all_gov = container.list(filter_role="governance")
                for e in all_gov[-40:]:
                    if "debate_log_" in e["name"]:
                        try:
                            d_log = json.loads(container.read_text(e["name"]))
                            if d_log.get("topic") != topic:
                                continue
                            # A deferred debate (ai_council's own bounded
                            # cascade gave up -- radius exhaustion or its
                            # 5-attempt cap) is a real, terminal outcome, not
                            # "not yet resolved". Treating it as still-pending
                            # meant this loop would keep issuing brand new
                            # debate directives with the same topic forever,
                            # each spawning its own fresh 5-attempt
                            # sub-cascade -- unbounded governance-log growth
                            # with no path to termination. Deferred yields
                            # the tile, same as an explicit reject: a
                            # stalemate is a resolution, not a reason to
                            # retry indefinitely.
                            terminal_status = d_log.get("terminal_status", "")
                            if terminal_status.startswith("deferred"):
                                print(f"    ✗ Clash yielded (debate deferred: {terminal_status}). Clearing cascade.")
                                faction_tracker.clear_active_cascade(state, faction, target_x, target_y)
                                faction_tracker.save_factions(container, state)
                                return False
                            if d_log.get("meets_threshold"):
                                if d_log.get("consensus") == "approve":
                                    resolved = True
                                    break
                                elif d_log.get("consensus") == "reject":
                                    print(f"    ✗ Clash lost (debate rejected). Clearing cascade.")
                                    faction_tracker.clear_active_cascade(state, faction, target_x, target_y)
                                    faction_tracker.save_factions(container, state)
                                    return False
                        except Exception:
                            pass
                
                if not resolved:
                    print(f"    [village_center] Contested frontier! Factions {contesting} in range. Routing to AI Council.")
                    
                    # Find any AI council
                    council_target = f"ai_council.py.2_7"  # Default fallback
                    all_arch = container.list(filter_role="architecture")
                    for a in all_arch:
                        if "ai_council" in a["name"]:
                            council_target = a["name"]
                            break
                            
                    issue_directive(container, f"village_center_{my_x}_{my_y}", council_target, "debate", {
                        "topic": topic, "consensus_threshold": 0.6
                    })
                    print(f"    [village_center] Re-queueing build unmoved pending debate resolution.")
                    issue_directive(container, f"village_center_{my_x}_{my_y}", f"village_center.py.{my_x}_{my_y}", "build", build_params)
                    return False

    # Check if space is empty
    target_name = f"{structure_type}.{target_x}_{target_y}"
    try:
        container.read(target_name)
        print(f"    ✗ Space already occupied at ({target_x}, {target_y})")
        return False
    except KeyError:
        pass

    # Generate structure template
    templates = {
        "utility_shed": b"#!/usr/bin/env python3\n# Shared utilities\ndef format_data(data):\n    return json.dumps(data, indent=2)",
        "watchtower": b"#!/usr/bin/env python3\n# Monitor territory\ndef scan_perimeter():\n    return {'threats': [], 'status': 'clear'}",
        "marketplace": b"#!/usr/bin/env python3\n# Resource exchange\nmarket = {'goods': [], 'offers': []}\ndef trade(item, quantity): pass",
    }

    content = templates.get(structure_type, b"# Auto-generated structure")

    # Add the structure
    container.add(
        target_name,
        content,
        role="architecture",
        note=f"Built by village_center at ({my_x}, {my_y})"
    )

    print(f"    ✓ Built {structure_type} at ({target_x}, {target_y})")

    if state is not None:
        faction = faction_tracker.faction_at(state, my_x, my_y)
        if faction is not None:
            faction_tracker.record_claim(state, faction, target_name)
            faction_tracker.clear_active_cascade(state, faction, target_x, target_y)
            faction_tracker.save_factions(container, state)

    return True


def execute_move_attention(container: Container, my_x: int, my_y: int, params: Dict) -> Dict:
    """Execute a move_attention directive: step this village center's
    faction toward a target coordinate, bounded by DEFAULT_STEP per turn."""
    target_x = params.get("target_x")
    target_y = params.get("target_y")
    step = params.get("step", faction_tracker.DEFAULT_STEP)

    state = faction_tracker.load_factions(container)
    if state is None:
        print(f"    ✗ No faction game in progress (faction_state not initialized)")
        return {"moved": False, "reason": "no_faction_game"}

    faction = faction_tracker.faction_at(state, my_x, my_y)
    if faction is None:
        print(f"    ✗ ({my_x}, {my_y}) is not a faction seed")
        return {"moved": False, "reason": "not_a_faction_seed"}

    report = faction_tracker.move_attention(state, faction, target_x, target_y, step=step)
    faction_tracker.save_factions(container, state)

    print(f"  [village_center] {faction} attention {report['from']} -> {report['to']} "
          f"(target {report['target']}, {report['dist_after']} tiles remaining"
          f"{', ARRIVED' if report['arrived'] else ''})")
    return report


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Village center execution")
    parser.add_argument("--directives", action="store_true",
                       help="Execute all pending governance directives")
    parser.add_argument("--status", action="store_true",
                       help="Report current status")
    parser.add_argument("--x", type=int, default=None,
                       help="Village center X coordinate (auto-detected from directives if not provided)")
    parser.add_argument("--y", type=int, default=None,
                       help="Village center Y coordinate (auto-detected from directives if not provided)")
    args = parser.parse_args()

    # Read my coordinates from environment (set by va_container.py run)
    import os
    va_container = os.environ.get("VA_CONTAINER", "visual_audio.mkv")

    with Container(va_container) as c:
        # Determine my coordinates
        my_x, my_y = args.x, args.y

        # If not provided, try to detect from directives
        if my_x is None or my_y is None:
            # Look for directives targeting any village center, infer coordinates
            all_gov = c.list(filter_role="governance")
            for e in all_gov[-20:]:  # Check recent directives
                if "village_center" in e["name"]:
                    try:
                        directive = json.loads(c.read_text(e["name"]))
                        target = directive.get("target", "")
                        # Parse: "village_center.py.8_8"
                        if "village_center" in target and "_" in target:
                            coord_part = target.rsplit("_", 1)[-1]
                            if "_" in coord_part:
                                coord_part = coord_part.replace(".py", "").replace(".json", "")
                                x_str, y_str = coord_part.split("_")
                                my_x, my_y = int(x_str), int(y_str)
                                break
                    except Exception:
                        continue

        if my_x is None or my_y is None:
            my_x, my_y = 0, 0
            print(f"Warning: Could not detect coordinates, defaulting to (0, 0)")

        print(f"=== Village Center at ({my_x}, {my_y}) ===")

        if args.status:
            # Just report status
            local = find_local_structures(c, my_x, my_y)
            print(f"Local structures ({len(local)}):")
            for s in local:
                print(f"  • {s['name']} (dist={s['distance']}, size={s['size']})")

        elif args.directives:
            # Execute all pending directives
            directives = read_governance_directives(c, my_x, my_y)
            print(f"Found {len(directives)} coordination directives")

            for idx, (name, directive) in enumerate(directives):
                print(f"\n  Executing directive {idx + 1}/{len(directives)}:")

                params = directive.get("params", {})

                if directive.get("action") == "coordinate":
                    result = execute_coordinate(c, my_x, my_y)
                    print(f"    ✓ Coordination complete ({len(result['structures'])} structures)")

                elif directive.get("action") == "build":
                    success = execute_build(c, my_x, my_y, params)
                    if not success:
                        print(f"    ✗ Build failed")

                elif directive.get("action") == "move_attention":
                    execute_move_attention(c, my_x, my_y, params)

                mark_consumed(c, name, directive)

        else:
            # Default: just show local structures
            local = find_local_structures(c, my_x, my_y)
            print(f"Local structures ({len(local)}):")
            for s in local:
                print(f"  • {s['name']} (dist={s['distance']}, size={s['size']})")


if __name__ == "__main__":
    main()
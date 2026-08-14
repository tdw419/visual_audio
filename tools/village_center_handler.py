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
            if content.get("action") in ("coordinate", "build"):
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
    return True


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

                mark_consumed(c, name, directive)

        else:
            # Default: just show local structures
            local = find_local_structures(c, my_x, my_y)
            print(f"Local structures ({len(local)}):")
            for s in local:
                print(f"  • {s['name']} (dist={s['distance']}, size={s['size']})")


if __name__ == "__main__":
    main()
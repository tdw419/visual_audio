#!/usr/bin/env python3
"""
spatial_governor.py -- Autonomous governance layer for Geometry OS.

Reads placed structures from terrain and coordinates behavior between them,
implementing emergent governance through spatial awareness.

Governance primitives:
- Issue directives to structures based on their roles
- Monitor resource consumption across biomes
- Trigger cascading operations when conditions are met
- Maintain governance logs in the spatial memory
"""

import json
import sys
import time
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container


# Role-based directives
DIRECTIVE_TEMPLATES = {
    "village_center": {
        "action": "coordinate",
        "params": {"mode": "gather_status", "targets": ["post_office", "utility_shed"]},
    },
    "ai_council": {
        "action": "debate",
        "params": {"topic": "resource_allocation", "consensus_threshold": 0.7},
    },
    "codec_adapter": {
        "action": "encode_stream",
        "params": {"format": "phoneme", "quality": "high"},
    },
    "cognitive_payload": {
        "action": "activate",
        "params": {"mode": "inference", "temperature": 0.8},
    },
}


def read_structures(container: Container) -> List[Dict]:
    """Read all architecture entries and their coordinates."""
    entries = container.list(filter_role="architecture")
    structures = []

    for e in entries:
        name = e["name"]
        # Parse coordinate from name (format: "structure_name.x_y")
        if "." in name:
            parts = name.rsplit(".", 1)
            base_name = parts[0]
            coord_str = parts[1] if len(parts) > 1 else ""
        else:
            base_name = name
            coord_str = ""

        try:
            x_str, y_str = coord_str.split("_")
            x, y = int(x_str), int(y_str)
        except (ValueError, AttributeError):
            x, y = None, None

        structures.append({
            "name": base_name,
            "x": x,
            "y": y,
            "role": "architecture",
            "size": e["length"],
            "raw_name": name,
        })

    return structures


def cluster_by_biome(structures: List[Dict]) -> Dict[str, List[Dict]]:
    """Group structures by coordinate proximity (simulating biome clustering)."""
    clusters: Dict[str, List[Dict]] = {}

    for s in structures:
        if s["x"] is None or s["y"] is None:
            biome = "unknown"
        else:
            # Simple clustering based on coordinate quadrants
            quadrant = f"{s['x']//4}_{s['y']//4}"
            biome = quadrant

        if biome not in clusters:
            clusters[biome] = []
        clusters[biome].append(s)

    return clusters


def generate_directive(structure: Dict, context: Dict, directive_index: int) -> Dict:
    """Generate a governance directive for a structure based on its role and context."""
    base_name = structure["name"]

    # Find matching directive template
    for role_key, template in DIRECTIVE_TEMPLATES.items():
        if role_key in base_name:
            directive = template.copy()
            directive["target"] = structure["raw_name"]
            directive["timestamp"] = time.time() + directive_index * 0.001  # Unique timestamp per directive
            directive["governor_id"] = "spatial_governor_v1"
            return directive

    # Default directive for unknown structures
    return {
        "target": structure["raw_name"],
        "action": "report_status",
        "params": {},
        "timestamp": time.time() + directive_index * 0.001,
        "governor_id": "spatial_governor_v1",
    }


def check_cascade_conditions(clusters: Dict[str, List[Dict]]) -> List[str]:
    """Check if any governance cascades should be triggered."""
    cascades = []

    for biome, structures in clusters.items():
        # Condition 1: Multiple AI councils in same biome -> consensus vote
        ai_councils = [s for s in structures if "ai_council" in s["name"]]
        if len(ai_councils) >= 2:
            cascades.append(f"TRIGGER_CONSENSUS: {len(ai_councils)} AI councils in biome {biome}")

        # Condition 2: Village center present -> issue coordination directive
        if any("village_center" in s["name"] for s in structures):
            cascades.append(f"TRIGGER_COORDINATION: village_center active in biome {biome}")

        # Condition 3: Cognitive payload + codec adapter -> initiate synthesis pipeline
        has_cognitive = any("cognitive_payload" in s["name"] for s in structures)
        has_codec = any("codec_adapter" in s["name"] for s in structures)
        if has_cognitive and has_codec:
            cascades.append(f"TRIGGER_SYNTHESIS: cognitive+codec pair in biome {biome}")

    return cascades


def execute_directive(container: Container, directive: Dict) -> bool:
    """Simulate executing a governance directive (in real system, would invoke the target)."""
    # For now, log the directive to the container as governance output
    log_entry = json.dumps(directive, indent=2).encode()

    # Create a governance log entry with unique name (target + timestamp)
    target_stem = directive['target'].split('.')[0]  # Remove coordinate suffix
    log_name = f"governance_{target_stem}_{int(directive['timestamp'] * 1000000)}"
    try:
        container.add(
            log_name,
            log_entry,
            role="governance",
            note=f"Governance directive for {directive['target']}"
        )
        return True
    except Exception as e:
        print(f"  Failed to log directive: {e}")
        return False


def main():
    """Run the spatial governor loop."""
    mkv_path = "visual_audio.mkv"

    print("=== Spatial Governor Started ===")
    print("Reading structures and issuing governance directives...\n")

    with Container(mkv_path) as c:
        # Read all structures
        structures = read_structures(c)
        print(f"Found {len(structures)} structures")

        # Cluster by biome
        clusters = cluster_by_biome(structures)
        print(f"Identified {len(clusters)} biome clusters:")
        for biome, s_list in clusters.items():
            names = [s["name"] for s in s_list]
            print(f"  {biome}: {names}")

        # Check cascade conditions
        cascades = check_cascade_conditions(clusters)
        print(f"\nCascade conditions detected: {len(cascades)}")
        for cascade in cascades:
            print(f"  • {cascade}")

        # Issue directives to each structure
        print(f"\nIssuing directives...")
        directives_issued = 0

        for idx, structure in enumerate(structures):
            directive = generate_directive(structure, {}, idx)
            print(f"\n  Directing {structure['name']} at ({structure['x']}, {structure['y']}):")
            print(f"    Action: {directive['action']}")

            if execute_directive(c, directive):
                directives_issued += 1
                print(f"    ✓ Directive logged")

        print(f"\n=== Governance Complete ===")
        print(f"Directives issued: {directives_issued}")

        # Verify governance logs
        entries = c.list()
        governance_entries = [e for e in entries if e["role"] == "governance"]
        print(f"Governance log entries: {len(governance_entries)}")


if __name__ == "__main__":
    main()
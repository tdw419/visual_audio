#!/usr/bin/env python3
"""
city_planner_agent.py -- Autonomous spatial architecture placement agent.

Uses ASCII viewport to identify terrain biomes and places purposeful
structures onto appropriate terrain types, organizing spatial memory
semantically rather than just geographically.

Biome Semantics:
- Plains (green): General code, tools, utilities
- Mountains (gray): Data structures, databases, memory palaces
- Water (blue): Stream processing, codecs, audio pipelines
- Desert (yellow): Compute kernels, emulators, hypervisors
- Forest (dark green): AI models, neural synthesis, cognitive payloads
"""

import hashlib
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from visual_audio_container import Container
from procedural_generator import generate_tile_image


# Structure templates for different biomes
STRUCTURE_TEMPLATES = {
    "plains": [
        {"name": "village_center.py", "content": b"#!/usr/bin/env python3\n# Village center - coordination hub for local agents\ndef coordinate(local_agents):\n    return [a.status() for a in local_agents]\n"},
        {"name": "utility_shed.py", "content": b"#!/usr/bin/env python3\n# Shared utilities\ndef format_data(data):\n    return json.dumps(data, indent=2)\n"},
        {"name": "post_office.json", "content": b'{"inbox": [], "outbox": [], "status": "operational"}'},
    ],
    "mountains": [
        {"name": "data_library.db", "content": b"SQLite database for persistent storage\n<SCHEMA_PLACEHOLDER>"},
        {"name": "memory_palace.png", "content": b"PNG<placeholder> - spatial knowledge base"},
        {"name": "index_structure.json", "content": b'{"type": "spatial_index", "entries": []}'},
    ],
    "water": [
        {"name": "stream_processor.py", "content": b"#!/usr/bin/env python3\n# Audio/data stream pipeline\ndef process_stream(data):\n    return [transform(chunk) for chunk in data]\n"},
        {"name": "codec_adapter.py", "content": b"#!/usr/bin/env python3\nclass CodecAdapter:\n    def encode(self, data): pass\n    def decode(self, data): pass\n"},
        {"name": "flow_meter.py", "content": b"#!/usr/bin/env python3\n# Monitor throughput\nbytes_processed = 0"},
    ],
    "desert": [
        {"name": "kernel_core.rv32", "content": b".text\n    li a0, 42\n    ret"},
        {"name": "hypervisor_bridge.py", "content": b"#!/usr/bin/env python3\n# Bridge to guest OS\nclass HypervisorBridge:\n    def hypercall(self, op, *args): pass\n"},
        {"name": "compute_shard.py", "content": b"#!/usr/bin/env python3\n# Isolated compute unit\ndef execute_task(task):\n    return task.run()\n"},
    ],
    "forest": [
        {"name": "neural_synthesis.py", "content": b"#!/usr/bin/env python3\n# Neural TTS synthesis\nimport torch\nmodel = load_model('tinyllama')"},
        {"name": "cognitive_payload.json", "content": b'{"model": "tinyllama", "weights": [], "config": {}}'},
        {"name": "ai_council.py", "content": b"#!/usr/bin/env python3\n# Multi-agent coordination\nclass AICouncil:\n    def debate(self, topic): pass\n"},
    ],
}


def identify_biome(terrain_bytes: bytes) -> str:
    """Identify biome type from terrain tile pixel data."""
    # Analyze dominant color from tile
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(terrain_bytes))
    pixels = list(img.getdata())

    # Count color frequencies
    color_counts = {}
    for r, g, b in pixels:
        # Quantize to biome color groups
        if r > 200 and g > 200 and b > 200:
            biome = "desert"  # Light yellow/white
        elif r < 100 and g < 100 and b > 150:
            biome = "water"  # Blue
        elif r < 100 and g > 150 and b < 100:
            biome = "forest"  # Green
        elif r > 150 and g > 150 and b > 150:
            biome = "mountains"  # Gray
        else:
            biome = "plains"  # Default
        color_counts[biome] = color_counts.get(biome, 0) + 1

    # Return most common biome
    return max(color_counts.items(), key=lambda x: x[1])[0]


def find_terrain_edge(container: Container, viewport_size: int = 16) -> tuple[int, int] | None:
    """Find an edge of the known terrain where expansion is possible."""
    # Get the full directory to find all terrain coordinates
    entries = container.list()
    terrain_coords = set()
    for e in entries:
        if e["role"] == "terrain_tile" and e["name"].startswith("terrain_chunk_"):
            # Parse "terrain_chunk_X_Y" format
            parts = e["name"].replace("terrain_chunk_", "").split("_")
            if len(parts) == 2:
                try:
                    x, y = int(parts[0]), int(parts[1])
                    terrain_coords.add((x, y))
                except ValueError:
                    pass

    if not terrain_coords:
        return (0, 0)  # Start at origin

    # Find boundary tiles adjacent to empty space
    for tx, ty in terrain_coords:
        # Check all 4 neighbors
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = tx + dx, ty + dy
            if (nx, ny) not in terrain_coords:
                # Found an edge - verify it's empty via ASCII viewport
                viewport = container.get_ascii_viewport(nx - 2, ny - 2, 5, 5)
                if viewport.count('.') > 0:  # Has empty space
                    return (nx, ny)

    return None


def place_structure(container: Container, x: int, y: int) -> bool:
    """Place a structure onto terrain at (x, y)."""
    # First, read the terrain to identify biome
    terrain_name = f"terrain_chunk_{x}_{y}"
    try:
        terrain_data = container.read(terrain_name)
    except KeyError:
        # Terrain doesn't exist yet - generate it first
        SEED = 13078663007992465314
        img = generate_tile_image(SEED, x, y, tile_size=256, scale=0.01)

        # Convert to bytes
        import io
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()

        container.add(terrain_name, img_bytes, role="terrain_tile", note=f"Procedural terrain at ({x}, {y})")
        terrain_data = img_bytes

    # Identify biome
    biome = identify_biome(terrain_data)
    print(f"  Identified biome: {biome}")

    # Check if structure fits this biome
    if biome not in STRUCTURE_TEMPLATES:
        print(f"  No structures defined for {biome} biome")
        return False

    # Pick a random structure template for this biome
    template = random.choice(STRUCTURE_TEMPLATES[biome])
    structure_name = f"{template['name']}.{x}_{y}"
    structure_content = template['content']

    print(f"  Placing structure: {structure_name}")

    # Add the structure to the container
    container.add(
        structure_name,
        structure_content,
        role="architecture",
        note=f"{biome} biome structure at ({x}, {y})"
    )

    return True


def main():
    """Run the city planner agent loop."""
    mkv_path = "visual_audio.mkv"

    print("=== City Planner Agent Started ===")
    print("Scanning terrain biomes and placing architectural structures...\n")

    with Container(mkv_path) as c:
        step = 0
        structures_placed = 0

        while structures_placed < 10:  # Place 10 structures this session
            step += 1
            print(f"--- Planner Step {step} ---")

            # Find edge of known terrain
            edge_coord = find_terrain_edge(c)
            if not edge_coord:
                print("  No more expansion edges found")
                break

            x, y = edge_coord
            print(f"  Target coordinate: ({x}, {y})")

            # Get ASCII viewport for visual confirmation
            viewport = c.get_ascii_viewport(max(0, x - 2), max(0, y - 2), 5, 5)
            print(f"  Viewport before:\n{viewport.replace(chr(10), chr(10) + '    ')}")

            # Place a structure
            if place_structure(c, x, y):
                structures_placed += 1
                print(f"  ✓ Structure placed (total: {structures_placed})")

                # Verify it appeared
                viewport_after = c.get_ascii_viewport(max(0, x - 2), max(0, y - 2), 5, 5)
                if '@' in viewport_after or '{' in viewport_after:
                    print(f"  ✓ Structure visible in ASCII viewport")
                else:
                    print(f"  ⚠ Structure added but not visible in viewport (expected)")
            else:
                print(f"  ✗ Failed to place structure")

            time.sleep(1)  # Brief pause for log readability

        print(f"\n=== Planning Complete ===")
        print(f"Structures placed: {structures_placed}")

        # Show final ASCII map
        entries = c.list()
        print(f"\nContainer now has {len(entries)} entries")
        print(f"Architecture entries: {len([e for e in entries if e['role'] == 'architecture'])}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
VLM Spatial Observer — Vision-Language Model integration for Geometry OS

The VLM watches the MKV surface (Frame 0) and:
1. Observes kernel state as visual patterns (process blocks, memory allocations)
2. Detects hot code paths by watching instruction frequency
3. Identifies optimization opportunities (fragmentation, sparse allocations)
4. Generates Patch-and-Copy payloads for autonomous optimization

Architecture:
  [MKV Frames] → [Frame Capture] → [VLM Analysis] → [Patch Payload] → [Kernel Update]

The observer bridges the gap between:
- Visual patterns (what the VLM sees)
- Spatial coordinates (where pixels are)
- Code opcodes (what they mean)
- Optimization actions (what to change)
"""

import argparse
import json
import struct
import numpy as np
import sys
import subprocess
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Check Ollama availability
try:
    result = subprocess.run(["ollama", "--version"], capture_output=True, timeout=5)
    OLLAMA_AVAILABLE = result.returncode == 0
except Exception:
    OLLAMA_AVAILABLE = False

from tools.spatial_os_kernel_3d import SpatialOS3D


# Opcodes from spatial_os_kernel_3d.py
OPCODES = {
    "LDI": 0,
    "ADD": 1,
    "PRT": 8,
    "HALT": 9,
    "MMAP": 10,
    "MUNMAP": 11,
}

OPCODE_COLORS = {
    "LDI": [236, 80, 80],
    "ADD": [80, 236, 120],
    "PRT": [247, 83, 80],
    "HALT": [255, 0, 0],
    "MMAP": [128, 128, 128],
    "MUNMAP": [128, 0, 128],
}

COLOR_TO_OPCODE = {tuple(v): k for k, v in OPCODE_COLORS.items()}


class VLMSpatialObserver:
    """Vision-Language Model observer for spatial kernel state"""

    def __init__(self, os_kernel: SpatialOS3D, model="llava:latest"):
        self.os = os_kernel
        self.model = model
        self.frame_width = os_kernel.vram_width
        self.frame_height = os_kernel.vram_height
        self.frame_depth = os_kernel.vram_depth

    def capture_frame_0(self) -> np.ndarray:
        """Capture Frame 0 (active VRAM) as a visual image"""
        # Read vram buffer from GPU
        data = self.os.device.queue.read_buffer(self.os.vram_buf)

        # vram_data_u32 is uint32, reshape it first then convert to uint8
        pixels_u32 = np.frombuffer(data, dtype=np.uint32).reshape(
            self.frame_depth, self.frame_height, self.frame_width, 4
        )

        # Convert to uint8 for color extraction
        pixels = pixels_u32.astype(np.uint8)
        return pixels[0]  # Frame 0 only

    def opcode_histogram(self, frame: np.ndarray) -> dict:
        """Count opcodes visible on frame"""
        histogram = {name: 0 for name in OPCODES.keys()}
        unknown = 0

        for y in range(self.frame_height):
            for x in range(self.frame_width):
                rgb = tuple(frame[y, x, :3])
                if rgb in COLOR_TO_OPCODE:
                    histogram[COLOR_TO_OPCODE[rgb]] += 1
                elif not (rgb == (0, 0, 0)):
                    unknown += 1

        histogram["UNKNOWN"] = unknown
        return histogram

    def detect_hot_regions(self, frame: np.ndarray, threshold=5) -> list:
        """Find dense instruction blocks (potential hot code paths)"""
        hot_regions = []

        # Scan in 4x4 blocks (Hilbert-friendly size)
        block_size = 4
        for y in range(0, self.frame_height, block_size):
            for x in range(0, self.frame_width, block_size):
                # Count non-black pixels in block
                count = 0
                for dy in range(block_size):
                    for dx in range(block_size):
                        if (x + dx) < self.frame_width and (y + dy) < self.frame_height:
                            rgb = frame[y + dy, x + dx, :3]
                            if not (rgb[0] == 0 and rgb[1] == 0 and rgb[2] == 0):
                                count += 1

                if count >= threshold:
                    hot_regions.append({
                        "x": x,
                        "y": y,
                        "size": block_size,
                        "density": count / (block_size * block_size),
                    })

        return hot_regions

    def analyze_fragmentation(self, frame: np.ndarray) -> dict:
        """Analyze memory fragmentation on the active frame"""
        free_pixels = 0
        free_runs = []  # Consecutive free pixel runs
        current_run = 0

        for y in range(self.frame_height):
            for x in range(self.frame_width):
                rgb = frame[y, x, :3]
                if rgb[0] == 0 and rgb[1] == 0 and rgb[2] == 0:
                    free_pixels += 1
                    current_run += 1
                else:
                    if current_run > 0:
                        free_runs.append(current_run)
                    current_run = 0

        if current_run > 0:
            free_runs.append(current_run)

        total_pixels = self.frame_width * self.frame_height
        avg_free_run = sum(free_runs) / len(free_runs) if free_runs else 0

        return {
            "free_pixels": free_pixels,
            "total_pixels": total_pixels,
            "utilization": (total_pixels - free_pixels) / total_pixels,
            "free_runs": len(free_runs),
            "avg_free_run": avg_free_run,
            "max_free_run": max(free_runs) if free_runs else 0,
        }

    def generate_visual_prompt(self, frame: np.ndarray, histogram: dict, hot_regions: list, frag: dict) -> str:
        """Generate a prompt for the VLM based on visual observations"""

        prompt = f"""
SPATIAL KERNEL VISUAL ANALYSIS

You are observing a Geometry OS kernel running on a GPU. The screen shows Frame 0 (active VRAM) as pixels.

FRAME METRICS:
- Resolution: {self.frame_width}×{self.frame_height} (Z coordinate is always 0)
- Utilization: {frag['utilization']:.1%}
- Free pixels: {frag['free_pixels']}/{frag['total_pixels']}
- Free runs: {frag['free_runs']} (avg: {frag['avg_free_run']:.1f}, max: {frag['max_free_run']})

OPCODE HISTOGRAM:
"""
        for opcode, count in histogram.items():
            if count > 0:
                prompt += f"  {opcode}: {count}\n"

        prompt += f"\nHOT REGIONS (dense blocks):\n"
        if hot_regions:
            for i, region in enumerate(hot_regions[:5]):  # Top 5
                region_x = region['x']
                region_y = region['y']
                prompt += f"  Region {i+1}: ({region_x}, {region_y}, 0) - {region['size']}×{region['size']} - {region['density']:.0%} dense\n"
        else:
            prompt += "  None detected\n"

        prompt += f"""
ANALYSIS TASK:
1. Identify potential optimization opportunities
2. For each opportunity, use ACTUAL COORDINATES from the hot regions above in format "(x, y, z)"
3. Suggest which hot regions should be compacted/coalesced
4. Propose memory reallocation strategy

CRITICAL: Your "target" field MUST use exact coordinates like "(16, 20, 0)" - DO NOT use text descriptions.

Respond in JSON format:
{{
  "opportunities": [
    {{
      "type": "FILL_RECT|CLEAR_REGION|COPY_BLOCK",
      "target": "(x, y, z)",
      "color": [r, g, b],
      "width": w,
      "height": h,
      "rationale": "why this should be optimized",
      "status": "PENDING"
    }}
  ],
  "priority": "HIGH|MEDIUM|LOW"
}}
"""
        return prompt

    def call_ollama(self, prompt: str) -> dict:
        """Call Ollama VLM with visual prompt"""

        if not OLLAMA_AVAILABLE:
            print("WARNING: Ollama not available, using mock analysis with concrete patch")
            # Generate concrete patch with actual coordinates for testing
            return {
                "opportunities": [
                    {
                        "type": "FILL_RECT",
                        "target": "(16, 20, 0)",  # Actual coordinates
                        "color": [236, 80, 80],  # LDI opcode color
                        "width": 4,
                        "height": 4,
                        "rationale": "dense block should be compacted",
                        "status": "PENDING"
                    }
                ],
                "priority": "HIGH",
            }

        try:
            result = subprocess.run(
                ["ollama", "run", self.model, prompt],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                print(f"ERROR: Ollama failed: {result.stderr}")
                return {"opportunities": [], "priority": "LOW"}

            # Try to parse JSON response
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                # Extract JSON if embedded in text
                import re
                match = re.search(r'\{.+?\}', result.stdout, re.DOTALL)
                if match:
                    return json.loads(match.group(0))

                return {"opportunities": [], "priority": "LOW"}

        except subprocess.TimeoutExpired:
            print("ERROR: Ollama timeout")
            return {"opportunities": [], "priority": "LOW"}
        except Exception as e:
            print(f"ERROR: Ollama call failed: {e}")
            return {"opportunities": [], "priority": "LOW"}

    def observe_and_analyze(self) -> dict:
        """Full observation and analysis cycle"""
        print("=" * 60)
        print("VLM SPATIAL OBSERVER")
        print("=" * 60)

        # Capture frame
        print("\n[1] Capturing Frame 0...")
        frame = self.capture_frame_0()
        print(f"  ✓ Frame captured: {frame.shape}")

        # Opcode histogram
        print("\n[2] Analyzing opcode distribution...")
        histogram = self.opcode_histogram(frame)
        print(f"  ✓ Histogram computed")
        for opcode, count in histogram.items():
            if count > 0:
                print(f"    {opcode}: {count}")

        # Hot regions
        print("\n[3] Detecting hot regions...")
        hot_regions = self.detect_hot_regions(frame)
        print(f"  ✓ Found {len(hot_regions)} hot regions")
        for i, region in enumerate(hot_regions[:3]):
            print(f"    Region {i+1}: ({region['x']}, {region['y']}) - {region['density']:.0%} dense")

        # Fragmentation
        print("\n[4] Analyzing fragmentation...")
        frag = self.analyze_fragmentation(frame)
        print(f"  ✓ Utilization: {frag['utilization']:.1%}")
        print(f"  ✓ Free runs: {frag['free_runs']} (avg: {frag['avg_free_run']:.1f})")

        # VLM analysis
        print("\n[5] VLM Analysis...")
        prompt = self.generate_visual_prompt(frame, histogram, hot_regions, frag)
        vlm_result = self.call_ollama(prompt)
        print(f"  ✓ Priority: {vlm_result['priority']}")
        print(f"  ✓ Opportunities: {len(vlm_result['opportunities'])}")
        for opp in vlm_result['opportunities']:
            print(f"    - {opp['type']}: {opp['rationale']}")

        # Return full analysis
        return {
            "frame_shape": frame.shape,
            "histogram": histogram,
            "hot_regions": hot_regions,
            "fragmentation": frag,
            "vlm_analysis": vlm_result,
        }

    def generate_patch_payload(self, analysis: dict) -> dict:
        """Generate Patch-and-Copy payload based on VLM analysis"""
        print("\n[6] Generating Patch-and-Copy payload...")

        payload = {
            "version": "1.0",
            "source": "VLM Spatial Observer",
            "timestamp": "",
            "patches": [],
        }

        for opp in analysis["vlm_analysis"]["opportunities"]:
            patch = {
                "type": opp["type"],
                "target": opp["target"],
                "rationale": opp["rationale"],
                "status": opp.get("status", "PENDING"),
            }
            # Include optional fields if present
            if "color" in opp:
                patch["color"] = opp["color"]
            if "width" in opp:
                patch["width"] = opp["width"]
            if "height" in opp:
                patch["height"] = opp["height"]
            payload["patches"].append(patch)

        print(f"  ✓ Generated {len(payload['patches'])} patches")
        return payload


def main():
    parser = argparse.ArgumentParser(
        description="VLM Spatial Observer — Watch MKV surface and generate optimization patches"
    )
    parser.add_argument(
        "--model",
        default="llava:latest",
        help="Ollama VLM model (default: llava:latest)",
    )
    parser.add_argument(
        "--output",
        default="/tmp/vlm_analysis.json",
        help="Output JSON file for analysis results",
    )
    parser.add_argument(
        "--generate-patch",
        action="store_true",
        help="Generate Patch-and-Copy payload",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: continuously observe and analyze",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Watch interval in seconds (default: 5)",
    )

    args = parser.parse_args()

    # Initialize Spatial OS kernel
    print("\nBooting Spatial OS 3D Kernel...")
    os_kernel = SpatialOS3D()
    os_kernel.init_kernel()

    # Initialize VLM observer
    print("\nInitializing VLM Observer...")
    observer = VLMSpatialObserver(os_kernel, model=args.model)

    if args.watch:
        print(f"\nWatch mode: analyzing every {args.interval} seconds...")
        print("Press Ctrl+C to stop\n")

        import time
        try:
            cycle = 0
            while True:
                cycle += 1
                print(f"\n=== Cycle {cycle} ===")

                # Run a few ticks of execution
                os_kernel.tick(5)

                # Observe and analyze
                analysis = observer.observe_and_analyze()

                # Generate patch if requested
                if args.generate_patch:
                    patch = observer.generate_patch_payload(analysis)

                # Save analysis
                with open(args.output, "w") as f:
                    json.dump(analysis, f, indent=2)
                print(f"  ✓ Analysis saved to {args.output}")

                time.sleep(args.interval)

        except KeyboardInterrupt:
            print("\n\nWatch mode stopped")
    else:
        # Single-shot analysis
        analysis = observer.observe_and_analyze()

        if args.generate_patch:
            patch = observer.generate_patch_payload(analysis)
            patch_path = args.output.replace(".json", "_patch.json")
            with open(patch_path, "w") as f:
                json.dump(patch, f, indent=2)
            print(f"\n  ✓ Patch payload saved to {patch_path}")

        # Save analysis
        with open(args.output, "w") as f:
            json.dump(analysis, f, indent=2)
        print(f"\n  ✓ Analysis saved to {args.output}")

    print("\n" + "=" * 60)
    print("VLM SPATIAL OBSERVER COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
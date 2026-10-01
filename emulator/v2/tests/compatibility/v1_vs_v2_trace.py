#!/usr/bin/env python3
"""
emulator/v2/tests/compatibility/v1_vs_v2_trace.py

Run identical execution trace on v1 and v2 emulators and compare results.

Usage:
    python3 v1_vs_v2_trace.py --kernel boot_images/alpine_vmlinuz --steps 1000000

Output:
    - v1 trace: .work/v1_trace.jsonl
    - v2 trace: .work/v2_trace.jsonl
    - Comparison report: .work/compatibility_report.txt
"""

import argparse
import sys
from pathlib import Path

# Add v1 and v2 to path
_V1_PATH = Path(__file__).parent.parent.parent.parent / "tools"
_V2_PATH = Path(__file__).parent.parent.parent

sys.path.insert(0, str(_V1_PATH))
sys.path.insert(0, str(_V2_PATH))

# Import both emulators (v1 and v2)
try:
    from spatial_rv64i_cpu import SpatialRV64ICore
    from emulator.v2.spatial_rv64i_v2 import SpatialRV64ICoreV2
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

def capture_trace(core_class, kernel_path: Path, max_steps: int, output_path: Path):
    """Capture execution trace from an emulator."""
    print(f"Capturing trace from {core_class.__name__}...")
    print(f"  Kernel: {kernel_path}")
    print(f"  Max steps: {max_steps}")
    print(f"  Output: {output_path}")

    core = core_class(64 * 1024 * 1024)  # 64MB RAM

    # Load kernel
    kernel_bytes = kernel_path.read_bytes()
    core.load_program(kernel_bytes, entry_point=0x80200000, ram_base=0x80000000)

    # Capture trace
    trace = []
    for step in range(0, max_steps, 10000):  # Sample every 10k steps
        core.step(10000)
        state = core.get_state()
        trace.append({
            "step": step,
            "pc": state["pc"],
            "running": state["running"],
            "priv_mode": state["priv_mode"],
        })

    # Save trace
    import json
    with open(output_path, "w") as f:
        for entry in trace:
            f.write(json.dumps(entry) + "\n")

    print(f"  Captured {len(trace)} samples")
    return trace

def compare_traces(v1_trace, v2_trace, tolerance: float = 0.0):
    """Compare v1 and v2 traces for compatibility."""
    if len(v1_trace) != len(v2_trace):
        return False, f"Trace length mismatch: v1={len(v1_trace)}, v2={len(v2_trace)}"

    mismatches = []
    for i, (v1_entry, v2_entry) in enumerate(zip(v1_trace, v2_trace)):
        if v1_entry["pc"] != v2_entry["pc"]:
            mismatches.append(f"Step {v1_entry['step']}: PC mismatch v1=0x{v1_entry['pc']:x}, v2=0x{v2_entry['pc']:x}")
        if v1_entry["running"] != v2_entry["running"]:
            mismatches.append(f"Step {v1_entry['step']}: running mismatch v1={v1_entry['running']}, v2={v2_entry['running']}")
        if v1_entry["priv_mode"] != v2_entry["priv_mode"]:
            mismatches.append(f"Step {v1_entry['step']}: priv_mode mismatch v1={v1_entry['priv_mode']}, v2={v2_entry['priv_mode']}")

    if mismatches:
        return False, f"Found {len(mismatches)} mismatches:\n" + "\n".join(mismatches[:10])  # First 10

    return True, "PASS: Traces are identical"

def main():
    ap = argparse.ArgumentParser(description="V1 vs V2 compatibility test")
    ap.add_argument("--kernel", type=Path, default=Path("boot_images/alpine_vmlinuz"),
                    help="Kernel image to boot")
    ap.add_argument("--steps", type=int, default=1_000_000,
                    help="Max instructions to execute")
    ap.add_argument("--tolerance", type=float, default=0.0,
                    help="Allowed divergence fraction (0.0 = exact match)")
    args = ap.parse_args()

    # Work directory
    work_dir = Path(".work")
    work_dir.mkdir(exist_ok=True)

    # Capture traces
    v1_trace_path = work_dir / "v1_trace.jsonl"
    v2_trace_path = work_dir / "v2_trace.jsonl"

    v1_trace = capture_trace(SpatialRV64ICore, args.kernel, args.steps, v1_trace_path)
    v2_trace = capture_trace(SpatialRV64ICoreV2, args.kernel, args.steps, v2_trace_path)

    # Compare
    print("\n=== Compatibility Test ===")
    success, message = compare_traces(v1_trace, v2_trace, args.tolerance)
    print(message)

    # Save report
    report_path = work_dir / "compatibility_report.txt"
    with open(report_path, "w") as f:
        f.write(f"V1 vs V2 Compatibility Test\n")
        f.write(f"Kernel: {args.kernel}\n")
        f.write(f"Steps: {args.steps}\n")
        f.write(f"Tolerance: {args.tolerance}\n")
        f.write(f"\nResult: {message}\n")

    print(f"\nReport saved to: {report_path}")
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
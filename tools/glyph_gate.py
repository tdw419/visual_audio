"""Normalized per-item gate runner for Glyph OS roadmap items.

Ensures consistent PYTHONPATH (tools:.), captures individual test legs,
reports pass/fail tallies, and can generate receipt files.

Usage:
    python3 tools/glyph_gate.py 18
    python3 tools/glyph_gate.py 23 --receipt
    python3 tools/glyph_gate.py --list
"""

import argparse
import glob
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent


def get_gate_map() -> Dict[str, str]:
    """Discover all tests/test_gh*.py gate files."""
    gates: Dict[str, str] = {}
    pattern = str(_REPO_ROOT / "tests" / "test_gh*.py")
    for f in sorted(glob.glob(pattern)):
        basename = os.path.basename(f)
        # Extract item identifier, e.g. test_gh18_syscall_abi.py -> 18, test_gh8c_... -> 8c
        parts = basename.split("_")
        if len(parts) >= 2 and parts[1].startswith("gh"):
            item_id = parts[1][2:]  # strip 'gh'
            gates[item_id] = os.path.relpath(f, _REPO_ROOT)
    return gates


def run_gate(item_id: str, write_receipt: bool = False, verbose: bool = True) -> Tuple[bool, str]:
    gates = get_gate_map()
    if item_id not in gates:
        print(f"Error: No gate test file found for GH-{item_id}. Available: {', '.join(sorted(gates.keys()))}")
        return False, ""

    test_file = gates[item_id]
    cmd = [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{_REPO_ROOT / 'tools'}:{_REPO_ROOT}"

    start_t = time.time()
    proc = subprocess.run(
        cmd,
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    duration = time.time() - start_t

    out = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    passed = (proc.returncode == 0)

    summary_lines = []
    summary_lines.append(f"=== GH-{item_id} Gate Test ({test_file}) ===")
    summary_lines.append(f"Status: {'PASS' if passed else 'FAIL'} (exit code {proc.returncode}) in {duration:.2f}s")
    summary_lines.append("")
    summary_lines.append(out.strip())

    full_report = "\n".join(summary_lines)

    if verbose:
        print(full_report)

    if write_receipt:
        out_dir = _REPO_ROOT / "output"
        out_dir.mkdir(exist_ok=True)
        receipt_path = out_dir / f"gh{item_id}_gate_receipt.txt"
        with open(receipt_path, "w") as rf:
            rf.write(full_report)
        print(f"\nReceipt written to {receipt_path}")

    return passed, full_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Glyph OS Normalized Gate Runner")
    parser.add_argument("item", nargs="?", default="", help="Roadmap item ID (e.g. 18, 20, 21, 22, 23, or 'all')")
    parser.add_argument("--list", action="store_true", help="List all available gates")
    parser.add_argument("--receipt", action="store_true", help="Write receipt to output/gh<item>_gate_receipt.txt")

    args = parser.parse_args()
    gates = get_gate_map()

    if args.list or not args.item:
        print("Available Glyph OS Gates:")
        for k, v in sorted(gates.items(), key=lambda x: (int(x[0]) if x[0].isdigit() else 999, x[0])):
            print(f"  GH-{k:<4}: {v}")
        return

    if args.item == "all":
        all_pass = True
        for k in sorted(gates.keys(), key=lambda x: (int(x[0]) if x[0].isdigit() else 999, x[0])):
            ok, _ = run_gate(k, write_receipt=args.receipt, verbose=True)
            if not ok:
                all_pass = False
        sys.exit(0 if all_pass else 1)

    # Normalize item: e.g. "GH-18" -> "18"
    item = args.item.upper()
    if item.startswith("GH-"):
        item = item[3:]
    elif item.startswith("GH"):
        item = item[2:]
    item = item.lower()

    ok, _ = run_gate(item, write_receipt=args.receipt, verbose=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

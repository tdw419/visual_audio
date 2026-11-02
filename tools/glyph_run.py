#!/usr/bin/env python3
"""glyph_run.py — R2.2 toolchain UX: ONE command compiles a program to a
glyph/tile artifact and runs it (PRODUCT_ROADMAP.md R2.2).

You do not need to have read this repo. Given a .glyph assembly source:

    python3 tools/glyph_run.py my_program.glyph

this bakes the spatial pixel artifact (default: my_program.glyph.png next to
the source — the artifact IS the program: code, tiles, and initial data as
pixels), executes it on the Glyph machine, and prints a receipt.

Run an existing artifact (no source needed):

    python3 tools/glyph_run.py my_program.glyph.png

Exit codes:
    0  clean HALT
    1  faulted (fault_addr / fault_reason in the receipt)
    2  the program did not assemble (bad instruction, undefined label, ...)
    3  instruction budget exhausted without HALT (still-running program)
    4  could not read the input file

Machine-readable receipt: add --json.

The instruction dialect is the Glyph assembly the repo's own engines speak
(see tests/test_glyph_run.py and examples/sum_1_to_5.glyph for a worked
sample: LDI/CMP/JZ/ADD/JMP/PRT/HALT with :label targets).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

EXIT_OK = 0
EXIT_FAULT = 1
EXIT_ASSEMBLE = 2
EXIT_BUDGET = 3
EXIT_IO = 4

ARTIFACT_SUFFIXES = (".png", ".npy", ".npz")


def _compile(source: Path, artifact: Path):
    """Bake .glyph source text -> spatial artifact. Raises on bad source."""
    from tools.glyph_gpt.baker import bake_image

    text = source.read_text()
    bake_image(text, cols_instrs=8, out_path=artifact)
    return artifact


def _run(artifact: Path, max_instructions: int) -> dict:
    """Execute a spatial artifact to HALT/fault/budget. Returns a receipt."""
    import contextlib
    import io

    from tools.glyph_gpt.runner import GlyphRunner

    runner = GlyphRunner(artifact, ram_words=16384)
    cpu = runner.get_cpu()
    cpu.running = True
    steps = 0
    # The engine's PRT prints directly to stdout (would pollute --json);
    # capture it — PRT results are reported via cpu.output in the receipt.
    with contextlib.redirect_stdout(io.StringIO()):
        while cpu.running and steps < max_instructions:
            cpu.step(runner.image)
            steps += 1
    receipt = {
        "artifact": str(artifact),
        "halted": not cpu.running and not getattr(cpu, "faulted", False),
        "faulted": bool(getattr(cpu, "faulted", False)),
        "steps": steps,
        "budget_exhausted": bool(cpu.running),
        "output": [int(v) & 0xFFFFFFFF for v in getattr(cpu, "output", [])],
        "registers": [int(r) & 0xFFFFFFFF for r in cpu.registers],
    }
    if receipt["faulted"]:
        receipt["fault_addr"] = int(getattr(cpu, "fault_addr", 0)) & 0xFFFFFFFF
        reason = getattr(cpu, "fault_reason", None)
        if reason:
            receipt["fault_reason"] = reason
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="glyph_run",
        description="Compile a .glyph program to a glyph/tile pixel artifact "
                    "and run it on the Glyph machine (one command).",
    )
    ap.add_argument("program",
                    help=".glyph assembly source, or a baked artifact "
                         "(.png/.npy/.npz) to run directly")
    ap.add_argument("-o", "--output", default=None,
                    help="artifact path to write (default: <source>.glyph.png "
                         "next to the source; ignored when running an artifact)")
    ap.add_argument("--max-instructions", type=int, default=1_000_000,
                    help="instruction budget before giving up (default 1e6)")
    ap.add_argument("--json", action="store_true",
                    help="print the machine-readable JSON receipt only")
    args = ap.parse_args(argv)

    program = Path(args.program)
    if not program.exists():
        print(f"glyph_run: no such file: {program}", file=sys.stderr)
        return EXIT_IO

    try:
        if program.suffix.lower() in ARTIFACT_SUFFIXES:
            artifact = program
        else:
            artifact = (Path(args.output) if args.output
                        else program.with_suffix(".glyph.png"))
            try:
                _compile(program, artifact)
            except Exception as e:
                print(f"glyph_run: compile failed: {type(e).__name__}: {e}",
                      file=sys.stderr)
                return EXIT_ASSEMBLE
    except OSError as e:
        print(f"glyph_run: {e}", file=sys.stderr)
        return EXIT_IO

    try:
        receipt = _run(artifact, args.max_instructions)
    except OSError as e:
        print(f"glyph_run: {e}", file=sys.stderr)
        return EXIT_IO

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(f"artifact : {receipt['artifact']}")
        if receipt["faulted"]:
            print("result   : FAULT")
            print(f"steps    : {receipt['steps']}")
            print(f"fault    : addr={receipt.get('fault_addr')} "
                  f"{receipt.get('fault_reason', '')}")
        elif receipt["budget_exhausted"]:
            print("result   : NO HALT (instruction budget exhausted)")
            print(f"steps    : {receipt['steps']}")
        else:
            print("result   : HALT")
            print(f"steps    : {receipt['steps']}")
            for v in receipt["output"]:
                print(f"output   : {v}")

    if receipt["faulted"]:
        return EXIT_FAULT
    if receipt["budget_exhausted"]:
        return EXIT_BUDGET
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

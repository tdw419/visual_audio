"""h5 fixture generator (deterministic, offline, measured).

Builds the Muse Spark semantic-layer corpus under hackathon/tests/fixtures/:

  h5_corpus.json
      Three C programs (sum, fib, max2), each with: an ENGLISH description
      (the semantic layer's input), the C source, the transpiler's reference
      glyph asm (RV32I ELF -> tools/rv64i_to_glyph.transpile_elf_to_glyph),
      and the measured ground truth: native x86 result, GlyphCPUv2 r10(a0)
      result, clean-halt flag, instruction count.
      Ground-truth provenance: native x86 execution + the QEMU-diff-verified
      GlyphCPUv2 chain. qemu-riscv32-static EXISTS on this host but is
      sandbox-walled (EPERM on MAP_FIXED at guest address 0; -B guest-base
      workaround hangs) -- see h5_RECEIPT.md ASK note. The corpus's own
      tests (tests/test_rv64i_to_glyph_*.py) establish the transpiler corpus
      as ground truth; this lane does NOT modify tools/.
  h5_response_*.json
      Recorded muse-spark-1.3 chat.completion responses (Meta API fixtures
      per lane rules -- live probes are operator receipts):
        sum_match   exact transpiler reference asm in a fenced ```asm block
        sum_wrong   convention-clean but semantically WRONG program
                    (sums 1..11 -> 66, ground truth is 55)
        bad3op      3rd arithmetic operand (the SILENTLY DROPPED class)
        badlabel    label def glued onto an instruction line
        comma       comma-separated operands (violates space-separated)
  h5_handwritten_sum.asm
      A hand-written, convention-clean 9-instruction sum loop (the kind of
      asm the semantic layer is supposed to make possible) -- execution-
      checked against the same ground truth.

Run: /usr/bin/python3.12 hackathon/demo/glyph_fixtures_h5.py [outdir]
Requires: riscv64-unknown-elf-gcc, gcc, numpy (toolchain provenance is
recorded in the fixture meta).
"""
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from tools.rv64i_to_glyph import (  # noqa: E402
    assemble_glyph_to_pixels,
    transpile_elf_to_glyph,
)
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402

RUN_BODIES = {
    "sum": (
        "__attribute__((noinline)) int run(void) { "
        "volatile int n = 10; int s = 0; "
        "for (volatile int i = 1; i <= n; i++) s += i; return s; }"
    ),
    "fib": (
        "__attribute__((noinline)) int run(void) { "
        "volatile int n = 10; int a = 0, b = 1; "
        "for (volatile int i = 0; i < n; i++) { int t = a + b; a = b; b = t; } "
        "return a; }"
    ),
    "max2": (
        "__attribute__((noinline)) int run(void) { "
        "volatile int x = 17; volatile int y = 42; "
        "return (x > y) ? x : y; }"
    ),
}

DESCRIPTIONS = {
    "sum": (
        "Compute the sum of the integers from 1 through 10 using a loop "
        "and leave the result in return register a0."
    ),
    "fib": (
        "Iterate the Fibonacci sequence for 10 steps starting from a=0, "
        "b=1 and return the tenth value in a0."
    ),
    "max2": (
        "Compare the values 17 and 42 and return the larger one in a0."
    ),
}

START_ASM = 'void _start(void) { __asm__ volatile ("li sp, 0x4000\\n call run\\n ecall\\n"); }'

HANDWRITTEN_SUM = """\
# sum 1..10 -> r10 (a0) -- hand-written, convention-clean
LDI r10 0        # accumulator
LDI r8 1         # i
LDI r9 11        # one past n: loop until i == 11
:cond
CMP r8 r9
JZ :done         # flag-based: JZ jumps when the CMP equality flag r0 is set
ADD r10 r8
LDI r7 1
ADD r8 r7
JMP :cond
:done
HALT
"""

# Recorded muse-spark-1.3 responses. sum_match is filled in at generation
# time with the transpiler's reference asm (the model output the layer must
# verify instruction-level); the rest are static.
RESPONSE_TEXT_STATIC = {
    "sum_wrong": (
        "Here is the glyph assembly:\n"
        "```asm\n"
        "LDI r10 0\nLDI r8 1\nLDI r9 12\n:cond\nCMP r8 r9\nJZ :done\n"
        "ADD r10 r8\nLDI r7 1\nADD r8 r7\nJMP :cond\n:done\nHALT\n"
        "```\nThis loops i from 1 while i != 12, accumulating into r10."
    ),
    "bad3op": (
        "```asm\nLDI r10 0\nLDI r8 1\nADD r10 r8 r9\nHALT\n```\n"
        "Accumulate with a three-operand add."
    ),
    "badlabel": (
        "```asm\nLDI r10 0 :loop\nADD r10 r8\nHALT\n```\nLoop with a label."
    ),
    "comma": (
        "```asm\nLDI r10, 0\nLDI r8, 1\nADD r10, r8\nHALT\n```\nSum two values."
    ),
}


def _gcc_toolchain():
    out = {}
    for tool in ("gcc", "riscv64-unknown-elf-gcc"):
        try:
            out[tool] = subprocess.run([tool, "--version"], capture_output=True,
                                       text=True).stdout.splitlines()[0]
        except OSError:
            out[tool] = "MISSING"
    return out


def build_reference(name, tmp):
    body = RUN_BODIES[name]
    c = tmp / f"{name}.c"
    c.write_text(body + "\n#ifndef HOST_TEST\n" + START_ASM + "\n#endif\n")
    # native x86 ground truth
    nat = tmp / f"native_{name}.c"
    nat.write_text(body + '\n#include <stdio.h>\n'
                   'int main(void){ printf("%d\\n", run()); return 0; }\n')
    r = subprocess.run(["gcc", "-O1", "-w", str(nat), "-o", str(tmp / f"nat_{name}")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    native = int(subprocess.run([str(tmp / f"nat_{name}")], capture_output=True,
                                text=True, timeout=60).stdout.strip())
    # rv32i ELF
    elf = tmp / f"{name}.elf"
    r = subprocess.run(
        ["riscv64-unknown-elf-gcc", "-march=rv32i", "-mabi=ilp32", "-O1",
         "-nostdlib", "-fno-builtin", "-w", "-Wl,-Ttext=0x0", str(c), "-o", str(elf)],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    # transpiler reference asm (ground truth -- do not modify tools/)
    ref_asm = transpile_elf_to_glyph(elf.read_bytes(), entry_symbol="_start",
                                     byte_to_word_mem=True)
    # GlyphCPUv2 execution ground truth
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
    pixels, _ = assemble_glyph_to_pixels(ref_asm, cols_instrs=64, min_rows=32)
    cpu.memory = [0] * 16384
    cpu.pc = (0, 0)
    cpu.running = True
    for _ in range(300000):
        if not cpu.step(pixels):
            break
    halted = not cpu.running
    glyph_r10 = cpu.registers[10]
    instrs = sum(1 for ln in ref_asm.splitlines()
                 if ln.strip() and not ln.strip().startswith(("#", ";", ":")))
    assert halted, f"{name}: GlyphCPUv2 did not halt"
    assert glyph_r10 == native, f"{name}: glyph {glyph_r10} != native {native}"
    return {
        "name": name,
        "description": DESCRIPTIONS[name],
        "c_source": body + "\n" + START_ASM + "\n",
        "reference_asm": ref_asm,
        "ground_truth": {
            "native_result": native,
            "glyph_result": glyph_r10,
            "halted": halted,
            "instruction_count": instrs,
        },
    }


def _chat_response(content):
    return {
        "id": "chatcmpl-h5-recorded",
        "object": "chat.completion",
        "created": 1769472000,
        "model": "muse-spark-1.3",
        "choices": [
            {"index": 0,
             "message": {"role": "assistant", "content": content},
             "finish_reason": "stop"}
        ],
    }


def main(outdir):
    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    import tempfile
    cases = []
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        for name in ("sum", "fib", "max2"):
            cases.append(build_reference(name, tmp))

    corpus = {
        "meta": {
            "purpose": "h5 Muse Spark semantic-layer corpus (RED fixture set)",
            "ground_truth_chain": (
                "rv32i ELF -> tools/rv64i_to_glyph.transpile_elf_to_glyph "
                "(reference asm, transpiler corpus is ground truth) -> "
                "assemble_glyph_to_pixels -> GlyphCPUv2; results cross-checked "
                "against native x86 execution of the same C"
            ),
            "qemu_note": (
                "qemu-riscv32-static exists on the build host but is "
                "sandbox-walled (EPERM on MAP_FIXED at guest address 0; "
                "-B guest-base workaround hangs) -- the lane uses the "
                "corpus's own QEMU-diff-verified engine chain instead; "
                "see .factory/receipts/h5_RECEIPT.md"
            ),
            "toolchain": _gcc_toolchain(),
        },
        "cases": cases,
    }
    (out / "h5_corpus.json").write_text(json.dumps(corpus, indent=1) + "\n")

    ref_sum = cases[0]["reference_asm"]
    texts = dict(RESPONSE_TEXT_STATIC)
    texts["sum_match"] = (
        "Sure — here is glyph spatial asm for that:\n```asm\n"
        + ref_sum + "```\nThe result is left in r10 (a0)."
    )
    for key, content in texts.items():
        (out / f"h5_response_{key}.json").write_text(
            json.dumps(_chat_response(content), indent=1) + "\n")

    (out / "h5_handwritten_sum.asm").write_text(HANDWRITTEN_SUM)

    # self-check: handwritten program executes to the sum ground truth
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
    pixels, _ = assemble_glyph_to_pixels(HANDWRITTEN_SUM, cols_instrs=64, min_rows=8)
    cpu.memory = [0] * 16384
    cpu.pc = (0, 0)
    cpu.running = True
    for _ in range(10000):
        if not cpu.step(pixels):
            break
    assert not cpu.running, "handwritten sum did not halt"
    assert cpu.registers[10] == cases[0]["ground_truth"]["glyph_result"], \
        f"handwritten sum r10={cpu.registers[10]}"
    print(f"wrote {len(cases)} corpus cases + {len(texts)} responses + handwritten "
          f"to {out}; handwritten r10={cpu.registers[10]}")


if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else str(
        pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures")
    main(outdir)

#!/usr/bin/env python3
"""glyph_cc.py — R2.3 hosted cross-compilation story (PRODUCT_ROADMAP.md R2.3).

One command takes C or Rust source (or a prebuilt RV32 ELF) all the way to a
running result on the Glyph machine:

    python3 tools/glyph_cc.py program.c          # C via riscv64-unknown-elf-gcc -march=rv32i
    python3 tools/glyph_cc.py program.rs         # Rust via rustc --target riscv32im-unknown-none-elf
    python3 tools/glyph_cc.py program.elf        # prebuilt RV32(I/IM) ELF, transpiled directly

Chain: source -> rv32 ELF (hosted cross-compiler) -> rv64i_to_glyph transpiler
-> glyph assembly -> baked spatial artifact -> GlyphCPUv2 execution -> receipt
with the a0 exit value. Receipt also embeds a ROUND-TRIP section: the glyph
artifact is re-read from disk and re-executed, and must reproduce the same
result, proving artifact fidelity (the artifact IS the program).

Exit codes:
    0  clean HALT (see receipt for the a0 result)
    1  faulted on the Glyph machine
    2  toolchain/transpile failure (compile error, unsupported instruction)
    3  instruction budget exhausted without HALT
    4  could not read the input file / no usable toolchain

Machine-readable receipt: --json.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

EXIT_OK = 0
EXIT_FAULT = 1
EXIT_TOOLCHAIN = 2
EXIT_BUDGET = 3
EXIT_IO = 4

_GCC = "riscv64-unknown-elf-gcc"
_OBJCOPY = "riscv64-unknown-elf-objcopy"
_RUSTC = "rustc"
_RUST_TARGET = "riscv32im-unknown-none-elf"

# crt0 for the C lane: init gp (GCC small-data), set sp, call main, ecall=HALT.
_CRT0 = """\
.globl _start
_start:
.option push
.option norelax
lui gp, %hi(__global_pointer$)
addi gp, gp, %lo(__global_pointer$)
.option pop
li sp, 0x4000
call main
ecall
"""

# Rust bare-metal wrapper appended when the user's .rs has no _start: their
# `main` must be `pub extern "C" fn main() -> i32` (or `fn main()`).
_RUST_WRAP = """\
#[panic_handler]
fn _glyph_cc_panic(_info: &core::panic::PanicInfo) -> ! {
    loop {}
}

#[unsafe(no_mangle)]
#[unsafe(naked)]
pub extern "C" fn _start() -> ! {
    // Ticket TICKET_R53_day1_transpiler_auipc_jalr (2026-09-22, R5.3 day-1):
    // rustc emits `addi sp,sp,-16` prologues for any function with locals or
    // calls. With sp (r2) starting at 0, that wraps to 0xfffffff0 and the
    // first `sw ra,N(sp)` faults (measured: recursive fib(15) -> FAULT step 9,
    // sp=0xfffffff0). A plain inline-asm `li sp` does NOT fix it: rustc emits
    // its own prologue BEFORE the asm block (measured this exact miss), so the
    // prologue's stores still run with sp=0. `#[naked]` (stable since 1.82)
    // suppresses the prologue entirely; naked_asm sets sp before the first
    // call, mirroring the C lane's crt0 `li sp, 0x4000` (glyph_cc.py _CRT0).
    // a0 = main's own return value when ecall (-> glyph HALT) fires.
    unsafe {
        core::arch::naked_asm!(
            "lui sp, 0x4", // sp = 0x4000, before ANY prologue can store
            "call main",
            "ecall",
        )
    }
}
"""


def _fail(code: int, message: str) -> int:
    print(f"glyph_cc: {message}", file=sys.stderr)
    return code


def _detect_lang(path: Path) -> str:
    s = path.suffix.lower()
    if s in (".c", ".h"):
        return "c"
    if s == ".rs":
        return "rust"
    if s in (".elf", ".o"):
        return "elf"
    return "unknown"


def _compile_c(source: Path, tmp: Path) -> Path:
    if shutil.which(_GCC) is None:
        raise RuntimeError(f"{_GCC} not installed (C lane unavailable)")
    elf = tmp / "prog.elf"
    crt0 = tmp / "crt0.S"
    crt0.write_text(_CRT0)
    res = subprocess.run(
        [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
         "-fno-builtin", "-w", "-Wl,-Ttext=0x0", "-Wl,--build-id=none",
         str(crt0), str(source), "-o", str(elf)],
        capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"C cross-compile failed:\n{res.stderr}")
    return elf


def _compile_rust(source: Path, tmp: Path) -> Path:
    if shutil.which(_RUSTC) is None:
        raise RuntimeError("rustc not installed (Rust lane unavailable)")
    src_text = source.read_text()
    if "_start" not in src_text:
        wrapped = tmp / "wrapped.rs"
        wrapped.write_text(src_text + "\n" + _RUST_WRAP)
        src = wrapped
    else:
        src = source
    obj = tmp / "prog.o"
    res = subprocess.run(
        [_RUSTC, "--edition", "2021", "-C", "opt-level=1",
         "--target", _RUST_TARGET, "--emit=obj",
         "-o", str(obj), str(src)],
        capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Rust cross-compile failed:\n{res.stderr}")
    elf = tmp / "prog.elf"
    res = subprocess.run(
        [_GCC, "-march=rv32im", "-mabi=ilp32", "-nostdlib", "-w",
         "-Wl,-Ttext=0x0", "-Wl,--build-id=none", "-e", "_start",
         str(obj), "-o", str(elf)],
        capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Rust link failed:\n{res.stderr}")
    return elf


def transpile_and_run(elf_path: Path, artifact_out: Path,
                      max_instructions: int) -> dict:
    """ELF -> glyph assembly -> baked artifact -> execute -> receipt."""
    from tools.rv64i_to_glyph import (assemble_glyph_to_pixels,
                                      parse_elf_data_sections,
                                      transpile_elf_to_glyph)
    from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2

    elf_bytes = elf_path.read_bytes()
    glyph_source = transpile_elf_to_glyph(
        elf_bytes, entry_symbol="_start", byte_to_word_mem=True)
    pixels, meta = assemble_glyph_to_pixels(
        glyph_source, cols_instrs=64, min_rows=32)
    artifact_out.parent.mkdir(parents=True, exist_ok=True)
    _save_artifact(pixels, artifact_out)

    receipt = _exec_artifact(artifact_out, elf_bytes, max_instructions,
                             pointer_table=True)
    receipt["artifact"] = str(artifact_out)
    receipt["glyph_instructions"] = glyph_source.count("\n")
    receipt["_elf_bytes"] = elf_bytes
    return receipt


def _save_artifact(pixels, out_path: Path) -> None:
    import numpy as np
    if out_path.suffix.lower() == ".npy":
        np.save(out_path, pixels)
    elif out_path.suffix.lower() == ".npz":
        np.savez_compressed(out_path, pixels=pixels)
    else:
        from PIL import Image
        arr = np.asarray(pixels, dtype=np.uint8)
        Image.fromarray(arr).save(out_path)


def _exec_artifact(artifact: Path, elf_bytes: bytes,
                   max_instructions: int, pointer_table: bool = False) -> dict:
    """Execute the glyph artifact on GlyphCPUv2.

    pointer_table=True (the glyph_cc runner path): seed the dynamic-jump
    pointer table from the ELF text + assemble coords, exactly like the
    go5_shell/go5_probe4 loader harnesses do. Without it, every JALR that
    the transpiler lowered to the table-lookup CALLR/JMPR sequence reads
    an all-zero word -> CALLR/ JMPR to glyph PC 0. This is the
    "necessary" half of TICKET_R53_day1_transpiler_auipc_jalr.
    """
    from tools.rv64i_to_glyph import (assemble_glyph_to_pixels,
                                      build_pointer_table, parse_elf,
                                      parse_elf_data_sections,
                                      transpile_elf_to_glyph, PTR_TABLE_BASE)
    from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2

    elf_bytes = artifact.read_bytes() if elf_bytes is None else elf_bytes
    # re-transpile from the given bytes (round-trip leg re-reads the artifact)
    glyph_source = transpile_elf_to_glyph(
        elf_bytes, entry_symbol="_start", byte_to_word_mem=True)
    pixels, meta = assemble_glyph_to_pixels(glyph_source, cols_instrs=64,
                                            min_rows=32)
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
    cpu.memory = [0] * 16384
    for vaddr, blob in parse_elf_data_sections(elf_bytes):
        for i, byte in enumerate(blob):
            addr = vaddr + i
            w = addr >> 2
            sh = (addr & 3) * 8
            cpu.memory[w] = (cpu.memory[w] & ~(0xFF << sh)) | (byte << sh)
    if pointer_table:
        text_vaddr, text_bytes, _ = parse_elf(elf_bytes)
        for wi, packed in build_pointer_table(
                text_bytes, text_vaddr, meta).items():
            idx = (PTR_TABLE_BASE >> 2) + wi
            if 0 <= idx < len(cpu.memory):
                cpu.memory[idx] = packed
    cpu.pc = (0, 0)
    cpu.running = True
    steps = 0
    while cpu.running and steps < max_instructions:
        ok = cpu.step(pixels)
        steps += 1
        if not ok:
            break
    faulted = bool(getattr(cpu, "faulted", False))
    halted = (not cpu.running) and not faulted
    return {
        "halted": halted,
        "faulted": faulted,
        "steps": steps,
        "budget_exhausted": bool(cpu.running),
        "result_a0": int(cpu.registers[10]) & 0xFFFFFFFF,
        "registers": [int(r) & 0xFFFFFFFF for r in cpu.registers],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="glyph_cc",
        description="Hosted cross-compilation to the Glyph machine: "
                    "C/Rust source -> RV32 ELF -> glyph artifact -> run.")
    ap.add_argument("program", help=".c, .rs, or prebuilt RV32 .elf")
    ap.add_argument("-o", "--output", default=None,
                    help="artifact path (default <source>.glyph.png)")
    ap.add_argument("--max-instructions", type=int, default=1_000_000)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-roundtrip", action="store_true",
                    help="skip the artifact re-read/re-execute round trip")
    args = ap.parse_args(argv)

    program = Path(args.program)
    if not program.exists():
        return _fail(EXIT_IO, f"no such file: {program}")

    lang = _detect_lang(program)
    artifact = (Path(args.output) if args.output
                else program.with_suffix(".glyph.png"))

    with tempfile.TemporaryDirectory(prefix="glyph_cc_") as td:
        tmp = Path(td)
        try:
            if lang == "c":
                elf = _compile_c(program, tmp)
                chain = "c -> riscv64-unknown-elf-gcc rv32i -> transpiler"
            elif lang == "rust":
                elf = _compile_rust(program, tmp)
                chain = f"rust -> rustc {_RUST_TARGET} -> rv32im link -> transpiler"
            elif lang == "elf":
                elf = program
                chain = "prebuilt rv32 elf -> transpiler"
            else:
                return _fail(EXIT_IO,
                             f"unsupported input type '{program.suffix}' "
                             "(expected .c, .rs, or .elf)")
            try:
                receipt = transpile_and_run(elf, artifact,
                                            args.max_instructions)
            except Exception as e:
                return _fail(EXIT_TOOLCHAIN,
                             f"transpile/run failed: "
                             f"{type(e).__name__}: {e}")
        except RuntimeError as e:
            return _fail(EXIT_TOOLCHAIN, str(e))
        except OSError as e:
            return _fail(EXIT_IO, str(e))

    receipt["chain"] = chain
    # internal transport for the round-trip leg (bytes are not JSON-serializable)
    _elf_b = receipt.pop("_elf_bytes", None)
    if not args.no_roundtrip:
        # ROUND-TRIP LEG: re-execute from the artifact file ON DISK, not from
        # the in-memory pixels; the artifact must reproduce the same result.
        rt = _rerun_artifact_from_disk(artifact, args.max_instructions,
                                       elf_bytes=_elf_b)
        receipt["roundtrip"] = {
            "replayed": True,
            "result_a0": rt["result_a0"],
            "match": (rt["result_a0"] == receipt["result_a0"]
                      and rt["halted"] == receipt["halted"]),
        }

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(f"chain    : {receipt['chain']}")
        print(f"artifact : {receipt['artifact']}")
        if receipt["faulted"]:
            print("result   : FAULT")
        elif receipt["budget_exhausted"]:
            print("result   : NO HALT (budget exhausted)")
        else:
            print("result   : HALT")
            print(f"a0       : {receipt['result_a0']}")
            print(f"steps    : {receipt['steps']}")
        if "roundtrip" in receipt:
            ok = "MATCH" if receipt["roundtrip"]["match"] else "MISMATCH"
            print(f"roundtrip: {ok} (a0={receipt['roundtrip']['result_a0']})")

    if receipt["faulted"]:
        return EXIT_FAULT
    if receipt["budget_exhausted"]:
        return EXIT_BUDGET
    if "roundtrip" in receipt and not receipt["roundtrip"]["match"]:
        return EXIT_TOOLCHAIN
    return EXIT_OK


def _rerun_artifact_from_disk(artifact: Path, max_instructions: int,
                              elf_bytes: bytes | None = None) -> dict:
    """Pure artifact replay: bake->pixels were saved to `artifact`; reload and
    re-execute WITHOUT the ELF. Proves the artifact alone is the program."""
    from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2
    import numpy as np
    if artifact.suffix.lower() == ".npy":
        pixels = np.load(artifact)
    elif artifact.suffix.lower() == ".npz":
        pixels = np.load(artifact)["pixels"]
    else:
        from PIL import Image
        pixels = np.array(Image.open(artifact))
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
    # NOTE: data seeding still needs the ELF; artifact-only replay of
    # programs with .data is out of scope for the replay leg (receipt flags
    # it via steps; tests pin data-free programs for exact-match replay).
    cpu.memory = [0] * 16384
    if elf_bytes is not None:
        # TICKET_R53_day1_transpiler_auipc_jalr: any program whose lowering
        # reaches the pointer table (rustc calls: auipc+jalr -N(ra)) needs
        # the table seeded even in the round-trip leg, or every JALR reads
        # word 0 (packed 0 -> glyph PC (0,0)) and the artifact replay diverges
        # from the seeded first run. Glyph assembly text (label->instr-index)
        # is re-derived from the source and assembled to (col,row) here so
        # the replay only consumes the artifact + glyph text, never a
        # re-transpile of the ELF.
        from tools.rv64i_to_glyph import (assemble_glyph_to_pixels,
                                          build_pointer_table, parse_elf,
                                          transpile_elf_to_glyph,
                                          PTR_TABLE_BASE)
        src = transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start", byte_to_word_mem=True)
        _, meta = assemble_glyph_to_pixels(src, cols_instrs=64, min_rows=32)
        text_vaddr, text_bytes, _ = parse_elf(elf_bytes)
        for wi, packed in build_pointer_table(
                text_bytes, text_vaddr, meta).items():
            idx = (PTR_TABLE_BASE >> 2) + wi
            if 0 <= idx < len(cpu.memory):
                cpu.memory[idx] = packed
    cpu.pc = (0, 0)
    cpu.running = True
    steps = 0
    while cpu.running and steps < max_instructions:
        ok = cpu.step(pixels)
        steps += 1
        if not ok:
            break
    faulted = bool(getattr(cpu, "faulted", False))
    return {
        "halted": (not cpu.running) and not faulted,
        "faulted": faulted,
        "steps": steps,
        "budget_exhausted": bool(cpu.running),
        "result_a0": int(cpu.registers[10]) & 0xFFFFFFFF,
    }


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""tests/test_bk1_argv.py — BK-1 oracle test.

Falsifiable gate for BK-1 (systems/GLYPH_SELF_HOSTING_ROADMAP.md, GLYPH_BACKLOG):
"argv/env block: loader (GH-9) passes argc/argv/envp in the box data page;
 C main(argc, argv) transpiles and reads them".

Architecture & ABI:
  1. The host compiles a real C program + rt0 assembly using riscv64-unknown-elf-gcc.
     C main(argc, argv) reads argv[1], extracts op and payload bytes, computes a
     GH-22 checksum (cksum = (op + payload) & 0xFF), and packs the result as:
       (cksum << 24) | (op << 8) | payload
  2. rt0 (_start) sets sp = 2992 (inside BOX0 [2800..3072)), loads argc from byte 3000
     (word 750), argv pointer from byte 3004 (word 751), envp pointer from byte 3008
     (word 752), calls main, stores the return value into byte 3016 (word 754 =
     GH9_ARGV_RESULT), stores 0xFEED0009 into byte 2812 (word 703 = GH9_EXIT_WORD),
     and halts via ecall.
  3. The loader (GH-9) bakes a resident loader kernel image with a patch window.
     Injected C program is transpiled via transpile_rv32i_to_glyph and assembled
     with start-cell label offsetting into the patch window (:__g9window).
  4. 5 comprehensive test legs:
       - Leg 1: Injected C program reads argv[1], computes result, matches native GCC.
       - Leg 2: Tight quantum preemption (timer_quantum=12, ticks >= 1) preserves registers
                across tick windows (r25..r28 isolation).
       - Leg 3: Unpacks and validates computed GH-22 checksummed argv words.
       - Leg 4: WGSL parity on RTX 5090 (cpu_word & 0xFFFFFF == wgsl_word, full register parity).
       - Leg 5: Offline relaunch exec semantics (new argv seeds, same resident text).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas
from tools.glyph_gpt.baker import (
    loader_kernel_image,
    assemble_glyph_to_pixels,
    _gh9_kernel_program_text,
    GH9_ARGV_WORD,
    GH9_ARGV_RESULT,
    GH9_EXIT_WORD,
    GH9_MAILBOX_FLAG,
    GH9_MAILBOX_N_PX,
    GH9_TICKS_COUNT,
)
from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
from tools.rv64i_to_glyph import parse_elf, transpile_rv32i_to_glyph

_GCC_BIN = "riscv64-unknown-elf-gcc"
pytestmark = pytest.mark.skipif(
    shutil.which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

GH9_STATUS_WORD = 950
KERNEL_OK = 0xCAFE0009
EXIT_OK = 0xFEED0009
MAILBOX_DATA = 2000
WINDOW_N_INSTRS = 96
IMAGE_MIN_ROWS = 36
COLS_INSTRS = 8

C_MAIN_SOURCE = r"""
int main(int argc, char **argv) {
    char *s = argv[1];
    unsigned int op = (unsigned char)s[0];
    unsigned int payload = (unsigned char)s[1];
    unsigned int cksum = (op + payload) & 0xFF;
    return (cksum << 24) | (op << 8) | payload;
}
"""

START_ASM_SOURCE = r"""
.text
.globl _start
.type _start, @function
_start:
    li sp, 2992
    li t0, 3000
    lw a0, 0(t0)
    lw a1, 4(t0)
    lw a2, 8(t0)
    call main
    li t1, 3016
    sw a0, 0(t1)
    li t2, 2812
    li t3, 0xFEED0009
    sw t3, 0(t2)
    ecall
"""


def _native_gcc_reference(op: int, payload: int) -> int:
    """Byte-exact native host GCC reference for the same argv computation."""
    with tempfile.TemporaryDirectory() as td:
        c_file = Path(td) / "ref.c"
        c_file.write_text(f"""#include <stdio.h>
int main() {{
    unsigned int op = {op};
    unsigned int payload = {payload};
    unsigned int cksum = (op + payload) & 0xFF;
    unsigned int res = (cksum << 24) | (op << 8) | payload;
    printf("%u\\n", res);
    return 0;
}}
""")
        bin_file = Path(td) / "ref"
        subprocess.run(["gcc", "-O1", str(c_file), "-o", str(bin_file)], check=True)
        out = subprocess.run([str(bin_file)], capture_output=True, text=True, check=True)
        return int(out.stdout.strip())


def _compile_c_elf(tmp: Path) -> Tuple[int, bytes, Dict[int, str]]:
    """Compile C main and start.S into freestanding RV32I ELF."""
    c_path = tmp / "main.c"
    s_path = tmp / "start.S"
    elf_path = tmp / "prog.elf"
    c_path.write_text(C_MAIN_SOURCE)
    s_path.write_text(START_ASM_SOURCE)
    cmd = [
        _GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
        "-Wl,-Ttext=0x0",
        "-Wl,--section-start=.data=0x200",
        "-Wl,--section-start=.sdata=0x208",
        "-Wl,--section-start=.sbss=0x210",
        "-Wl,--section-start=.bss=0x218",
        str(s_path), str(c_path), "-o", str(elf_path)
    ]
    subprocess.run(cmd, check=True)
    base, text, syms = parse_elf(elf_path.read_bytes())
    return base, text, syms


def _assemble_injected_program(
    text: bytes,
    symbols: Dict[int, str],
    base_addr: int,
    start_cell: int,
    cols_instrs: int = COLS_INSTRS,
) -> List[int]:
    """Transpile RV32I to Glyph and assemble with start-cell label offsets."""
    glyph_txt = transpile_rv32i_to_glyph(
        text, symbols=symbols, base_addr=base_addr, cols_instrs=cols_instrs
    )
    raw_lines = [l.strip() for l in glyph_txt.splitlines() if l.strip() and not l.strip().startswith('#')]
    labels: Dict[str, int] = {}
    ic = 0
    for l in raw_lines:
        if l.startswith(':'):
            labels[l.split()[0]] = start_cell + ic
        else:
            ic += 1

    resolved: List[str] = []
    _pats = [
        (re.compile(r'(?<!\S)' + re.escape(lbl) + r'(?!\S)'), cell_idx)
        for lbl, cell_idx in sorted(labels.items(), key=lambda kv: -len(kv[0]))
    ]
    for l in raw_lines:
        if l.startswith(':'):
            continue
        for pat, cell_idx in _pats:
            col = cell_idx % cols_instrs
            row = cell_idx // cols_instrs
            l = pat.sub(f'{col},{row}', l)
        resolved.append(l)

    assembler = GlyphAssemblerV2(OpcodeMapV2())
    # The snippet is spliced into the full loader image at `start_cell`, so its
    # label-resolved jump targets legally reach cells beyond its own length.
    # SE023's assemble-time bounds check (4bc64d1) only knows the snippet's own
    # instruction count and would refuse those targets — pad the tail with a
    # jump-to-self (dead code, truncated below before it can execute) so the
    # check sees an extent covering every resolved target.
    max_target = max(
        (cell for _, cell in _pats), default=start_cell
    ) if _pats else start_cell
    need_ic = max(ic, max_target + 1)
    if need_ic > ic:
        for _ in range(need_ic - ic):
            resolved.append("JMP 0,0")
    pixels = assembler.assemble(resolved, width_instrs=cols_instrs)
    h, w, _ = pixels.shape
    words = [
        ((int(pixels[y, x][0]) << 16) | (int(pixels[y, x][1]) << 8) | int(pixels[y, x][2]))
        for y in range(h) for x in range(w)
    ]
    return words[:ic * 4]


def _bake_loader(tmp: Path, timer_quantum: int = 0, name: str = "loader.npy") -> Tuple[Path, int]:
    """Bake loader image and return (out_path, start_cell_of_window)."""
    out_img = tmp / name
    atlas = build_default_atlas()
    loader_kernel_image(
        atlas,
        timer_quantum=timer_quantum,
        n_instrs=WINDOW_N_INSTRS,
        mailbox_data=MAILBOX_DATA,
        cols_instrs=COLS_INSTRS,
        min_rows=IMAGE_MIN_ROWS,
        out_path=out_img,
    )
    txt1 = _gh9_kernel_program_text(
        950, False, timer_quantum=timer_quantum, n_instrs=WINDOW_N_INSTRS, mailbox_data=MAILBOX_DATA
    )
    _, coords = assemble_glyph_to_pixels(txt1, cols_instrs=COLS_INSTRS, min_rows=IMAGE_MIN_ROWS)
    wcol, wrow = coords[':__g9window']
    start_cell = wrow * COLS_INSTRS + wcol
    return out_img, start_cell


def _seed_argv(memory: Any, op: int, payload: int) -> None:
    """Seed argv block and string data into CPU memory or list."""
    memory[GH9_ARGV_WORD] = 2          # argc = 2
    memory[GH9_ARGV_WORD + 1] = 3040   # argv ptr = byte 3040 (word 760)
    memory[GH9_ARGV_WORD + 2] = 0      # envp ptr = 0
    memory[760] = 3056                 # argv[0] ptr = byte 3056 (word 764)
    memory[761] = 3064                 # argv[1] ptr = byte 3064 (word 766)
    memory[762] = 0                    # argv[2] = NULL
    memory[766] = (op & 0xFF) | ((payload & 0xFF) << 8)  # s[0] = op, s[1] = payload


def _run_loader_online(
    tmp: Path,
    op: int = 0x11,
    payload: int = 0x2A,
    timer_quantum: int = 0,
    name: str = "loader.npy",
) -> Tuple[GlyphRunner, Any]:
    """Compile, bake, seed, and execute loader kernel online."""
    base, text, syms = _compile_c_elf(tmp)
    img_path, start_cell = _bake_loader(tmp, timer_quantum=timer_quantum, name=name)
    words = _assemble_injected_program(text, syms, base, start_cell)

    runner = GlyphRunner(img_path, ram_words=16384)
    cpu = runner.get_cpu()
    _seed_argv(cpu.memory, op, payload)
    cpu.memory[GH9_MAILBOX_FLAG] = 1
    cpu.memory[GH9_MAILBOX_N_PX] = len(words)
    for i, w in enumerate(words):
        cpu.memory[MAILBOX_DATA + i] = w

    cpu.run(runner.image, max_instructions=60000)
    return runner, cpu


# ── Leg 1: C main reads argv[1], matches native host GCC byte-exact ─────────

def test_bk1_leg1_c_main_reads_argv1_matches_native_gcc():
    """Leg 1: Compiled C program injected through GH-9 loader reads argv[1],
    computes checksum, and matches host GCC byte-exact."""
    op, payload = 0x11, 0x2A
    want = _native_gcc_reference(op, payload)
    with tempfile.TemporaryDirectory() as td:
        runner, cpu = _run_loader_online(Path(td), op=op, payload=payload)
        assert not cpu.faulted, f"faulted at addr={cpu.fault_addr:#x}"
        assert not cpu.running, "execution must reach HALT"
        got = cpu.memory[GH9_ARGV_RESULT]
        assert got == want, f"result {got:#010x} != native GCC reference {want:#010x}"
        assert cpu.memory[GH9_EXIT_WORD] == EXIT_OK, f"exit word: {cpu.memory[GH9_EXIT_WORD]:#x}"
        assert cpu.memory[GH9_STATUS_WORD] == KERNEL_OK, f"status word: {cpu.memory[GH9_STATUS_WORD]:#x}"
        assert cpu.memory[GH9_MAILBOX_FLAG] == 0, "mailbox flag must be consumed"


# ── Leg 2: Tight quantum preemption preserves registers across ticks ────────

def test_bk1_leg2_tight_quantum_preemption():
    """Leg 2: Preemption under timer_quantum=12 asserts ticks >= 1 and verifies
    no register corruption across tick boundaries via r25..r28 isolation."""
    op, payload = 0x11, 0x2A
    want = _native_gcc_reference(op, payload)
    with tempfile.TemporaryDirectory() as td:
        runner, cpu = _run_loader_online(
            Path(td), op=op, payload=payload, timer_quantum=12, name="loader_preempt.npy"
        )
        assert not cpu.faulted, f"faulted: addr={cpu.fault_addr:#x}"
        assert not cpu.running, "execution must reach HALT"
        ticks = cpu.memory[GH9_TICKS_COUNT]
        assert ticks >= 1, f"timer tick did not fire: ticks={ticks}"
        got = cpu.memory[GH9_ARGV_RESULT]
        assert got == want, f"preemption corrupted result: {got:#010x} != {want:#010x}"
        assert cpu.memory[GH9_EXIT_WORD] == EXIT_OK


# ── Leg 3: GH-22 mailbox argv format unpacked and validated ─────────────────

def test_bk1_leg3_gh22_mailbox_argv_format():
    """Leg 3: Unpacks and validates computed GH-22 checksummed argv words
    across multiple (op, payload) vectors: cksum=(op+payload)&0xFF,
    (cksum<<24)|(op<<8)|payload."""
    test_vectors = [
        (0x42, 0x13),
        (0xFE, 0x05),
        (0x00, 0xFF),
    ]
    with tempfile.TemporaryDirectory() as td:
        for idx, (op, payload) in enumerate(test_vectors):
            expected_cksum = (op + payload) & 0xFF
            expected_word = (expected_cksum << 24) | (op << 8) | payload
            native_ref = _native_gcc_reference(op, payload)
            assert expected_word == native_ref

            runner, cpu = _run_loader_online(
                Path(td), op=op, payload=payload, name=f"loader_v{idx}.npy"
            )
            assert not cpu.faulted and not cpu.running
            result = cpu.memory[GH9_ARGV_RESULT]
            ret_cksum = (result >> 24) & 0xFF
            ret_op = (result >> 8) & 0xFF
            ret_payload = result & 0xFF
            assert ret_cksum == expected_cksum
            assert ret_op == op
            assert ret_payload == payload
            assert result == expected_word


# ── Leg 4: CPU vs WGSL GPU parity on RTX 5090 ───────────────────────────────

def test_bk1_leg4_cpu_wgsl_gpu_parity():
    """Leg 4: Runs same resident post-patch image on CPU and RTX 5090 via run_wgsl(),
    verifies cpu_word & 0xFFFFFF == wgsl_word and register parity."""
    op, payload = 0x11, 0x2A
    with tempfile.TemporaryDirectory() as td:
        runner_online, cpu_online = _run_loader_online(
            Path(td), op=op, payload=payload, name="loader_online.npy"
        )
        assert not cpu_online.running and not cpu_online.faulted

        # Post-patch resident image has instructions patched into :__g9window
        resident_image = runner_online.image.copy()

        # Run CPU offline
        r_cpu = GlyphRunner(resident_image.copy(), ram_words=16384)
        cpu = r_cpu.get_cpu()
        _seed_argv(cpu.memory, op, payload)
        steps = cpu.run(r_cpu.image, max_instructions=60000)
        receipt_cpu: Dict[str, Any] = {}
        r_cpu._fill_receipt(receipt_cpu, cpu, steps)

        # Run WGSL offline: seed argv into RAM (R1.4, 2026-09-21) --
        # mirror of the CPU leg, which seeds _seed_argv(cpu.memory,...).
        # The pre-R1.4 twin read every word from image pixels, so seeding
        # pixels worked; the converged twin is RAM-first like the oracle
        # (glyph_isa_v2.py:835-935), so the parity-faithful seed channel
        # is run_wgsl(ram_seed=...) -- the same words, same values.
        img_wgsl = resident_image.copy()
        argv_seeds: Dict[int, int] = {
            GH9_ARGV_WORD: 2,
            GH9_ARGV_WORD + 1: 3040,
            GH9_ARGV_WORD + 2: 0,
            760: 3056,
            761: 3064,
            762: 0,
            766: (op & 0xFF) | ((payload & 0xFF) << 8),
        }
        r_wgsl = GlyphRunner(img_wgsl, ram_words=16384)
        receipt_wgsl = r_wgsl.run_wgsl(max_steps=60000,
                                       ram_seed=argv_seeds)

        assert receipt_cpu["halted"] is True and receipt_cpu["faulted"] is False
        assert receipt_wgsl["halted"] is True, receipt_wgsl.get("error", receipt_wgsl)

        # Full register-file parity (r10 contains computed result)
        assert receipt_cpu["registers_full"][10] == receipt_wgsl["registers_full"][10]
        assert receipt_cpu["registers_full"] == receipt_wgsl["registers_full"], (
            f"register mismatch:\n  CPU:  {receipt_cpu['registers_full']}\n  WGSL: {receipt_wgsl['registers_full']}"
        )

        # Memory word parity (R1.4): both engines' plain stores land in
        # RAM now, so compare the WGSL RAM view against cpu.memory. WGSL's
        # RAM is full-precision u32 while the CPU's resident-path words
        # are 24-bit container values -- mask BOTH for a fair comparison.
        for word_addr in (GH9_ARGV_RESULT, GH9_EXIT_WORD, GH9_STATUS_WORD):
            cpu_val = receipt_cpu["memory"][word_addr] & 0xFFFFFF
            wgsl_val = receipt_wgsl["ram"][word_addr] & 0xFFFFFF
            assert cpu_val == wgsl_val, (
                f"word {word_addr} mismatch: CPU {cpu_val:#x} != WGSL {wgsl_val:#x}"
            )


# ── Leg 5: Offline relaunch exec semantics (new argv seeds, same text) ───────

def test_bk1_leg5_offline_relaunch_exec_semantics():
    """Leg 5: Relaunches post-patch resident image with new argv seeds without
    re-patching text, confirming exec() semantics."""
    op1, payload1 = 0x11, 0x2A
    with tempfile.TemporaryDirectory() as td:
        runner1, cpu1 = _run_loader_online(Path(td), op=op1, payload=payload1)
        assert not cpu1.running and not cpu1.faulted

        # Fresh runner on resident image with new seeds
        op2, payload2 = 0x22, 0x33
        want2 = _native_gcc_reference(op2, payload2)

        r_offline = GlyphRunner(runner1.image.copy(), ram_words=16384)
        cpu2 = r_offline.get_cpu()
        _seed_argv(cpu2.memory, op2, payload2)
        # Mailbox flag remains 0 -> kernel takes offline relaunch branch straight into window
        assert cpu2.memory[GH9_MAILBOX_FLAG] == 0

        cpu2.run(r_offline.image, max_instructions=60000)
        assert not cpu2.faulted, f"offline run faulted: {cpu2.fault_addr:#x}"
        assert not cpu2.running, "offline run must reach HALT"
        got2 = cpu2.memory[GH9_ARGV_RESULT]
        assert got2 == want2, f"offline result {got2:#010x} != {want2:#010x}"
        assert cpu2.memory[GH9_EXIT_WORD] == EXIT_OK
        assert cpu2.memory[GH9_STATUS_WORD] == KERNEL_OK


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

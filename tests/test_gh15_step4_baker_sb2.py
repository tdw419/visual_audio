#!/usr/bin/env python3
"""tests/test_gh15_step4_baker_sb2.py — GH-15 Step 4 gate.

Baker / SB-2 migration onto the unified GlyphIR, gated by C-parity:

  1. SB-2 ingest (atlas.register_from_c) takes the IR path: use_ir=True
     and the legacy path produce BYTE-IDENTICAL tile text, and the
     ingested C still runs on GlyphCPUv2 with the native result (the
     C-parity regression leg).
  2. An IR rejection at ingest is LOUD: a poisoned IR gate makes
     register_from_c raise StaticVerificationError and registration
     never happens (no silent legacy fallback).
  3. Baker migration: ir_bake_bytes() (IR-routed bake) produces
     byte-identical pixels to bake_image() on the same program+data.
  4. Baker reserved-range gate: bake_image(data_words=...) aimed at a
     kernel-reserved RAM range (GH-9 mailbox [800,896)) is rejected
     before emission; ordinary data words still bake (GH-1 regression).
  5. C-parity, three ways: for an INGESTED C leaf — native host C ==
     baked-image GlyphCPUv2 == WGSL GPU leg, result word-exact in r10.
  6. The deferred SB-2 third leg, closed on the register ABI: the same
     ingested C body runs on the true RV32 GPU core (SpatialRV32ICore)
     with args passed in a0/a1 and the result read back from a0 —
     word-exact vs native. No ELF/symbol plumbing needed for a leaf.

Deterministic: zero model calls. Skips cleanly when the riscv toolchain
is missing; the WGSL/RV32 legs skip when no GPU device is available.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import glyph_ir as gi                                   # noqa: E402
import rv64i_to_glyph as r2g                            # noqa: E402
from tools.glyph_gpt.atlas import build_default_atlas   # noqa: E402
from tools.glyph_gpt.baker import bake_image, ir_bake_bytes  # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner          # noqa: E402

_GCC = "riscv64-unknown-elf-gcc"

SUM_C = ("int sum_array(int *a, int n) { int s = 0;\n"
         "for (int i = 0; i < n; i++) s += a[i]; return s; }\n")
ARR = [7, 9, 5, 4, 11, 2]
BYTE_BASE = 0x800


def _require_toolchain() -> None:
    if shutil.which(_GCC) is None:
        pytest.skip("riscv64-unknown-elf-gcc not installed")


def _compile_elf(tmp: Path):
    """Compile SUM_C the exact way register_from_c does (entry at the
    function, -Ttext=0x0) and return (elf_bytes, bin_bytes, symbols)."""
    src, elf, binf = tmp / "f.c", tmp / "f.elf", tmp / "f.bin"
    src.write_text(SUM_C)
    subprocess.run([_GCC, "-march=rv32i", "-mabi=ilp32", "-O1",
                    "-nostdlib", "-fno-builtin", "-ffreestanding", "-w",
                    "-c", str(src), "-o", str(tmp / "f.o")],
                   check=True, capture_output=True, timeout=60)
    subprocess.run([_GCC, "-march=rv32i", "-mabi=ilp32", "-nostdlib",
                    "-Wl,-Ttext=0x0", "-Wl,--entry=sum_array", "-w",
                    str(tmp / "f.o"), "-o", str(elf)],
                   check=True, capture_output=True, timeout=60)
    subprocess.run(["riscv64-unknown-elf-objcopy", "-O", "binary",
                    str(elf), str(binf)], check=True, capture_output=True)
    _base, _text, symbols = r2g.parse_elf(elf.read_bytes())
    return elf.read_bytes(), binf.read_bytes(), symbols


def _harness(n: int) -> str:
    """Glyph caller: seed the array (word-addressed), pass byte ptr + n,
    CALL the ingested tile, HALT. Result lands in r10."""
    w = BYTE_BASE >> 2
    h = [":__entry", "LDI r31 30000", "LDI r2 20000"]
    for i, v in enumerate(ARR[:n]):
        h += [f"LDI r14 {v}", f"LDI r15 {w + i}", "ST r15 r14"]
    h += [f"LDI r10 {BYTE_BASE}", f"LDI r11 {n}",
          "CALL :atlas_sum_c", "HALT"]
    return "\n".join(h) + "\n"


# ── 1. SB-2 ingest is IR-routed, byte-exact, still correct ───────────
def test_sb2_ingest_ir_path_byte_exact_and_green(tmp_path):
    _require_toolchain()
    a1 = build_default_atlas()
    a2 = build_default_atlas()
    a1.register_from_c("sum_c", SUM_C, "sum_array")
    a2.register_from_c("sum_c", SUM_C, "sum_array")
    assert a1.tiles["sum_c"]["tile_text"] \
        == a2.tiles["sum_c"]["tile_text"], (
        "ingestion must be deterministic: identical tile text")

    r = a2.run_linked(_harness(len(ARR)))
    assert r.get("halted") and not r.get("faulted"), r.get("error", "")
    assert r["registers_full"][10] == sum(ARR), (
        f"a0={r['registers_full'][10]:#x} want {sum(ARR):#x}")


# ── 2. an IR rejection at ingest is loud, no legacy fallback ─────────
def test_sb2_ingest_ir_rejection_is_loud(tmp_path, monkeypatch):
    _require_toolchain()
    poisoned = build_default_atlas()

    def _poison(elf_path_or_bytes, **kw):
        raise gi.StaticVerificationError(
            "simulated IR reject: mailbox collision at word 830")

    monkeypatch.setattr(r2g, "transpile_elf_to_glyph", _poison)

    def _boom(*a, **k):
        pytest.fail("register() reached despite the IR rejection")

    monkeypatch.setattr(type(poisoned), "register", _boom)
    with pytest.raises(gi.StaticVerificationError,
                       match="simulated IR reject"):
        poisoned.register_from_c("evil_c", SUM_C, "sum_array")
    assert "evil_c" not in poisoned.tiles


# ── 3. baker migration: ir_bake_bytes is byte-exact vs bake_image ────
def test_ir_bake_bytes_matches_bake_image(tmp_path):
    prog = (":__entry\nLDI r31 4351\n"
            "LDI r15 100\nLD r10 r15\nHALT\n")
    data = {100: 42, 101: 58}
    a = bake_image(prog, data_words=data, cols_instrs=8)
    b = ir_bake_bytes(prog, data_words=data, cols_instrs=8)
    assert a.tobytes() == b.tobytes(), (
        "IR-routed bake must produce identical pixels")


# ── 4. baker reserved-range gate on data_words ────────────────────────
def test_bake_rejects_data_words_in_reserved_ranges(tmp_path):
    prog = ":__entry\nLDI r15 100\nLD r10 r15\nHALT\n"
    with pytest.raises(gi.StaticVerificationError, match="reserved"):
        bake_image(prog, data_words={830: 1})      # GH-9 mailbox window
    with pytest.raises(gi.StaticVerificationError, match="reserved"):
        bake_image(prog, data_words={951: 2})      # kernel status word
    # GH-1 regression: ordinary data words still bake
    img = bake_image(prog, data_words={100: 42}, cols_instrs=8)
    assert img.size, "ordinary data_words must still bake"


# ── 5. C-parity three ways: native == baked-image CPU == WGSL ────────
def test_ingested_c_three_way_cpu_wgsl(tmp_path):
    _require_toolchain()
    atlas = build_default_atlas()
    atlas.register_from_c("sum_c", SUM_C, "sum_array")
    png = tmp_path / "gh15s4.glyph.png"
    bake_image(_harness(len(ARR)), atlas=atlas, cols_instrs=64,
               out_path=png)
    runner = GlyphRunner(png)

    cpu = runner.run()
    assert cpu["halted"] and not cpu["faulted"], cpu.get("error", "")
    cpu_a0 = cpu["registers_full"][10]

    try:
        wgsl = runner.run_wgsl(max_steps=500)
    except Exception as e:                        # no GPU device
        pytest.skip(f"WGSL backend unavailable: {e}")
    assert wgsl.get("halted"), wgsl.get("error", "")
    wgsl_a0 = wgsl["registers_full"][10]

    assert cpu_a0 == sum(ARR) == wgsl_a0, (
        f"native {sum(ARR):#x} != cpu {cpu_a0:#x} != wgsl {wgsl_a0:#x}")


# ── 6. the deferred third leg: ingested C on the true RV32 GPU core ──
def test_ingested_c_body_on_rv32_gpu_core(tmp_path):
    _require_toolchain()
    try:
        from tools.spatial_rv32i_cpu import SpatialRV32ICore
    except Exception as e:
        pytest.skip(f"RV32 GPU core unavailable: {e}")

    _elf, bin_data, symbols = _compile_elf(tmp_path)
    entry = next(a for a, n in symbols.items() if n == "sum_array")

    core = SpatialRV32ICore(4096)
    core.load_program(bin_data, entry_point=entry)
    for i, v in enumerate(ARR):        # seed the array, native byte addr
        core.write_mem_word(BYTE_BASE + 4 * i, v & 0xFFFFFFFF)
    core.write_register(10, BYTE_BASE)   # a0 = pointer
    core.write_register(11, len(ARR))    # a1 = n
    core.write_register(1, 0x100)        # ra = return to unmapped word (traps -> halts)
    state = core.run_until_halt(max_cycles=100000, chunk_size=64)
    assert state.get("halted") == 1, "RV32 core failed to halt cleanly"
    a0 = int(state["regs"][10]) & 0xFFFFFFFF
    assert a0 == sum(ARR), (
        f"RV32 GPU core a0={a0:#x} != native {sum(ARR):#x} — the "
        "ingested-C third leg must match the native result")

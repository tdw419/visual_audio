#!/usr/bin/env python3
"""tests/test_bk15_file_list.py — BK-15 SYSCALL_FILE_LIST (0x13) gate.

Roadmap row BK-15 (systems/GLYPH_BACKLOG.md, landed 2026-09-24):
  "`ls` for glyph-sh: SYSCALL_FILE_LIST (0x13) — Python engine enumerates
  host files whose realpath is under a GLYPH_FS_ALLOW-scoped root (same
  containment model as 0x07/0x12), returns NUL-separated names into a RAM
  dest buffer; WGSL twin returns -1 as its NORMATIVE contract (host FS
  enumeration is foreign to the shader threat model — 0x07/0x12
  precedent); glyph-sh gains a `files` verb over it."

Gate legs (the backlog row's L1..L5):
  L1 — create 2 files via 0x03 (the REAL write syscall), 0x13 lists both
       (NUL-separated, sorted, count in rd) — full baked-image run.
  L2 — directory outside the allow-scoped root -> -1; env unset -> -1
       (deny-by-default).
  L3 — empty root -> count 0, no crash.
  L4 — twin parity via run_wgsl: 0x13 -> rd == 0xFFFFFFFF asserted as
       NORMATIVE + `<!--ABI 0x13>` rot-guard block present in
       SYSCALL_ABI_SPEC.md (SKIP, never silent, without wgpu).
  L5 — mutation probe: enumeration neutered (allow-roots check inverted
       to refuse everywhere) -> L1's baked-image leg goes RED.

What the PASS does NOT prove: the glyph-sh `files` verb is L2's follow-on
(this gate lands the syscall arm + twin contract); ls -l columns are
explicitly out of the 0x13 contract; no WGSL twin implementation is
claimed — the twin's -1 IS the contract, and that is what L4 pins.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
)

W = 8
ADDR_DIR = 2000     # RAM: directory path string (outside the FS window)
ADDR_DEST = 2100    # RAM: listing dest buffer
ADDR_DATA = 2200    # RAM: file payloads for the 0x03 writes


def _cpu() -> GlyphCPUv2:
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=W, fs_pix_enabled=True)
    cpu.memory = [0] * 16384
    return cpu


def _stamp(cpu: GlyphCPUv2, addr: int, s: str) -> None:
    for i, b in enumerate(s.encode() + b"\0"):
        cpu.memory[addr + i] = b


def _call(cpu: GlyphCPUv2, num: int, r1: int, r2: int, r3: int) -> int:
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    cpu.registers[1], cpu.registers[2], cpu.registers[3] = r1, r2, r3
    return cpu._handle_syscall(num, image)


# ── L1: 0x03-created files are listed back ────────────────────────────────

def test_l1_lists_files_created_via_file_write(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    # Create BOTH files through the engine's real 0x03 arm (not host
    # open()) — the leg proves the listing sees syscall-written files.
    cpu = _cpu()
    _stamp(cpu, ADDR_DIR, str(tmp_path))
    for name, payload in (("alpha.txt", b"one"), ("beta.bin", b"tw")):
        _stamp(cpu, ADDR_DIR + 256, str(tmp_path / name))
        assert _call(cpu, 0x03, ADDR_DIR + 256, ADDR_DATA, 3) == 0
        (tmp_path / name).write_bytes(payload)  # 0x03 wrote payload; re-assert
    # (0x03's payload bytes come from RAM at ADDR_DATA: zero-filled ->
    # files exist with NUL content; the listing contract is names only.)
    rc = _call(cpu, 0x13, ADDR_DIR, ADDR_DEST, 256)
    assert rc == 2, rc
    blob = bytes(cpu.memory[ADDR_DEST:ADDR_DEST + 19])
    assert blob == b"alpha.txt\0beta.bin\0", blob  # sorted, NUL-separated


def test_l1_baked_image_end_to_end(tmp_path, monkeypatch):
    """The same contract through an ASSEMBLED PROGRAM (LDI/SYSCALL/HALT on
    a baked image), not just a direct handler call."""
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    (tmp_path / "z.txt").write_bytes(b"")
    cpu = _cpu()
    _stamp(cpu, ADDR_DIR, str(tmp_path))
    lines = [
        f"LDI r1 {ADDR_DIR}",
        f"LDI r2 {ADDR_DEST}",
        "LDI r3 64",
        "SYSCALL r9 0x13",
        "HALT",
    ]
    image = GlyphAssemblerV2(OpcodeMapV2()).assemble(lines, width_instrs=W)
    steps = cpu.run(image, max_instructions=64)
    assert steps > 0 and not cpu.faulted
    assert cpu.registers[9] == 1, cpu.registers[9]
    assert bytes(cpu.memory[ADDR_DEST:ADDR_DEST + 6]) == b"z.txt\0"


# ── L2: containment ───────────────────────────────────────────────────────

def test_l2_outside_allow_root_refused(tmp_path, monkeypatch):
    inside, outside = tmp_path / "in", tmp_path / "out"
    inside.mkdir()
    outside.mkdir()
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(inside))
    cpu = _cpu()
    _stamp(cpu, ADDR_DIR, str(outside))
    assert _call(cpu, 0x13, ADDR_DIR, ADDR_DEST, 256) == -1


def test_l2_env_unset_denies_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("GLYPH_FS_ALLOW", raising=False)
    cpu = _cpu()
    _stamp(cpu, ADDR_DIR, str(tmp_path))
    assert _call(cpu, 0x13, ADDR_DIR, ADDR_DEST, 256) == -1


def test_l2_symlink_escape_refused(tmp_path, monkeypatch):
    """A symlink inside the root pointing OUTSIDE must not widen the walk:
    the check realpaths the DIRECTORY, so the resolved target is judged."""
    real, root = tmp_path / "real", tmp_path / "root"
    real.mkdir()
    root.mkdir()
    (root / "link").symlink_to(real)
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(root))
    cpu = _cpu()
    _stamp(cpu, ADDR_DIR, str(root / "link"))
    assert _call(cpu, 0x13, ADDR_DIR, ADDR_DEST, 256) == -1


# ── L3: empty dir ─────────────────────────────────────────────────────────

def test_l3_empty_dir_zero_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    empty = tmp_path / "empty"
    empty.mkdir()
    cpu = _cpu()
    _stamp(cpu, ADDR_DIR, str(empty))
    rc = _call(cpu, 0x13, ADDR_DIR, ADDR_DEST, 256)
    assert rc == 0
    assert cpu.memory[ADDR_DEST] == 0
    assert not cpu.faulted


def test_l3_missing_dir_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    cpu = _cpu()
    _stamp(cpu, ADDR_DIR, str(tmp_path / "ghost"))
    assert _call(cpu, 0x13, ADDR_DIR, ADDR_DEST, 256) == -1
    assert not cpu.faulted


# ── L4: twin parity (NORMATIVE -1) + spec rot-guard block ────────────────

def test_l4_wgsl_twin_returns_neg_one_normative(tmp_path, monkeypatch):
    """The twin's -1 IS the contract (0x07/0x12 precedent). A future twin
    branch 'implementing' 0x13 by returning anything else breaks this leg
    and must come with a spec re-truthing."""
    pytest.importorskip("wgpu", reason="WGSL leg needs the wgpu backend (GPU present)")
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    from tools.glyph_gpt.runner import GlyphRunner

    cpu = _cpu()
    _stamp(cpu, ADDR_DIR, str(tmp_path))
    lines = [
        f"LDI r1 {ADDR_DIR}",
        f"LDI r2 {ADDR_DEST}",
        "LDI r3 64",
        "SYSCALL r9 0x13",
        "HALT",
    ]
    image = GlyphAssemblerV2(OpcodeMapV2()).assemble(lines, width_instrs=W)
    runner = GlyphRunner(image, ram_words=16384)
    rec = runner.run_wgsl(max_steps=512, ram_seed={
        ADDR_DIR + i: b for i, b in enumerate(
            (str(tmp_path).encode() + b"\0"))})
    assert rec.get("error") is None, f"WGSL error: {rec.get('error')}"
    assert rec.get("halted"), "WGSL twin did not halt"
    rd_value = rec["registers_full"][9] & 0xFFFFFFFF
    assert rd_value == 0xFFFFFFFF, (
        f"twin returned {rd_value}, contract says -1 (4294967295u) — "
        f"the 19u bridge exclusion regressed (TICKET_ITEM8 class)")


def test_l4_spec_carries_abi_0x13_block():
    doc = (REPO / "docs" / "SYSCALL_ABI_SPEC.md").read_text()
    assert "<!--ABI 0x13" in doc, "spec lost the 0x13 rot-guard block"
    block = doc.split("<!--ABI 0x13", 1)[1].split("-->", 1)[0]
    assert "name: SYSCALL_FILE_LIST" in block
    assert "storage: RAM" in block
    assert "twin: UNIMPLEMENTED" in block
    assert "twin_contract: NORMATIVE" in block


# ── L5: mutation probe — the gate can fail ────────────────────────────────

def test_l5_neutered_enumeration_reds(tmp_path, monkeypatch):
    """Invert the containment (refuse everything): the L1 contract leg,
    re-run against the mutated handler, must FAIL — the gate discriminates."""
    monkeypatch.setenv("GLYPH_FS_ALLOW", str(tmp_path))
    (tmp_path / "alpha.txt").write_bytes(b"")

    class _Neutered(GlyphCPUv2):
        def _handle_syscall(self, syscall_num, image, imm=0):
            if syscall_num == 0x13:
                return -1  # enumeration neutered
            return super()._handle_syscall(syscall_num, image, imm)

    dead = _Neutered(OpcodeMapV2(), cols_instrs=W, fs_pix_enabled=True)
    dead.memory = [0] * 16384
    _stamp(dead, ADDR_DIR, str(tmp_path))
    assert _call(dead, 0x13, ADDR_DIR, ADDR_DEST, 256) == -1
    # and the LIVE engine must NOT behave that way:
    live = _cpu()
    _stamp(live, ADDR_DIR, str(tmp_path))
    assert _call(live, 0x13, ADDR_DIR, ADDR_DEST, 256) == 1


def test_l5_twin_bridge_reversion_reds_l4_contract():
    """If the twin's 19u bridge exclusion regresses (bridge returns 0 for
    0x13 — the TICKET_ITEM8 false-success class), the L4 contract text in
    this file no longer matches a working twin; the pin on the twin
    source must catch the reversion NOW, statically."""
    wgsl = (REPO / "tools" / "wgsl_glyph_isa_v2.py").read_text()
    assert "&& syscall_num != 19u" in wgsl, (
        "19u exclusion missing from the twin bridge — L4's GPU leg would "
        "fail with rd==0; fix the twin, not this test")

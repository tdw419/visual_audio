"""Standing gate: the RETIRED RAM-vs-pixel-space static check stays retired.

History: built 2026-09-15 (commit 4347547, Jericho-authorized) as backlog
item (a) of the SE023 ergonomics note — GlyphAssemblerV2 tracked registers
through LDI and raised ValueError on LD of a statically-known address
written only by an image-space syscall (then 0x04/0x09/0x11), exempting the
GH-8b FS window [1024,1280).

Retirement (Pillar 3 (d) completion, claim-queue round-3 item 7): the (A)
ruling's own completion terms said IMAGE_SPACE_WRITE_SYSCALLS + the
FS-window exemption "get deleted, not just narrowed" once obsolete. Seat
measured at HEAD (round-3 filing): all five data handlers (0x01/0x02/
0x03/0x04/0x08/0x09) read/write RAM via the _read_path single view; the
set was down to {0x11: 1} and 0x11 is excluded-forever per DEFECT-27, so
the check could never fire for a migrating handler again. Deleted
2026-09-22: the LDI-const register tracking (known_reg_const /
image_space_writes / ram_space_writes), the FS-window exemption, and the
assemble-time raise.

What these legs pin NOW:
- the old two-syscall-class hazard programs assemble CLEAN (no stale raise
  resurrected by a revert);
- the machinery (IMAGE_SPACE_WRITE_SYSCALLS et al.) is really gone from
  the assembler source, not behind a flag;
- runtime FS-window aliasing (GH-8b/SE017, fs_pix_enabled) is UNCHANGED —
  that mechanism is live and out of this retirement's scope.

Residual honesty (recorded, not waived): an LD of an address written only
by 0x11's image-space write now assembles clean and reads stale RAM at
runtime; that hazard is out of contract per DEFECT-27 and has no static
guard anymore.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2  # noqa: E402

W = 8


def _assemble(lines):
    return GlyphAssemblerV2(OpcodeMapV2()).assemble(lines, width_instrs=W)


def test_r1_former_red_program_now_assembles_clean():
    """The old L1 program (0x11 image-space write, then LD of its dest
    address) must NOT raise anymore: the check is deleted, so reverting the
    retirement (resurrecting the raise without the test update) turns this
    leg RED. Same program test_l1 used to assert RAISES on."""
    lines = ["LDI r1 500", "LDI r2 600", "LDI r3 1", "SYSCALL r9 0x11",
             "LD r5 r1", "HALT"]
    _assemble(lines)  # must not raise


def test_r2_former_fs_window_exempt_program_still_clean():
    """The old L3 program (0x04 then LD inside the FS window) assembles
    clean — trivially true post-deletion, pinned so the window's absence
    from the assembler is not misread as the program becoming invalid."""
    lines = ["LDI r1 1024", "LDI r2 1030", "LDI r3 5", "SYSCALL r9 0x04",
             "LD r5 r2", "HALT"]
    _assemble(lines)  # must not raise


def test_r3_pure_ram_roundtrip_still_clean():
    """Pure RAM round-trip (no syscall involved) never raises — the trivially
    true case, kept from the old L2 so the suite still covers it."""
    lines = ["LDI r1 600", "LDI r2 42", "ST r1 r2", "LD r5 r1", "HALT"]
    _assemble(lines)  # must not raise


def test_r4_machinery_is_gone_from_source():
    """The retirement is a DELETION, not a flag flip: the assembler source
    must no longer contain any of the retired machinery's names or its
    raise message. If any name reappears, this leg REDs and whoever
    reintroduced it must say why in the source."""
    src_path = REPO / "tools" / "glyph_isa_v2.py"
    source = src_path.read_text()
    for name in ("IMAGE_SPACE_WRITE_SYSCALLS", "image_space_writes",
                 "ram_space_writes", "known_reg_const", "in_fs_window",
                 "RAM-vs-pixel-space mismatch"):
        assert name not in source, (
            f"retired static-check machinery '{name}' reappeared in "
            f"{src_path.name} - the (d) deletion has been partially reverted"
        )
    # The runtime FS-window aliasing mechanism (GH-8b/SE017) must STILL be
    # present - this retirement must not have swept it up by mistake.
    assert "fs_pix_enabled" in source, (
        "runtime FS-window aliasing (fs_pix_enabled) missing - the (d) "
        "deletion over-reached into a live mechanism"
    )


def test_r5_check_can_still_catch_a_real_static_error():
    """Non-vacuity for the SUITE itself: the assembler's remaining static
    checks must still fire. SE023's jump-bounds check is retained
    machinery; an out-of-bounds jump target must still raise. Proves the
    assembler's assemble() path is genuinely exercised (not stubbed) by
    these legs."""
    lines = ["LDI r1 1", "JMP 999,999", "HALT"]
    with pytest.raises(ValueError, match="out of bounds"):
        _assemble(lines)


def test_r6_runtime_fs_window_aliasing_still_works():
    """The GH-8b runtime mechanism is NOT part of the retirement: with
    fs_pix_enabled, _mem_write into the FS window [1024,1280) aliases into
    image pixels (2 pixels per word, write-through memory mirror). Pin one
    live aliasing round-trip so the deletion cannot silently change runtime
    behavior. Packing per GlyphCPUv2._fs_pix_write: pixel W*2 carries bits
    23..0, pixel W*2+1 carries bits 31..24 in blue."""
    from tools.glyph_isa_v2 import GlyphCPUv2

    import numpy as np

    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=W, fs_pix_enabled=True)
    cpu.memory = [0] * 16384
    image = np.zeros((64, 32, 3), dtype=np.uint8)
    value = 0x41424344  # 'ABCD'
    cpu._mem_write(image, 1024, value)
    # Write-through mirror: the window word is readable from memory[].
    assert cpu.memory[1024] == value
    # Pixels are the persisted truth: bits 23..0 in pixel (word*2).
    px0 = image[0, 0]
    assert (int(px0[0]) << 16) | (int(px0[1]) << 8) | int(px0[2]) == (value & 0xFFFFFF)
    # Round-trip: _mem_read aliases back out of the pixels.
    assert cpu._mem_read(image, 1024) == value

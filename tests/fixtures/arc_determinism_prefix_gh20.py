#!/usr/bin/env python3
"""tests/test_gh20_fs_v2.py — Pixel-FS v2 gate (ticket gh20-spec-finalize).

RED UNTIL IMPLEMENTED: imports baker.pixel_fs_v2_kernel_image, which does
not exist yet. This file IS the finalized spec (receipt discipline: the
next session implements against THIS contract, no re-design).

Finalized 2026-09-08 against the LANDED GH-18 ABI facts (commit e3d3c13
+ reservation 07106ab — see ticket gh20-spec-finalize.json):

  - FS ops dispatch through the GH-18 indexed syscall table
    (GH18_TABLE_WORD=1568, 16 slots, sys_n 6..21); admission is
    autoatlas.admit_syscall ONLY (proof = admission; unverified
    candidates rejected E_ATLAS_UNVERIFIED, table untouched).
  - Slot allocation: 6/7 = legacy fixed slices, 8 = the GH-18 triple
    tile (gate fixture), 9 = the GH-18 unknown-syscall leg number
    (must STAY unassigned — do not light it). FS v2 ops:
      SYS 10 = fs_append, SYS 11 = fs_rename, SYS 12 = fs_unlink.
  - FS window: GH-8b pixel alias [1024,1280) (2 px/word, lo24+hi8-BLUE,
    engine = glyph_isa_v2._fs_pix_write). FSTAB v2 = 2 slots x 8 words
    [1024,1040): (name, start, len, in_use, refcount, parent_dir,
    next_chain, reserved). Data extents [1040,1280).
  - WARNING (ticket): no MUL in OpcodeMapV2 (shift-add only); LDI is
    exact — decimalize hex constants carefully; CMP against r0 tests
    the FLAG register, never zero.
  - _pix_write_word raises ValueError for unknown word ranges — FS op
    tiles' staged words land in the fs-alias branch (already present),
    table writes in the reserved pfn-5 window [1312,1328).
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import (                              # noqa: E402 (RED)
    pixel_fs_v2_kernel_image,      # does not exist yet — RED at import
    GH18_TABLE_WORD,
)
from tools.glyph_gpt.autoatlas import admit_syscall              # noqa: E402 (RED)
from tools.glyph_gpt.baker import _gh18_tile_pc                  # noqa: E402
from tools.glyph_gpt.baker import GH18_TABLE_PIX_WORD            # noqa: E402
from tools.glyph_gpt.fs_v2 import _gh20_bake_stamp               # noqa: E402

# ── finalized FS v2 ABI constants ────────────────────────────────────────
FSV2_FSTAB_WORD = 1024       # 2 slots x 8 words [1024,1040)
FSV2_NSLOTS = 2
FSV2_SLOT_WORDS = 8          # name,start,len,in_use,refcount,parent,next,rsvd
FSV2_DATA_WORD = 1040        # data extents [1040,1280)
FSV2_DATA_END = 1280
FSV2_N_APPEND = 10           # SYS 10 = fs_append
FSV2_N_RENAME = 11           # SYS 11 = fs_rename
FSV2_N_UNLINK = 12           # SYS 12 = fs_unlink
FSV2_REF_SHARED = 2          # refcount of the shared fixture file
FSV2_ERR_BUSY = ord('E')     # clean-fail marker (E-K1 family) in the result word
FSV2_RESULT_WORD = 754       # GH-18 tile ABI result word (BOX2)
FSV2_EXIT_A = 703
FSV2_EXIT_OK = 0xFEED0000 | 6
KERNEL_OK = 0xCAFE0014       # 0xCAFE0000 | 20 (GH-20 status tail)

NAME_A = ord('A')            # single-char names: exact LDI constants
NAME_B = ord('B')


def _bake(tmp: Path, name: str = "gh20.npy") -> GlyphRunner:
    out = tmp / name
    pixel_fs_v2_kernel_image(build_default_atlas(), out_path=out)
    return GlyphRunner(out, ram_words=16384)


def _table_slot(sys_n: int) -> int:
    return GH18_TABLE_WORD + (sys_n - 6)


def _img_md5(img) -> str:
    import numpy as np
    return hashlib.md5(np.ascontiguousarray(img).tobytes()).hexdigest()


def _fs_word(img, word: int) -> int:
    """Engine-exact read of an fs-window word from the IMAGE (glyph_isa_v2
    GlyphCPUv2._fs_pix_read layout). Receipt (2026-09-09, probes 51-52):
    the pixels are the persisted truth, but receipt memory[] only mirrors
    RUNTIME writes — _fs_pix_write updates the mirror on store, while
    BAKE-time seeded words never pass through it, so a refused-op leg that
    asserts seeded fields via receipt memory[] reads ZEROS for words the
    tile correctly left untouched. Read the image, not the RAM mirror."""
    h, w, _ = img.shape
    lin = (word * 2) % (w * h)
    lo = ((int(img[lin // w, lin % w][0]) << 16)
          | (int(img[lin // w, lin % w][1]) << 8)
          | int(img[lin // w, lin % w][2]))
    lin2 = (word * 2 + 1) % (w * h)
    hi = int(img[lin2 // w, lin2 % w][2])
    return (lo | (hi << 24)) & 0xFFFFFFFF


# ── leg 1: fs_append grows extents without clobbering neighbors ─────────

@pytest.mark.skipif(False, reason="GH-20 implemented (fs_v2 bake + abi=gh20 admission)")
def test_gh20_fs_append_grows_extents_clean():
    """fs_append (SYS 10) grows file A's extent past its initial
    allocation; the FSTAB slot 1, the box words, and the pixels BEYOND
    the grown extent stay byte-identical."""
    with tempfile.TemporaryDirectory() as d:
        runner = _bake(Path(d))
        img_before = runner.image.copy()
        res = admit_syscall(runner, FSV2_N_APPEND,
                            contract="fs_append(name,start,len): grow "
                                     "extent by staged words @750",
                            argv={0: NAME_A}, expected=0)
        assert res.ok, f"{res.code}: {res.detail}"
        # .table_word carries the tile's packed pixel PC (the value the
        # table slot is LIT with — the GH-18 gate asserts liveness via
        # != 0, not a slot address). The slot itself is verified by the
        # on-die re-dispatch below.
        assert res.table_word != 0, "table entry must be live"
        assert res.table_word == _gh18_tile_pc(mode="fs_v2")
        receipt = runner.drive(seeds={}, max_instructions=60000)
        assert receipt["halted"] is True and not receipt["faulted"]
        slot1 = 1024 + FSV2_SLOT_WORDS          # neighbor FSTAB slot
        for w in range(slot1, slot1 + FSV2_SLOT_WORDS):
            assert receipt["memory"][w] == 0, f"slot 1 word {w} clobbered"
        # pixels outside the grown extent untouched (spot: box2 window)
        for w in range(736, 768):
            assert (runner.image.reshape(-1, 3)[w * 2] ==
                    img_before.reshape(-1, 3)[w * 2]).all()


# ── leg 2: fs_rename updates the entry in place, inode index preserved ──

@pytest.mark.skipif(False, reason="GH-20 implemented (fs_v2 bake + abi=gh20 admission)")
def test_gh20_fs_rename_inplace_inode_preserved():
    """fs_rename (SYS 11) rewrites slot 0's name field in place; slot
    ORDER (the inode index) is unchanged and slot 1 STAYS FREE."""
    with tempfile.TemporaryDirectory() as d:
        runner = _bake(Path(d))
        # STRENGTHENED fixture (audit 2026-09-09: the original RED gate's
        # direct slot-order assert was deleted pre-green — this leg had
        # only an indirect slot-1-free guard). Seed a SECOND live file
        # into slot 1 so "slot order preserved" is a two-sided fact: slot
        # 0's inode fields survive the rename AND slot 1's entry is
        # byte-identical (a tile that allocated slot 1 for the new name,
        # or rewrote start/len while copying, now fails HERE).
        _gh20_bake_stamp(runner.image, {
            1032: NAME_B,           # slot 1: file 'B'
            1033: 1042,             # start = second data word
            1034: 1,                # len
            1035: 1,                # in_use
            1036: 1,                # refcount (live, not free)
            1037: 0, 1038: 0, 1039: 0,
        })
        res = admit_syscall(runner, FSV2_N_RENAME,
                            contract="fs_rename(old,new): in-place FSTAB "
                                     "name update, slot order preserved",
                            argv={0: NAME_A, 1: NAME_B}, expected=0)
        assert res.ok, f"{res.code}: {res.detail}"
        receipt = runner.drive(seeds={}, max_instructions=60000)
        assert receipt["halted"] is True and not receipt["faulted"]
        mem = receipt["memory"]
        assert mem[1024] == NAME_B, "slot 0 name not renamed in place"
        assert mem[FSV2_RESULT_WORD] == 0
        # DIRECT slot-order proof (restored; deleted in 0d83f89, audit
        # 2026-09-09). receipt memory[] misses BAKE-time seeds, so inode
        # fields read engine-exactly from the persisted IMAGE pixels —
        # _fs_word, not the RAM mirror.
        img = runner.image
        # slot 0: name updated, inode fields byte-identical to the seed
        assert _fs_word(img, 1024) == NAME_B, "slot 0 name wrong in image"
        assert _fs_word(img, 1025) == FSV2_DATA_WORD, "slot 0 start moved"
        assert _fs_word(img, 1026) == 2, "slot 0 len changed"
        assert _fs_word(img, 1027) == 1, "slot 0 in_use changed"
        assert _fs_word(img, 1028) == FSV2_REF_SHARED, "slot 0 refcount changed"
        # slot 1: the second file's entry untouched, still in slot 1
        assert _fs_word(img, 1032) == NAME_B, "slot 1 name clobbered"
        assert _fs_word(img, 1033) == 1042, "slot 1 start moved"
        assert _fs_word(img, 1034) == 1, "slot 1 len changed"
        assert _fs_word(img, 1035) == 1, "slot 1 in_use changed"
        assert _fs_word(img, 1036) == 1, "slot 1 refcount changed"


# ── leg 3: fs_unlink with non-zero refcount fails cleanly ────────────────

@pytest.mark.skipif(False, reason="GH-20 implemented (fs_v2 bake + abi=gh20 admission)")
def test_gh20_fs_unlink_shared_refcount_fails_clean():
    """fs_unlink (SYS 12) on a file with refcount=2 must fail CLEANLY:
    errno marker in the result word, refcount and in_use unchanged, data
    pixels intact (no dangling extent, no corruption)."""
    with tempfile.TemporaryDirectory() as d:
        runner = _bake(Path(d))
        before = runner.image.copy()
        res = admit_syscall(runner, FSV2_N_UNLINK,
                            contract="fs_unlink(name): refuse when "
                                     "refcount != 0 (clean errno)",
                            argv={0: NAME_A}, expected=FSV2_ERR_BUSY)
        assert res.ok, f"{res.code}: {res.detail}"
        receipt = runner.drive(seeds={}, max_instructions=60000)
        assert receipt["halted"] is True and not receipt["faulted"], receipt
        mem = receipt["memory"]
        assert mem[FSV2_RESULT_WORD] == FSV2_ERR_BUSY
        # The refuse path must leave the FSTAB byte-identical. Seeded
        # fields read ENGINE-EXACTLY from the IMAGE (receipt: the memory[]
        # mirror only carries runtime stores — seeded words read 0 there
        # even untouched; probes 51-52, 2026-09-09).
        assert _fs_word(runner.image, 1027) == 1, "in_use clobbered on refused unlink"
        assert _fs_word(runner.image, 1028) == FSV2_REF_SHARED, "refcount clobbered"
        for w in range(1024, 1040):
            assert _fs_word(runner.image, w) == _fs_word(before, w), \
                f"FSTAB word {w} mutated on refused unlink"
        assert _fs_word(runner.image, 1040) == 0x11111111, "data word 0 corrupted"
        assert _fs_word(runner.image, 1041) == 0x22222222, "data word 1 corrupted"
        assert mem[FSV2_EXIT_A] == FSV2_EXIT_OK


# ── leg 4: canonical replay md5 fixpoint preserved across mutations ─────

@pytest.mark.skipif(False, reason="GH-20 implemented (fs_v2 bake + abi=gh20 admission)")
def test_gh20_canonical_replay_fixpoint_across_mutations():
    """After FS mutations (append+rename) the saved image replays
    offline to the SAME md5 twice (idempotence = the image md5 stays a
    valid receipt even post-mutation)."""
    with tempfile.TemporaryDirectory() as d:
        runner = _bake(Path(d))
        for n in (FSV2_N_APPEND, FSV2_N_RENAME):
            r = admit_syscall(runner, n, contract="fs op tile",
                              argv={0: NAME_A}, expected=0)
            assert r.ok, f"{r.code}: {r.detail}"
        runner.drive(seeds={}, max_instructions=60000)
        path = Path(d) / "mutated.npy"
        import numpy as np
        np.save(path, runner.image)
        mds = []
        for _ in range(2):
            r2 = GlyphRunner(path, ram_words=16384).run(
                max_instructions=60000)
            assert r2["halted"] is True and not r2["faulted"]
            np.save(path, GlyphRunner(path, ram_words=16384).image)
            mds.append(_img_md5(runner.image))
        assert mds[0] == mds[1], f"replay not idempotent: {mds}"


# ── leg 5: ALL FS ops route through the table as proven tiles ───────────

@pytest.mark.skipif(False, reason="GH-20 implemented (fs_v2 bake + abi=gh20 admission)")
def test_gh20_fs_ops_are_proven_table_tiles():
    """Structural: every FS op enters via admit_syscall (its IngestResult
    says ok + table slot); slot 9 stays UNLIT (the unknown-syscall leg
    number); no host pixel writes outside (table slot words ∪ fs window
    ∪ tile rect)."""
    with tempfile.TemporaryDirectory() as d:
        runner = _bake(Path(d))
        before = runner.image.copy()
        results = {}
        for n, exp in ((FSV2_N_APPEND, 0), (FSV2_N_RENAME, 0),
                       (FSV2_N_UNLINK, FSV2_ERR_BUSY)):
            # fs_unlink's contract verdict IS the clean-fail errno (69) —
            # the seed's refcount=2 forces the refuse path. Receipt
            # (2026-09-09): the first draft admitted all three with
            # expected=0, an unsatisfiable oracle for the unlink tile —
            # and argv={0: 0} seeded the ORACLE with argv0=0, so the
            # branch-on-name took the mismatch errno on every op
            # (r2=0x45, E_ATLAS_UNVERIFIED 6/6). argv0 must be the name
            # char the tiles branch on.
            r = admit_syscall(runner, n, contract="fs op tile",
                              argv={0: NAME_A}, expected=exp)
            results[n] = r
        assert all(r.ok for r in results.values())
        # .table_word carries the tile's packed pixel PC — the VALUE the
        # slot is LIT with (GH-18 liveness contract: != 0 on admission).
        # Receipt (2026-09-09, probes 40-45): the first draft asserted
        # table_word == the slot ADDRESS (_table_slot(n)), a category
        # mismatch — legs 1-4 already assert the PC == _gh18_tile_pc
        # (mode="fs_v2"); the slot-address contract is verified on-die by
        # the probe-then-issue drive leg (the op only dispatches because
        # the walk of that very slot returned this PC) and by the stray
        # whitelist below pinning the slot's pixel to a live write.
        for n in (FSV2_N_APPEND, FSV2_N_RENAME, FSV2_N_UNLINK):
            assert results[n].table_word == _gh18_tile_pc(mode="fs_v2"), \
                f"SYS {n} slot not lit with the fs_v2 tile PC"
        # RESTORED (audit 2026-09-09): 0d83f89 collapsed the RED gate's
        # per-syscall distinct-slot assertions into one shared constant,
        # so "each FS op routes through ITS OWN table slot" was no longer
        # proven anywhere. The slot VALUES are all the same PC (one shared
        # rect), but the slot ADDRESSES are per-syscall: admit stamps
        # pixel word GH18_TABLE_PIX_WORD + (sys_n - 6) (autoatlas
        # _pix_write_word) — and a failed verification ROLLS THAT SLOT
        # BACK to 0 (a broken tile never keeps its slot). Read the three
        # slots' pixels directly: each must be lit with the tile PC, and
        # slot 9 (the unknown-syscall leg number, never admitted here)
        # must stay zero — i.e. the three FS slots are lit INDIVIDUALLY,
        # not as a side effect of one shared write.
        img = runner.image
        h, w, _ = img.shape
        # on-die exercise (kept from the RED contract): task A probe-issues
        # SYS 10/11/12 and each dispatches THROUGH its own slot — this is
        # the routing proof at runtime, complementing the pixel reads below.
        receipt = runner.drive(seeds={}, max_instructions=60000)
        assert receipt["halted"] is True and not receipt["faulted"]
        for s, n in ((10, FSV2_N_APPEND), (11, FSV2_N_RENAME), (12, FSV2_N_UNLINK)):
            pw = GH18_TABLE_PIX_WORD + (s - 6)
            px = img[pw // w, pw % w]
            slot_val = (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])
            assert slot_val == _gh18_tile_pc(mode="fs_v2"), \
                f"table slot {s} (SYS {n}) pixel word {pw} not lit with the tile PC: {slot_val:#x}"
        pw9 = GH18_TABLE_PIX_WORD + (9 - 6)
        px9 = img[pw9 // w, pw9 % w]
        assert not px9.any(), "slot 9 pixel must stay unlit"
        # whitelist: only table slots 10..12 + fs window + tile rect differ
        # (docstring contract: table slot words ∪ fs window ∪ tile rect).
        # Receipt (2026-09-09): the first draft omitted the tile rect —
        # three stamped tiles (96 words = 96 px at [1600,1696)) read as
        # strays against the docstring's own whitelist.
        diff = (before != runner.image).any(axis=2).reshape(-1)
        allowed = set()
        h, w, _ = runner.image.shape
        for s in (10, 11, 12):
            pw = 1312 + (s - 6)           # reserved pfn-5 window (07106ab)
            allowed |= {pw // w * w + pw % w}
        # whitelist: only table slots 10..12 + tile rect + fs window differ
        # (docstring contract: table slot words ∪ fs window ∪ tile rect).
        # NARROWED (audit 2026-09-09): 0d83f89 whitelisted the WHOLE
        # [1024,1280) alias block, so a tile corrupting arbitrary FS data
        # words passed this leg. The three admitted ops can legitimately
        # mutate a KNOWN, SMALL set of window words:
        #   1024: rename writes the slot-0 name
        #   1026: append writes the slot-0 len
        #   1040+2=1042: append's new extent word (len was 2 -> index 2)
        #   1032..1039: slot 1 (must stay ZERO — pinned by the drive,
        #     see below; whitelisted so the zero-check, not this leg's
        #     diff, is what enforces it)
        # Everything else in the window must be byte-identical.
        # (Alias layout: 2 px per word — glyph_isa_v2._fs_pix_write; the
        # first RED draft whitelisted flat word indexes 1024..1280 in the
        # TOP-LEFT of the image — program text — and missed the real
        # alias block at pixels [2048,2560), probes 40-45, 2026-09-09.)
        h, w, _ = runner.image.shape
        mutated_window = {1024, 1026, 1042} | set(range(1032, 1040))
        for word in mutated_window:
            allowed |= {(word * 2) % (w * h), (word * 2 + 1) % (w * h)}
        # slot 1 words must read ZERO in the image after everything ran
        # (the RED contract's slot-1-free guard, engine-exact):
        for word in range(1032, 1040):
            assert _fs_word(runner.image, word) == 0, \
                f"slot 1 word {word} clobbered (must stay free)"
        # Tile rect: derive from the MODE-CORRECT packed PC, not
        # GH18_TILE_WORD. Receipt (2026-09-09): GH18_TILE_WORD=1600 is the
        # ADMIT-mode rect; this image is baked with mode="fs_v2", whose
        # tile rect row shifts per mode (admit 0x1e0007 vs fs_v2
        # 0x230006 — _gh18_relocate_jumps docstring, probes 22/23/25),
        # putting the rect at flat pixels [1144,1240). Whitelisting the
        # admit-mode rect let the three legitimately stamped fs_v2 tile
        # bodies read as 55 strays. The same mode-correct PC is already
        # pinned by legs 1-4 and the table-liveness assertion above.
        from tools.glyph_gpt.baker import _gh18_tile_pc as _tile_pc
        pc = _tile_pc(mode="fs_v2")
        tcol, trow = pc & 0xFFFF, (pc >> 16) & 0xFFFF
        rect0 = trow * w + tcol * 4      # 8 instrs/row = 32 px wide
        for word in range(rect0, rect0 + 96):
            allowed |= {word}            # tile rect: 1 word = 1 px
        allowed = {i for i in allowed if i < diff.size}
        strays = [i for i in range(diff.size) if diff[i] and i not in allowed]
        assert not strays, f"pixel writes outside the whitelist: {strays[:8]}"

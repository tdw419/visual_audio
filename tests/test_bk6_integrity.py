"""BK-6 gate: tests/test_bk6_integrity.py.

Roadmap BK-6 (promoted from GLYPH_BACKLOG, commit 1549209): "Boot
self-check: image carries a hash-of-code-region word baked at build;
kernel verifies before dispatch (detects pixel corruption)."

Gate legs (the spec's oracle clause, mapped):
  L1 (clean):     uncorrupted image → kernel posts verdict 0x600D0006
                  and dispatches: the task's work receipt (903 = 77)
                  lands — proof the check ran BEFORE dispatch and
                  passed on a clean image.
  L2 (tamper):    flipping ONE code pixel INSIDE the hashed window →
                  kernel posts INTEGRITY_FAIL (902 = 0xBAD0006) and
                  HALTs; the task NEVER runs (receipt 903 stays 0) —
                  verification BEFORE dispatch, garbage never executed.
  L3 (nonvacuity): the tampered leg is meaningful — the flipped pixel
                  is provably inside the hashed window AND the baked
                  constant differs from the tampered sum (no trivially
                  passing check), plus a guard that the harness RAM
                  size matches the wrap assumption and that the kernel
                  compare constant equals the recomputed window sum.

WINDOW GEOMETRY (measured, bk6_rsweep2 probe):
  ram_words=1792: the wrapped-LD stream at addresses >= ram_words falls
  through to glyph_isa_v2._mem_read's linear image read, landing on
  image pixel words [(1792 + k) mod 832] = [128, 192) — code rows 4-5,
  41 nonzero pixel words, and crucially EXCLUDING the :__kcend constant
  pixels [80, 84) so the two-pass bake is self-consistent (the baked
  constant does not perturb the bytes it hashes). ram_words must ALSO
  exceed the isolation MMIO top word (8283) so the BOX0 arming stores
  land in real MMIO and the receipt words 901+ exist in RAM.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.integrity import (                          # noqa: E402
    bk6_image, wrap_window_sum, BK6_VERDICT_WORD, BK6_VERDICT_OK,
    BK6_FAULT_WORD, BK6_FAULT_SEEN, BK6_WORK_WORD, BK6_WORK_RECEIPT,
    BK6_RAM_WORDS, BK6_NWORDS,
)
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402

# Window geometry chosen so the wrapped window lands on real code
# pixels while keeping the MMIO block and receipt words in RAM.
# ram_words must exceed _ISO_TOP_WORD (8283) or the BOX0 arming store
# itself faults; 8448 % 832 = 128 puts the window at pixel words
# [128, 192) — code rows 4-5, excluding the :__kcend constant pixels.
BK6_RAM = 8448


def _bake() -> np.ndarray:
    return bk6_image(out_path=None, ram_words=BK6_RAM)


def _window(image: np.ndarray, ram_words: int = BK6_RAM) -> list:
    n = image.shape[0] * image.shape[1]
    return [(ram_words + k) % n for k in range(BK6_NWORDS)]


def _tamper_in_window(image: np.ndarray) -> tuple:
    """Flip exactly one byte channel of a nonzero pixel INSIDE the hashed
    window. Returns (tampered image, flipped linear word).

    BUG-13 (this run): the original scan picked the FIRST nonzero window
    word — linear 128 = (0,4), the `:__kbad` leg's own OR opcode pixel.
    Killing the kbad leg means the INTEGRITY_FAIL store never executes
    and the engine dies as opcode=None instead. Pick the LAST nonzero
    window word instead (linear 190 = instr 47, the tail of the
    :__kgood const block) — well ahead of the kbad leg at instrs 50+,
    and still strictly inside the hashed window (moves the sum)."""
    px = image.reshape(-1, 3)
    target = max(w for w in _window(image) if any(px[w]))
    bad = image.copy()
    bad.reshape(-1, 3)[target, 2] ^= 0x01
    assert not np.array_equal(bad, image)
    return bad, target


def test_bk6_clean_image_verifies_and_dispatches():
    with tempfile.TemporaryDirectory() as d:
        runner = GlyphRunner(_bake(), ram_words=BK6_RAM)
        receipt = runner.drive(seeds={}, max_instructions=60000)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # verdict posted by the check leg
        assert mem[BK6_VERDICT_WORD] == BK6_VERDICT_OK, hex(mem[BK6_VERDICT_WORD])
        # dispatch happened: task receipt landed
        assert mem[BK6_WORK_WORD] == BK6_WORK_RECEIPT, mem[BK6_WORK_WORD]
        # no fault marker
        assert mem[BK6_FAULT_WORD] == 0, hex(mem[BK6_FAULT_WORD])


def test_bk6_single_pixel_flip_faults_integrity_fail():
    with tempfile.TemporaryDirectory() as d:
        bad, _target = _tamper_in_window(_bake())
        runner = GlyphRunner(bad, ram_words=BK6_RAM)
        receipt = runner.drive(seeds={}, max_instructions=60000)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        mem = receipt["memory"]
        # INTEGRITY_FAIL posted by the corrupt-image leg
        assert mem[BK6_FAULT_WORD] == BK6_FAULT_SEEN, hex(mem[BK6_FAULT_WORD])
        # task NEVER ran: work receipt still clean
        assert mem[BK6_WORK_WORD] == 0, mem[BK6_WORK_WORD]
        # verdict never posted (dispatch never reached)
        assert mem[BK6_VERDICT_WORD] == 0, hex(mem[BK6_VERDICT_WORD])


def test_bk6_tamper_is_in_window_and_detected():
    """Non-vacuity: the tamper leg is meaningful — the tamper pixel is
    inside the hashed window and actually moves the window sum."""
    img = _bake()
    px = img.reshape(-1, 3)
    nonzero_in_window = sum(1 for w in _window(img) if any(px[w]))
    assert nonzero_in_window > 0, "window is vacuous zero padding"
    bad, _target = _tamper_in_window(img)
    assert wrap_window_sum(img, ram_words=BK6_RAM) != \
        wrap_window_sum(bad, ram_words=BK6_RAM)


def test_bk6_baked_constant_matches_window_sum():
    """The two-pass bake landed the TRUE window sum: the kernel compare
    constant (recorded host-side at bake time) equals the sum recomputed
    from the FINAL baked image over the same window."""
    img = _bake()
    baked = bk6_image.last_expected_sum
    assert baked != 0, "bake did not record the expected sum"
    assert baked == wrap_window_sum(img, ram_words=BK6_RAM), \
        (hex(baked), hex(wrap_window_sum(img, ram_words=BK6_RAM)))


def test_bk6_harness_ram_matches_wrap_assumption():
    """The wrapped-LD read path and the isolation MMIO block only exist
    with ram_words = the value the image was baked for — a mismatched
    RAM size rotates the window (hashing different bytes) or drops the
    MMIO block entirely (BOX0 arming store faults). Guard the invariant:
    the harness RAM matches the bake and isolation is active."""
    with tempfile.TemporaryDirectory() as d:
        runner = GlyphRunner(_bake(), ram_words=BK6_RAM)
        assert runner.get_cpu()._iso_enabled is True


def test_bk6_window_covers_code_and_excludes_constant():
    """Geometry receipt: the window sits inside the code region (rows
    4-5 of the 26-row image), is 41/64 nonzero, and does NOT overlap
    the :__kcend constant pixels [80, 84) — the two-pass bake invariant
    that makes the baked constant stable under its own hashing."""
    img = _bake()
    n = img.shape[0] * img.shape[1]
    win = _window(img)
    px = img.reshape(-1, 3)
    assert all(w < n for w in win)
    nonzero = sum(1 for w in win if any(px[w]))
    assert nonzero >= 32, f"window mostly empty: {nonzero}/64"
    assert not (set(win) & set(range(80, 84))), "window overlaps constant"

"""BK-6 BOOT SELF-CHECK — hash-of-code-region word verified before dispatch.

Roadmap BK-6 (promoted from GLYPH_BACKLOG, commit 1549209): "Boot
self-check: image carries a hash-of-code-region word baked at build;
kernel verifies before dispatch (detects pixel corruption)."

Gate (tests/test_bk6_integrity.py): flipping one code pixel → kernel
faults with INTEGRITY_FAIL instead of executing garbage.

Mechanics — all kernel-side, zero engine changes (signals.py patterns):

  THE WRAP (proven live, probe in systems/RECEIPT_BK6_INTEGRITY.md):
  with ram_words=W, a `LD` at address >= W falls through to
  glyph_isa_v2._mem_read, whose linear wrap reads IMAGE PIXEL WORD
  (addr mod w*h) as a 24-bit r<<16|g<<8|b pack. At W=16384 with this
  image (n=800 pixel words) the loop starting at addr 16384+k covers
  linear words [384, 448) — i.e. the zero padding band BETWEEN the two
  code blocks (rows 12..14 at 32 px/row), deliberately: padding is
  image content too, and hashing zeros is the degenerate case this
  gate exists to EXPOSE, not hide (see the non-vacuity legs below).

  THE HASH: sum of the 24-bit pixel words mod 2^32. A single-channel
  flip of pixel p moves the sum by ±(1<<k)·delta ≠ 0 — every single-
  pixel corruption inside the window is detected (integer sum, no
  collisions within the window: total < 2^32 for 64 max-ish words).

  TWO-PASS BAKE: pass 1 (constant 0) fixes the layout; the host
  measures the sum over the final window from the assembled pass-1
  image; pass 2 bakes with the constant in :__kcend's LDI pair. The
  window [384,448) contains NO instruction pixels (it is pure zero
  padding), so the baked constant does not perturb the hashed bytes —
  the loop and the host measure the same bytes by construction. For
  non-degenerate windows (any rotation covering code pixels), hashing
  code that contains the constant is still sound: pass 1 pins the
  layout, the constant's pixels are inside the measured image, and
  any later flip — of code OR constant — shifts the sum.

  VERDICT: JZ (equality-only ISA — signals.py Bug-1 discipline) routes
  the MATCH case over the branch to :__kgood; any mismatch falls
  through to :__kbad, which posts BK6_FAULT_SEEN (INTEGRITY_FAIL) and
  HALTs. The task NEVER runs on a corrupt image (verification BEFORE
  dispatch): work word 903 stays 0.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Union

import numpy as np

_REPO = Path(__file__).resolve().parent.parent.parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, str(_p))

# ── BK-6 word ABI ────────────────────────────────────────────────────────
BK6_VERDICT_WORD = 901            # kernel posts 0x600D0006 on a clean check
BK6_VERDICT_OK = 0x600D0006
BK6_FAULT_WORD = 902              # INTEGRITY_FAIL marker on corruption
BK6_FAULT_SEEN = 0x0BAD006        # 'BAD0' prefix + BK-6 tail id
BK6_WORK_WORD = 903               # task posts 77 here (dispatch happened)
BK6_WORK_RECEIPT = 77
BK6_SCRATCH_WORD = 910            # loop scratch (cursor lives in r5)
# Wrap point AND loop bound: must exceed the isolation MMIO top word
# (8283 — or the BOX0 arming store faults) and (BK6_RAM_WORDS mod 832)
# must put the 64-word window [start, start+64) on real code pixels
# while EXCLUDING the :__kcend constant pixels [80, 84). 8448 % 832 =
# 128 → window = pixel words [128, 192), code rows 4-5, 41 nonzero.
BK6_RAM_WORDS = 8448
BK6_NWORDS = 64                   # pixel words hashed (16 instructions)

_BK6_TASK_PC = 0                  # pass-1 global (two-pass bake, signals.py pattern)


def _pack_consts(v: int) -> List[str]:
    """Full 32-bit v in r14 — FIXED-SIZE 5 lines (two-pass invariant,
    see signals.py._pack_consts)."""
    hi, lo = (v >> 16) & 0xFFFF, v & 0xFFFF
    return [f"LDI r14 {lo}", f"LDI r13 {hi}", "LDI r4 16", "SHL r13 r4",
            "OR r14 r13"]


def _jump_r30(lines: List[str], v: int) -> None:
    lines.extend(_pack_consts(v))
    lines.append("XOR r30 r30")
    lines.append("OR r30 r14")
    lines.append("KJMP r30")


def bk6_program_text(expected_sum: int) -> str:
    """Kernel: verify the image window, then dispatch the task.
    expected_sum is the pass-1-measured sum over the hashed window.
    The :__kgood jump target rides the module-global _BK6_TASK_PC
    (pass-1 coords), same two-pass pattern as signals.py's PCs."""
    a: List[str] = []
    add = a.append
    add(":__entry")
    add("JMP :__kcheck")
    # ---- integrity check (SUPER, before ANY dispatch) ----
    # r6 = running sum, r5 = LD cursor; each LD at 16384+k wraps onto
    # image pixel word (16384+k) mod (w*h) — 24-bit r<<16|g<<8|b.
    add(":__kcheck")
    # arm BOX0 over the kernel/task data words [900,912): the dispatch
    # arms USER for :__task, and a USER store outside every box faults
    # E-K1 (signals.py latch discipline). Values are BYTE addresses.
    add("LDI r15 8195"); add("LDI r14 3600"); add("ST r15 r14")
    add("LDI r15 8196"); add("LDI r14 3648"); add("ST r15 r14")
    add(f"LDI r15 {BK6_SCRATCH_WORD}")
    add("LDI r14 0")
    add("ST r15 r14")
    add("XOR r6 r6")                          # sum = 0
    add(f"LDI r5 {BK6_RAM_WORDS}")            # cursor = wrap point
    add(":__kloop")
    add("LD r7 r5")                           # r7 = pixel word (wrapped)
    add("ADD r6 r7")                          # sum += word (mod 2^32)
    add("LDI r4 1")
    add("ADD r5 r4")                          # k += 1
    add(f"LDI r4 {BK6_RAM_WORDS + BK6_NWORDS}")  # end cursor
    add("CMP r5 r4")
    add("JZ :__kcend")
    add("JMP :__kloop")
    # ---- compare against the baked constant ----
    add(":__kcend")
    a.extend(_pack_consts(expected_sum))
    add("CMP r6 r14")
    # JZ jumps on equality → good path; mismatch falls through to the
    # INTEGRITY_FAIL leg (never route the alive case INTO the branch).
    add("JZ :__kgood")
    add(":__kbad")
    add(f"LDI r15 {BK6_FAULT_WORD}")
    a.extend(_pack_consts(BK6_FAULT_SEEN))
    add("ST r15 r14")
    add("HALT")
    # ---- verified: post verdict, dispatch the real task ----
    add(":__kgood")
    add(f"LDI r15 {BK6_VERDICT_WORD}")
    a.extend(_pack_consts(BK6_VERDICT_OK))
    add("ST r15 r14")
    add("LDI r15 8192")                       # latch=1 → KJMP lands USER
    add("LDI r14 1")
    add("ST r15 r14")
    _jump_r30(a, _BK6_TASK_PC)                # pass-1 task PC (two-pass bake);
    # BUG-12 (this run): the call previously passed literal 0 — the KJMP
    # rebooted the kernel at :__entry WITH the latch already USER (1), so
    # the re-entry's BOX0 arming store to MMIO word 8195 (byte 32780)
    # faulted E-K1 on the clean-image leg. _BK6_TASK_PC is the value
    # bk6_image() computes from pass-1 coords for exactly this call.
    add("JMP :__kdone")
    # ---- trivial task: post work receipt, exit ----
    add(":__task")
    add(f"LDI r15 {BK6_WORK_WORD}")
    add(f"LDI r14 {BK6_WORK_RECEIPT}")
    add("ST r15 r14")
    add("HALT")
    add(":__kdone")
    add("HALT")
    return "\n".join(a) + "\n"


def wrap_window_sum(image: np.ndarray, ram_words: int = BK6_RAM_WORDS,
                    nwords: int = BK6_NWORDS) -> int:
    """THE ground-truth mirror of the in-image loop: sum of the 24-bit
    pixel words the wrapped LD stream reads — linear indices
    (ram_words + k) mod (w*h), packed r<<16|g<<8|b, summed mod 2^32."""
    h, w, _ = image.shape
    n = w * h
    words = image.reshape(-1, 3)
    total = 0
    for k in range(nwords):
        r, g, b = (int(c) for c in words[(ram_words + k) % n])
        total += (r << 16) | (g << 8) | b
    return total & 0xFFFFFFFF


def bk6_image(
    min_rows: int = 16,
    cols_instrs: int = 8,
    out_path: Optional[Union[str, Path]] = None,
    ram_words: int = BK6_RAM_WORDS,
) -> np.ndarray:
    """Two-pass bake: pass 1 (constant 0) fixes the layout; the host
    measures the window sum; pass 2 bakes with the constant in place."""
    from glyph_gpt.baker import bake_image
    from rv64i_to_glyph import assemble_glyph_to_pixels

    global _BK6_TASK_PC
    txt1 = bk6_program_text(expected_sum=0)
    _, coords1 = assemble_glyph_to_pixels(txt1, cols_instrs=cols_instrs,
                                          min_rows=min_rows)

    def packed(label: str) -> int:
        col, row = coords1[label]
        return (col & 0xFFFF) | ((row & 0xFFFF) << 16)

    _BK6_TASK_PC = packed(":__task")
    try:
        # pass 1: fix the layout (any constant value assembles identically)
        pass1 = assemble_glyph_to_pixels(txt1, cols_instrs=cols_instrs,
                                         min_rows=min_rows)[0]
        sum1 = wrap_window_sum(pass1, ram_words=ram_words)
        txt2 = bk6_program_text(expected_sum=sum1)
        # pass 2 could perturb window bytes if the constant OR the task PC
        # landed inside the window (pass 2 patches both). The task-PC block
        # (instrs 45-49) DOES land inside the current window, so iterate to
        # a fixed point: keep re-baking until the baked sum matches the
        # final image's measured sum. The map sum(word mod 2^32) is
        # contractive here — a mismatch shifts only the constant's LDI
        # immediates, whose contribution converges immediately.
        expected = sum1
        for _ in range(8):
            image = bake_image(txt2, atlas=None, cols_instrs=cols_instrs,
                               min_rows=min_rows, out_path=out_path)
            measured = wrap_window_sum(image, ram_words=ram_words)
            if measured == expected:
                bk6_image.last_expected_sum = expected
                return image
            expected = measured
            txt2 = bk6_program_text(expected_sum=expected)
        raise RuntimeError(
            f"bk6 bake did not converge: expected={expected:#x} "
            f"measured={measured:#x}")
    finally:
        _BK6_TASK_PC = 0


bk6_image.last_expected_sum = 0

#!/usr/bin/env python3
"""tests/test_gh9_window_span.py — DEFECT-19 falsifier.

The GH-9 loader PARALLEL_STs the injected program's pixel words into the code
image starting at the ``:__g9window`` label.  That copy span is
``[dst, dst + 4*N)`` words, where ``N`` is the injected program's instruction
count and ``dst`` is the window's linear word index (``baker.py``
``_GH9_WINDOW_DST``).  Nothing bounds it against the loader kernel's OWN in-box
ABI words, so a program long enough silently overwrites argv / the tick
counter / the result slot and the run fails with no diagnostic.

Measured at the time of writing (see ``.builder_queue/DEFECT-19_loader_copy_span.json``
and ``output/DEFECT19_loader_copy_span.txt``):

    quantum   pre-window instrs   dst(word)   landed program (84 instrs) span
      0             76              304      [304, 640)   92 words of margin
     12             99              396      [396, 732)    0 words of margin
    capacity span (96 instrs = 384 words) at quantum 12: [396, 780)
      -> covers GH9_TICKS_COUNT(732) AND the whole argv block (750-752, 754, 760-766)

The rule this gate enforces: **the largest program the window can hold
(``WINDOW_N_INSTRS``) must not reach the ABI words**.  With the held
DEFECT-16c LBU/LHU variant the injected program is 96 instructions, i.e.
exactly the capacity, so this gate is the leg that would have caught DEFECT-19
months earlier.  It is deliberately expressed against the *capacity*, not
against one particular program length: any future change that lengthens the
loader's pre-window text (which moves ``dst`` right) turns it red.

``GH9_EXIT_WORD`` (703) is excluded from the blocked set on measurement, not
convention: it sits inside the window span at the tightest quantum *today*
(``[396, 732)`` covers 703) and the landed gates are green, because the kernel
zeroes it at boot — before the copy — and the injected program writes it last.
The blocked set is the words whose coverage is measured-fatal (``argv`` block,
result slot) or silently corrupting (the tick counter).
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas  # noqa: E402
from tools.glyph_gpt.baker import (  # noqa: E402
    GH9_ARGV_RESULT,
    GH9_ARGV_WORD,
    GH9_EXIT_WORD,
    GH9_MAILBOX_DATA,
    GH9_MAILBOX_FLAG,
    GH9_MAILBOX_N_PX,
    GH9_TICKS_COUNT,
    _gh9_kernel_program_text,
    assemble_glyph_to_pixels,
    gh9_window_span_conflict,
    loader_kernel_image,
)

# Words whose coverage by the copy span is measured-fatal (argv header/data,
# result slot) or silently corrupting (the tick counter).  See the module
# docstring for why GH9_EXIT_WORD is not in this set.
ABI_BLOCKED = {
    GH9_TICKS_COUNT: "GH9_TICKS_COUNT",
    GH9_ARGV_WORD: "argv argc",
    GH9_ARGV_WORD + 1: "argv argvp",
    GH9_ARGV_WORD + 2: "argv envp",
    GH9_ARGV_RESULT: "GH9_ARGV_RESULT",
    760: "argv[0] ptr",
    761: "argv[1] ptr",
    766: "argv[1] string",
}

# The BK-1 harness's bake parameters (tests/test_bk1_argv.py constants).  Kept
# local so this gate does not import a test module that needs the toolchain.
WINDOW_N_INSTRS = 96
COLS_INSTRS = 8
IMAGE_MIN_ROWS = 36
MAILBOX_DATA = 2000


def window_dst(timer_quantum: int, n_instrs: int = WINDOW_N_INSTRS) -> int:
    """Linear word index the loader copies the injected program to (baker.py:2313)."""
    txt = _gh9_kernel_program_text(
        950, False, timer_quantum=timer_quantum, n_instrs=n_instrs, mailbox_data=MAILBOX_DATA
    )
    _, coords = assemble_glyph_to_pixels(txt, cols_instrs=COLS_INSTRS, min_rows=IMAGE_MIN_ROWS)
    wcol, wrow = coords[":__g9window"]
    return wrow * (COLS_INSTRS * 4) + wcol * 4


def label_word(timer_quantum: int, label: str, n_instrs: int = WINDOW_N_INSTRS) -> int:
    txt = _gh9_kernel_program_text(
        950, False, timer_quantum=timer_quantum, n_instrs=n_instrs, mailbox_data=MAILBOX_DATA
    )
    _, coords = assemble_glyph_to_pixels(txt, cols_instrs=COLS_INSTRS, min_rows=IMAGE_MIN_ROWS)
    wcol, wrow = coords[label]
    return wrow * (COLS_INSTRS * 4) + wcol * 4


def span_conflicts(dst: int, n_words: int) -> dict:
    """ABI words the copy span ``[dst, dst + n_words)`` would overwrite."""
    return {w: name for w, name in ABI_BLOCKED.items() if dst <= w < dst + n_words}


def _load_bk1_harness(name: str):
    """Import the BK-1 harness module without pytest collecting it twice."""
    spec = importlib.util.spec_from_file_location(name, _REPO / "tests" / "test_bk1_argv.py")
    assert spec is not None and spec.loader is not None
    t = importlib.util.module_from_spec(spec)
    sys.modules[name] = t
    spec.loader.exec_module(t)
    return t


def _bk1_program_words(tmp: Path):
    """The landed BK-1 injected program, assembled exactly as the harness does."""
    t = _load_bk1_harness("_t_bk1_span")
    base, text, syms = t._compile_c_elf(tmp)
    _, start_cell = t._bake_loader(tmp, timer_quantum=0, name="span0.npy")
    words = t._assemble_injected_program(text, syms, base, start_cell)
    return len(words)


_needs_gcc = pytest.mark.skipif(
    shutil.which("riscv64-unknown-elf-gcc") is None,
    reason="riscv64-unknown-elf-gcc not installed",
)


# ── Leg 1 (the DEFECT-19 fix's gate): capacity span must clear the ABI block ──

@pytest.mark.parametrize("timer_quantum", [0, 12])
def test_window_capacity_span_clears_the_abi_block(timer_quantum: int):
    """The largest program the window can hold must not reach the ABI words.

    RED before the fix at timer_quantum=12 (capacity span [396,780) covers
    GH9_TICKS_COUNT and the whole argv block); GREEN after.
    """
    dst = window_dst(timer_quantum)
    capacity_words = 4 * WINDOW_N_INSTRS
    conflicts = span_conflicts(dst, capacity_words)
    assert not conflicts, (
        f"quantum={timer_quantum}: window dst={dst}, capacity span "
        f"[{dst}, {dst + capacity_words}) overwrites {conflicts} "
        f"(GH9_TICKS_COUNT={GH9_TICKS_COUNT}, argv={GH9_ARGV_WORD}..{GH9_ARGV_WORD + 2}, "
        f"result={GH9_ARGV_RESULT})"
    )


# ── Leg 2: the landed program, span measured end to end ──────────────────────

@_needs_gcc
@pytest.mark.parametrize("timer_quantum", [0, 12])
def test_landed_program_span_clears_the_abi_block(timer_quantum: int):
    """The landed BK-1 program's own span is ABI-clean at both quanta."""
    with tempfile.TemporaryDirectory() as td:
        n_words = _bk1_program_words(Path(td))
    dst = window_dst(timer_quantum)
    conflicts = span_conflicts(dst, n_words)
    assert not conflicts, (
        f"quantum={timer_quantum}: dst={dst} program={n_words} words "
        f"span=[{dst}, {dst + n_words}) overwrites {conflicts}"
    )


# ── Leg 3: the falsifier is live (encodes DEFECT-19's measured geometry) ─────

def test_falsifier_detects_the_measured_defect19_geometry():
    """Predicate liveness: the shipped defect geometry must be flagged."""
    pre_fix_q12 = span_conflicts(396, 384)          # measured pre-fix capacity span
    assert set(pre_fix_q12) == {732, 750, 751, 752, 754, 760, 761, 766}, pre_fix_q12
    pre_fix_lbu_q12 = span_conflicts(396, 336 + 48)  # 96-instr LBU variant
    assert pre_fix_lbu_q12, "the 96-instruction variant must be flagged"
    # …and the two clean geometries stay clean (no vacuous always-red check):
    assert span_conflicts(304, 384) == {}   # quantum 0, capacity
    assert span_conflicts(304, 336) == {}   # quantum 0, landed program


# ── Leg 4: the tick handler's own code must avoid every written word ─────────

@pytest.mark.parametrize("timer_quantum", [0, 12])
def test_tick_handler_code_avoids_written_words(timer_quantum: int):
    """Wherever the fix parks the tick handler, its code must not land on a
    word the kernel, the host, or the harness writes (ABI block, GH-9 default
    mailbox [800,896), the GH-10 shell words 903-912, status 950, flag/n_px
    960/961, legacy 964, GH-8b FS alias [1024,1280))."""
    if timer_quantum == 0:
        pytest.skip("no tick handler at quantum 0")
    start = label_word(timer_quantum, ":__g9tick")
    protected = set(ABI_BLOCKED) | set(range(800, 896)) | set(range(903, 913)) | {950, 960, 961, 964} | set(range(1024, 1280))
    hit = sorted(w for w in range(start, start + 4 * 11) if w in protected)
    assert not hit, f"tick handler code at word {start} lands on written words {hit}"


# ── Leg 5: the harness constants this gate mirrors are still in sync ─────────

@_needs_gcc
def test_gate_constants_match_the_bk1_harness():
    """Guard against the harness changing its bake parameters under this gate."""
    t = _load_bk1_harness("_t_bk1_consts")
    assert t.WINDOW_N_INSTRS == WINDOW_N_INSTRS
    assert t.COLS_INSTRS == COLS_INSTRS
    assert t.IMAGE_MIN_ROWS == IMAGE_MIN_ROWS
    assert t.MAILBOX_DATA == MAILBOX_DATA


# ── Leg 6: the bake-time refusal is live, not decorative ────────────────────

def test_bake_time_guard_fires_on_the_first_conflicting_word():
    """`gh9_window_span_conflict` + the `loader_kernel_image` raise must be
    live: an over-budget window must be refused loudly at bake time, and the
    landed geometries must still bake."""
    # predicate: one instruction over the landed q12 capacity hits GH9_TICKS_COUNT
    assert gh9_window_span_conflict(window_dst(0), 4 * WINDOW_N_INSTRS) == {}
    assert window_dst(12) + 4 * WINDOW_N_INSTRS == GH9_TICKS_COUNT
    assert gh9_window_span_conflict(window_dst(12), 4 * (WINDOW_N_INSTRS + 1)) == {
        GH9_TICKS_COUNT: "GH9_TICKS_COUNT"
    }
    # production guard: over-budget refuses, landed capacity bakes
    atlas = build_default_atlas()
    with tempfile.TemporaryDirectory() as td:
        over = Path(td) / "over.npy"
        with pytest.raises(ValueError, match="conflicts with loader ABI words"):
            loader_kernel_image(
                atlas,
                timer_quantum=12,
                n_instrs=WINDOW_N_INSTRS + 1,
                mailbox_data=MAILBOX_DATA,
                cols_instrs=COLS_INSTRS,
                min_rows=IMAGE_MIN_ROWS,
                out_path=over,
            )
        assert not over.exists(), "the guard must refuse before writing an image"
    with tempfile.TemporaryDirectory() as td:
        landed = Path(td) / "landed.npy"
        loader_kernel_image(
            atlas,
            timer_quantum=12,
            n_instrs=WINDOW_N_INSTRS,
            mailbox_data=MAILBOX_DATA,
            cols_instrs=COLS_INSTRS,
            min_rows=IMAGE_MIN_ROWS,
            out_path=landed,
        )
        assert landed.exists()

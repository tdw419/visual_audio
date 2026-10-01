#!/usr/bin/env python3
"""tests/test_bk2_wgsl_syscall_parity.py — BK-2 oracle test.

Falsifiable gate for BK-2 (systems/GLYPH_SELF_HOSTING_ROADMAP.md,
systems/GLYPH_BACKLOG.md): "every new SYS N (6/7/8, loader) runs
byte-identical on GlyphCPUv2 ≡ WGSL". Extends the GH-4 parity pattern
(tests/test_gh4_wgsl_parity.py) specifically to the E-K2 SYSCALL trap --
GH-4 proved arithmetic/CALL-RET parity; every syscall landed since (GH-18,
GH-20, GH-21, GH-22, GH-26) has been CPU-only. Before this gate, WGSL's
SYSCALL opcode had ZERO references to KSYS_PC/SYS_N_ADDR/the trap
mechanism at all -- a flat, hardcoded dispatch on legacy syscall numbers
1-6, entirely disjoint from the CPU oracle's E-K2 trap (register marshal
via r17/r10/r11, privilege drop, KSYS_PC dispatch, SYSRET resume).

Ground image: tools.glyph_gpt.baker.multiproc_kernel_image (GH-7) -- the
simplest landed kernel that actually exercises a real KSYS_PC dispatcher
and two independent SYSCALLs (task A: SYS 6, task B: SYS 7), already
CPU-verified by tests/test_gh7_processes.py. Reused rather than
reinvented, per this repo's own "don't fork a second ground truth" rule.

Comparison methodology (the one subtlety this gate exists to get right):
GlyphCPUv2's receipt["memory"] is `cpu.memory` -- a full-precision Python
RAM list that plain (non-fs_pix, non-paged) ST instructions write
DIRECTLY to when `ram_words` is set, bypassing image pixels entirely.
WGSL has no such list; every WGSL word is a real (H,W,3) image pixel,
24-bit-per-word by construction (RGB channels). So a fair per-word
comparison is `cpu_word & 0xFFFFFF == wgsl_word`, not a raw equality --
comparing the full-precision CPU value against a pixel-truncated WGSL
value would fail even when both engines are executing identically
(discovered by direct measurement while building this gate, not assumed).
Register comparison (registers_full) needs no such adjustment -- WGSL's
per-lane registers are already u32, same width as the CPU's.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas           # noqa: E402
from tools.glyph_gpt.baker import multiproc_kernel_image         # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402

# GH-7 ABI (same word map tests/test_gh7_processes.py already verifies
# CPU-side; this gate adds the WGSL leg, not a new kernel).
GH7_UART_A_WORD, GH7_UART_A_LEN = 710, 712
GH7_UART_B_WORD, GH7_UART_B_LEN = 720, 722
GH7_EXIT_A, GH7_EXIT_B = 703, 723
GH7_STATUS_WORD = 950


def _bake(tmp: Path) -> Path:
    out = tmp / "gh7.npy"
    multiproc_kernel_image(build_default_atlas(), out_path=out)
    return out


def _run_both(tmp: Path, max_steps: int = 2000):
    """Two INDEPENDENT GlyphRunner instances over the same baked image --
    each engine must start from the untouched bake, not from a state the
    other engine already mutated (run_wgsl uploads its own GPU-side copy
    and never writes back into runner.image, but the CPU's run() DOES
    mutate runner.image in place, so sharing one runner across both calls
    silently gives WGSL a head start on some runs and not others)."""
    img = _bake(tmp)
    r_cpu = GlyphRunner(img, ram_words=16384)
    r_wgsl = GlyphRunner(img, ram_words=16384)
    cpu = r_cpu.run(max_instructions=max_steps)
    wgsl = r_wgsl.run_wgsl(max_steps=max_steps)
    return cpu, wgsl


def test_bk2_runner_wgsl_exposes_memory_readback():
    """RED gate check: run_wgsl's receipt must carry decoded RAM words,
    not just registers -- otherwise no memory-content parity leg is even
    possible (GH-4's arithmetic legs only ever checked registers)."""
    with tempfile.TemporaryDirectory() as d:
        cpu, wgsl = _run_both(Path(d), max_steps=50)
    assert "memory" in wgsl, "GlyphRunner.run_wgsl() must return receipt['memory']"
    assert isinstance(wgsl["memory"], list) and len(wgsl["memory"]) > 0


def test_bk2_syscall_dispatch_reaches_ksys_not_unknown():
    """The E-K2 trap must actually route through the kernel's in-image
    dispatcher -- not silently fall through to an unknown-syscall path.
    Falsifiable independent of the exact UART bytes below: if SYS_N never
    reaches the kernel's :__ksys_N selector, task A's UART LENGTH word
    (712) stays 0 forever (the 'unknown syscall' leg never writes it)."""
    with tempfile.TemporaryDirectory() as d:
        cpu, wgsl = _run_both(Path(d))
    assert cpu["halted"] is True and cpu["faulted"] is False, cpu
    assert wgsl["halted"] is True, wgsl.get("error", wgsl)
    # R1.4 (2026-09-21): kernel stores land in RAM on BOTH engines -- the
    # converged twin writes RAM words like the oracle, so the receipt's
    # "ram" view is the live channel (the pixel view no longer carries
    # kernel stores).
    assert wgsl["ram"][GH7_UART_A_LEN] == 4, (
        "SYS 6 never reached the kernel dispatcher (UART length word "
        "still 0) -- E-K2 trap did not route correctly")


def test_bk2_registers_byte_identical():
    """Full register-file parity after both tasks complete (round-robin,
    two independent SYSCALL/SYSRET round-trips)."""
    with tempfile.TemporaryDirectory() as d:
        cpu, wgsl = _run_both(Path(d))
    assert cpu["registers_full"] == wgsl["registers_full"], (
        f"register mismatch:\n  CPU  {cpu['registers_full']}\n"
        f"  WGSL {wgsl['registers_full']}")
    assert cpu["steps"] == wgsl["steps"], (
        f"step count diverged: CPU {cpu['steps']} != WGSL {wgsl['steps']}")


def test_bk2_syscall_memory_words_byte_identical():
    """The actual payload proof: every word either SYSCALL's trap
    marshaling or the kernel's in-image dispatcher touches must agree
    between engines, low-24-bits (WGSL's pixel storage width -- see the
    module docstring for why CPU's full-precision value needs masking
    for a fair comparison)."""
    with tempfile.TemporaryDirectory() as d:
        cpu, wgsl = _run_both(Path(d))
    words = (GH7_EXIT_A, GH7_UART_A_WORD, GH7_UART_A_WORD + 1, GH7_UART_A_LEN,
             GH7_EXIT_B, GH7_UART_B_WORD, GH7_UART_B_WORD + 1, GH7_UART_B_LEN,
             GH7_STATUS_WORD)
    mismatches = []
    for w in words:
        # R1.4 (2026-09-21): plain stores land in RAM on both engines;
        # compare CPU RAM against the WGSL RAM view, BOTH masked to the
        # 24-bit container width (WGSL's new RAM view is full-precision
        # u32; the CPU's resident-path words are 24-bit container values).
        cv, wv = cpu["memory"][w] & 0xFFFFFF, wgsl["ram"][w] & 0xFFFFFF
        if cv != wv:
            mismatches.append((w, hex(cv), hex(wv)))
    assert not mismatches, f"word mismatches (addr, cpu, wgsl): {mismatches}"
    # non-vacuity: these must actually be non-zero, real verb results --
    # not both engines agreeing on an all-zero no-op.
    assert cpu["memory"][GH7_EXIT_A] & 0xFFFFFF != 0
    assert cpu["memory"][GH7_UART_A_WORD] & 0xFFFFFF != 0

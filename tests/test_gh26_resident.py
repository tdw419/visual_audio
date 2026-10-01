"""GH-26.4 gate: tests/test_gh26_resident.py.

Roadmap: GH-26 Agent-in-the-Loop, Tier 3 RESIDENT (26.4) — the agent's
*program* runs as a USER task in its own box on the preemptive timer
(GH-16), receives work via mailbox (argv @750/@752), publishes results
via mailbox (result @754). The AI session drives the box from outside
(Tier 2 emit, geos_emit.py); the box itself is real scheduled OS work,
not a simulation. Working memory beyond the box size pages through the
GH-25 PTE_HILB frames (first resident-viewport consumer, vpn 13).

Ticket gh26-4-resident gate requirements mapped to legs:
  1. resident daemon completes a verb under preemptive tick; result word
     lands in the box window after the argv post (GH-22 word semantics
     on the argv channel).
  2. two agent boxes + one driver box coexist, zero violations (GH-16
     scheduling + box isolation, adversarial: neighbor integrity under
     concurrent agents).
  3. adversarial: a resident task faulting on an out-of-box store does
     NOT corrupt neighbor boxes (E-K1 reap; BOX1 completes; BOX2 window
     bytes unchanged).
  4. adversarial: preemption does not lose box register context (result
     correct when the tick lands mid-compute; done-flag word stable
     across the tick boundary).
  5. paged working memory: the daemon's working set exceeds its box, so
     the bytecode walks vpn 13 through a GH-25 PTE_HILB frame — the
     frame word carries the computed result AFTER the walk (payload
     lands in image pixels, not RAM).
  6. ticks actually serviced (non-vacuity: the GH-16 timer fired).
  7. canonical replay fixpoint: a second identical drive from the same
     image yields the identical final surface word (md5-stable state).
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402 (RED)
    resident_image, RES_KERNEL_OK, RES_FAULT_SEEN, RES_HILB_PAYLOAD,
)

QUANTUM = 12          # tight timer: ticks land while tasks are mid-compute
ARGV0 = 0x2A          # argv posted for BOX0: the daemon's verb input
RESULT0 = ARGV0 * 3   # the triple() daemon verb
RESULT1 = ARGV0 * 4   # BOX1's independent quadruple() result


def _argv_word(v: int) -> int:
    """GH-22 mailbox word: cksum[31:24]=(op+payload)&0xFF | op[15:8] |
    payload[7:0]. The argv channel posts op 0x11, payload v."""
    op, payload = 0x11, v & 0xFF
    return (((op + payload) & 0xFF) << 24) | (op << 8) | payload


def _bake(tmp: Path, mode: str = "resident", quantum: int = QUANTUM) -> Path:
    out = tmp / "gh264.glyph.npy"
    resident_image(build_default_atlas(), mode=mode, timer_quantum=quantum,
                   out_path=out)
    return out


def _run(tmp: Path, mode: str = "resident", quantum: int = QUANTUM):
    runner = GlyphRunner(_bake(tmp, mode, quantum), ram_words=16384)
    receipt = runner.drive(seeds={}, max_instructions=60000)
    return runner, receipt


def _img_md5(runner: GlyphRunner) -> str:
    return hashlib.md5(
        np.ascontiguousarray(runner.image).tobytes()).hexdigest()


# ── leg 1: resident daemon services a verb under preemptive tick ────────

def test_gh264_resident_daemon_completes_verb_under_preemption():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d))
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # result word landed in the BOX2 tile-ABI window after the argv post
        assert mem[754] == RESULT0, (
            f"result word {mem[754]:#x} != {RESULT0:#x}")
        # the argv post itself was consumed intact (GH-22 word semantics)
        assert mem[750] == _argv_word(ARGV0), hex(mem[750])
        # kernel reached the end of schedule with a clean status word
        assert receipt["status_word_value"] == RES_KERNEL_OK, receipt
        # the syscall-tile result was delivered through SYSRET as well
        # (Task B runs after Task A in round-robin; r10 reflects the last SYSRET)
        assert receipt["registers_full"][10] == RESULT1, (
            f"a0 {receipt['registers_full'][10]:#x} != {RESULT1:#x}")
        assert mem[733] == RESULT1, f"BOX1 result {mem[733]:#x} != {RESULT1:#x}"


# ── leg 2: two agent boxes + one driver box coexist, zero violations ────

def test_gh264_two_agent_boxes_and_driver_box_coexist():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d))
        assert receipt["halted"] is True and not receipt["faulted"], receipt
        mem = receipt["memory"]
        # BOX0 triple() finished and lit its done bit
        assert mem[717] & 1, f"BOX0 done flag clear: {mem[717]:#x}"
        # BOX1 quadruple() finished independently (no cross-box writes)
        assert mem[752] == ARGV0, f"BOX1 argv disturbed: {mem[752]:#x}"
        # kernel drove BOTH completion bits (0b11) through the shared word
        assert mem[717] == 3, f"done flags {mem[717]:#x} != 0b11"
        assert receipt["status_word_value"] == RES_KERNEL_OK, receipt
        # BOX2 driver window untouched by either agent (no writes into
        # the driver box's scratch/checkpoint words)
        assert mem[736] == 0 and mem[755] == 0, "BOX2 window dirtied"


# ── leg 3: adversarial — daemon fault does not corrupt neighbor boxes ───

def test_gh264_daemon_fault_does_not_corrupt_neighbor_boxes():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        runner, receipt = _run(tmp, mode="fault")
        assert receipt["halted"] is True, receipt.get("error", receipt)
        mem = receipt["memory"]
        # the kernel reaped the offending agent through its fault handler
        assert mem[731] == RES_FAULT_SEEN, (
            f"fault word {mem[731]:#x} != {RES_FAULT_SEEN:#x}")
        # the violation store never landed (word 800 is outside every box)
        assert mem[800] == 0, "out-of-box store escaped isolation"
        # the faulting agent never completed
        assert not (mem[717] & 1), "faulted agent lit its done bit"
        # the NEIGHBOR agent still ran to completion, byte-intact:
        # BOX1 finished inside the tainted image (BOX0's box bytes were
        # zero at bake, the violating store was suppressed, and BOX1's
        # own arena words are untouched — the byte-exact neighbor proof
        # is the diff on the PUBLISHED surface below).
        # neighbor-integrity: the post-fault image's BOX1 PRIVATE arena
        # words match a clean coexist run's word-for-word. The slice
        # deliberately SKIPS the two shared kernel receipt words embedded
        # in BOX1's numeric span (measured diff,
        # output/dbg_gh264_faultslice.py): 731 = RES_FAULT_WORD (the
        # kernel's own fault receipt — set by the fault run, legitimately
        # zero in the clean run; comparing it here would contradict this
        # same test's mem[731] assertion above) and 732 = RES_TICKS_COUNT
        # (tick counts legitimately diverge — the fault leg faults before
        # the first tick fires). Those are the KERNEL's words, not BOX1's.
        _, clean = _run(tmp, mode="resident")
        clean_mem = clean["memory"]
        assert mem[718:731] == clean_mem[718:731], (
            "BOX1 arena diverged under the neighbor's fault")
        assert mem[733:735] == clean_mem[733:735], (
            "BOX1 words 733-734 diverged under the neighbor's fault")
        assert mem[717] & 2, "BOX1 never completed after neighbor fault"


# ── leg 4: adversarial — preemption does not lose box register context ──

def test_gh264_preemption_does_not_lose_box_register_context():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        runner, receipt = _run(tmp, mode="resident", quantum=6)
        assert receipt["halted"] is True and not receipt["faulted"], receipt
        mem = receipt["memory"]
        # a tick DID land while a USER task was mid-compute (the timer was
        # armed at quantum 6 — far below the task's instruction budget)
        assert mem[732] >= 1, "no tick serviced; context leg is vacuous"
        # the mid-compute result survived every preemption word-exactly
        assert mem[754] == RESULT0, (
            f"result word {mem[754]:#x} != {RESULT0:#x} after preemption")
        # BOX1's independent result likewise survived
        assert mem[752] == ARGV0, "BOX1 argv corrupted across ticks"
        # done-flag word stable across the tick boundary: no torn write
        assert mem[717] in (0, 1, 3), f"torn done flags {mem[717]:#x}"
        assert mem[717] == 3, "agents did not both complete under ticks"
        assert receipt["status_word_value"] == RES_KERNEL_OK, receipt


# ── leg 5: working memory beyond box size pages via GH-25 PTE_HILB ──────

def test_gh264_working_memory_pages_through_hilbert_frames():
    """The resident daemon's working set exceeds its box: the bytecode
    writes its computed result to vpn 13 (word 3328 — OUTSIDE every box
    and outside identity-mapped RAM pages), which walks PTE_HILB and
    lands in Hilbert frame slot 5 IN IMAGE PIXELS."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        runner, receipt = _run(tmp, mode="paged")
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # the frame walk produced the same result the register ABI did
        assert mem[754] == RESULT0, f"result {mem[754]:#x} != {RESULT0:#x}"
        # the paged word is NOT in RAM (outside identity pages 0..3 and
        # never allocated): RAM word 3328 stayed untouched by the store
        assert mem[3328] == 0, "paged store landed in RAM, not the frame"
        # the payload IS in the image at the slot-5 Hilbert frame origin
        # (word 5 of the frame): first resident-viewport consumer
        img = np.ascontiguousarray(runner.image)
        w = img.shape[1]
        from tools.geos_hilbert import hilbert_d2xy_true
        from tools.glyph_gpt.gh25_hilbert_paging import (
            hilbert_frame_pix_word, HILB_SIDE, PAGE_WORDS)
        col, row = hilbert_d2xy_true(HILB_SIDE, 5)
        base = hilbert_frame_pix_word((row << 8) | col, 0)
        pix = base + 5                       # vaddr 3328 -> offset 5
        assert pix < img.shape[0] * w, "frame slot 5 outside the image"
        px = img[pix // w, pix % w]
        word = (int(px[0]) << 16) | (int(px[1]) << 8) | int(px[2])
        assert word == RES_HILB_PAYLOAD, (
            f"frame word {word:#x} != {RES_HILB_PAYLOAD:#x}")
        assert receipt["status_word_value"] == RES_KERNEL_OK, receipt


# ── leg 6: non-vacuity — the GH-16 timer actually fired ─────────────────

def test_gh264_ticks_serviced():
    with tempfile.TemporaryDirectory() as d:
        _, receipt = _run(Path(d))
        assert receipt["halted"] is True and not receipt["faulted"], receipt
        assert receipt["memory"][732] >= 1, (
            f"expected >= 1 tick serviced, got {receipt['memory'][732]}")


# ── leg 7: canonical replay fixpoint ────────────────────────────────────

def test_gh264_canonical_replay_fixpoint():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        img = _bake(tmp)
        r1 = GlyphRunner(img, ram_words=16384).drive(
            seeds={}, max_instructions=60000)
        r2 = GlyphRunner(img, ram_words=16384).drive(
            seeds={}, max_instructions=60000)
        for r in (r1, r2):
            assert r["halted"] and not r["faulted"], r
        assert r1["memory"] == r2["memory"], "replay diverged"
        assert r1["registers_full"] == r2["registers_full"]
        assert r1["memory"][754] == RESULT0 and r2["memory"][754] == RESULT0


# ── leg 8: runner budget invariant (GH-5) still honest ──────────────────

def test_gh264_runner_line_budget():
    lines = (_REPO / "tools" / "glyph_gpt" / "runner.py").read_text().splitlines()
    assert len(lines) <= 200, f"runner.py exceeds 200 lines: {len(lines)}"

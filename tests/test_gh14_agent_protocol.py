"""tests/test_gh14_agent_protocol.py — GH-14 oracle test.

The capstone of the self-hosting arc: N=2 simulated agent SESSIONS share
ONE baked image file. Each session owns exactly one box (memory-ownership
extended from GH-13's path-ownership); all cross-session data flows
through kernel-mediated channels. Unlike GH-13 (the kernel drives all
agents inside one run), GH-14 is HOST-DRIVEN: two separate GlyphRunner
sessions — one per agent — take turns on the same persisted image,
exactly as two real AI sessions would. The host helper performs the
writeback (np.save of the runner's live image) between sessions, the
host-side analogue of the interactive pixel backend's writeback timer.

Scenario (roadmap cell GH-14):
  1. The kernel bakes with a work-ticket file table in the GH-8 pixel FS:
     slot0 = TICK_A (payload 7), slot1 = TICK_B (payload 5). Seeding is
     idempotent (GH-8 rule): session B's boot sees in_use=1 and leaves
     the persisted pixels untouched.
  2. Session A (BOX0): claims TICK_A via the FS-claim syscall, performs
     the work IN ITS BOX (result = payload * 2 = 14), writes its receipt
     to its uart, signals via SYS 3 (mailbox 754 + pixel-FS receipt word
     1048), exits 0xFEED0001.
  3. Session B (BOX1) reopens the SAME image file offline: claims TICK_B,
     performs its work (payload * 3 = 15), receives A's result through
     the ONLY cross-session channel — the pixel-FS receipt (SYS 4 recv,
     kernel copies 1048 -> B's read-out 720) — combines (15 + 14 = 29),
     receipts to its uart, signals into pixel-FS slot 1 (1049), exits
     0xFEED0002. Kernel writes status 0xCAFE0000 | 2.
  4. Byte-exactness: both receipts equal the single-agent reference
     computed host-side.

Image ABI (fixed word indices; GH-13's scheme, 2 boxes):
  BOX0 = agent A [700..717), BOX1 = agent B [718..735)
  703 / 723        agent exit words (0xFEED0001 / 0xFEED0002)
  710 / 730        per-agent uart receipt
  720/721          agent read-out (kernel delivers ticket payload / recv)
  724              ticket-claim verdict ('V' / 'E')
  754              agent->agent mailbox (within-session signal; RAM)
  758 / 759        unknown-syscall marker / fault-leg verdict (0xFA171)
  760              host agent selector (seed: 1 = A, 2 = B)
  1024..           GH-8 pixel FS: slot0 TICK_A, slot1 TICK_B,
                   data 1044..1047, receipts 1048 (A) / 1049 (B)
  950              kernel status word (0xCAFE0000 | 2)
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import agent_protocol_kernel_image    # noqa: E402

# ── image ABI (baker.py constants, mirrored — do not renumber) ──────────
GH14_EXIT_A, GH14_EXIT_B = 703, 723
GH14_UART_A = 710
GH14_UART_B = 730
GH14_READOUT_B = 720
GH14_VERDICT = 724
GH14_MAILBOX = 754
GH14_SELECT_WORD = 760
GH14_BADSYS_WORD = 758
GH14_FAULT_WORD = 759
GH14_RSLT_A = 1048           # pixel-FS receipt: agent A's result
GH14_RSLT_B = 1049           # pixel-FS receipt: agent B's combined result
GH14_N_A, GH14_N_B = 1, 2

GH14_EXIT_OK_A = 0xFEED0000 | GH14_N_A
GH14_EXIT_OK_B = 0xFEED0000 | GH14_N_B
GH14_FAULT_SEEN = 0xFA171
GH14_STATUS_OK = 0xCAFE0000 | 2
VERIFIED = ord("V")

# single-agent reference (host-computed)
A_PAYLOAD, B_PAYLOAD = 7, 5
REF_A = (A_PAYLOAD * 2) & 0xFFFFFFFF          # 14
REF_B = ((B_PAYLOAD * 3) + REF_A) & 0xFFFFFFFF  # 29


def _bake(tmp: Path, name: str = "gh14.glyph.npy",
          fault_leg: bool = False) -> Path:
    out = tmp / name
    agent_protocol_kernel_image(build_default_atlas(), fault_leg=fault_leg,
                                out_path=out)
    return out


def _session(img: Path, agent: int, max_instructions: int = 80000) -> dict:
    """One agent session: a GlyphRunner on the SHARED image file + host
    writeback. The kernel's FS stores land on the runner's LIVE image
    (GH-8b pixel aliasing); the host persists them so the next session's
    fresh runner reads the updated pixels."""
    runner = GlyphRunner(img, ram_words=16384)
    receipt = runner.drive(seeds={GH14_SELECT_WORD: agent},
                           max_instructions=max_instructions)
    np.save(img, runner.image)
    return receipt


def test_gh14_image_bakes():
    with tempfile.TemporaryDirectory() as d:
        assert _bake(Path(d)).exists(), \
            "agent_protocol_kernel_image must emit one image"


def test_gh14_two_sessions_claim_work_and_combine():
    """Session A claims TICK_A, works, signals; session B (offline reopen
    of the same image) claims TICK_B, receives A's result through the
    pixel-FS receipt channel, combines, receipts. Final state is
    byte-exact vs the host-side single-agent reference."""
    with tempfile.TemporaryDirectory() as d:
        img = _bake(Path(d))

        # ── session A ──
        rec_a = _session(img, GH14_N_A)
        assert rec_a["faulted"] is False, rec_a
        ma = rec_a["memory"]
        assert ma[GH14_EXIT_A] == GH14_EXIT_OK_A, hex(ma[GH14_EXIT_A])
        assert ma[GH14_UART_A] == REF_A, \
            f"A result 0x{ma[GH14_UART_A]:08x} != 0x{REF_A:08x}"
        assert ma[GH14_MAILBOX] == REF_A, "A must signal via the mailbox"
        assert ma[GH14_VERDICT] == VERIFIED, "A's ticket claim must verify"

        # ── session B: NEW runner on the SAME image file ──
        rec_b = _session(img, GH14_N_B)
        assert rec_b["faulted"] is False, rec_b
        mb = rec_b["memory"]
        assert mb[GH14_EXIT_B] == GH14_EXIT_OK_B, hex(mb[GH14_EXIT_B])
        # B received A's result ONLY through the kernel-mediated channel
        assert mb[GH14_READOUT_B] == REF_A, \
            f"B read-out 0x{mb[GH14_READOUT_B]:08x} != 0x{REF_A:08x}"
        assert mb[GH14_UART_B] == REF_B, \
            f"B combined 0x{mb[GH14_UART_B]:08x} != 0x{REF_B:08x}"
        assert mb[GH14_VERDICT] == VERIFIED, "B's ticket claim must verify"
        # unknown-syscall marker untouched
        assert mb[GH14_BADSYS_WORD] == 0
        # final kernel status: 0xCAFE0000 | 2
        assert rec_b["status_word_value"] == GH14_STATUS_OK, rec_b

        # ── byte-exact vs single-agent reference ──
        assert (ma[GH14_UART_A], mb[GH14_UART_B]) == (REF_A, REF_B)
        # final FS receipts persist in the image PIXELS (the word-array
        # mirror only tracks RAM; the FS window is pixel-aliased, so
        # decode the persisted image the way the GH-8b gate does)
        final_img = np.load(img)
        assert _pw(final_img, GH14_RSLT_A) == REF_A, \
            "A's FS receipt must persist in the image pixels"
        assert _pw(final_img, GH14_RSLT_B) == REF_B, \
            "B's FS receipt must be written into the image pixels"


def _pw(image: np.ndarray, word: int) -> int:
    """GH-8b pixel decode: FS word W lives in LINEAR pixels (2W, 2W+1)
    (row-major over the image array): word = lo24 | hi8."""
    flat = image.reshape(-1, 3)
    lo = flat[2 * word]
    hi = flat[2 * word + 1]
    return ((int(lo[0]) << 16) | (int(lo[1]) << 8) | int(lo[2])) \
        | ((int(hi[2]) & 0xFF) << 24)


def test_gh14_session_a_receipt_persists_across_reopen():
    """The GH-8b property at protocol level: A's receipt survives in the
    image pixels between sessions — session B (or any later reader) sees
    A's work without any host-side relay of RAM state."""
    with tempfile.TemporaryDirectory() as d:
        img = _bake(Path(d))
        _session(img, GH14_N_A)
        # fresh runner, NO execution: pure offline read of the persisted
        # pixels — decode the image the way the GH-8b gate does
        fresh = np.load(img)
        assert _pw(fresh, GH14_RSLT_A) == REF_A, (
            f"A's FS receipt lost across reopen: 0x{_pw(fresh, GH14_RSLT_A):08x}")
        assert _pw(fresh, GH14_RSLT_B) == 0, "B must not have run yet"


def test_gh14_fault_leg_isolates():
    """Agent A's out-of-box store vectors to KFAULT_PC; the handler records
    0xFA171; agent B's slice never runs (its uart + exit stay zero)."""
    with tempfile.TemporaryDirectory() as d:
        img = _bake(Path(d), fault_leg=True)
        rec = _session(img, GH14_N_A, max_instructions=40000)
        mem = rec["memory"]
        assert mem[GH14_FAULT_WORD] == GH14_FAULT_SEEN, \
            f"fault verdict 0x{mem[GH14_FAULT_WORD]:08x}"
        assert mem[GH14_EXIT_B] == 0, "B must never run in the fault leg"
        assert mem[GH14_UART_B] == 0, "B's receipt must stay untouched"


def test_gh14_zero_dev_imports():
    """The baker growth stays in its lane: no dev-only imports (GH-11 AST
    gate, extended)."""
    src = (_REPO / "tools" / "glyph_gpt" / "baker.py").read_text()
    tree = ast.parse(src)
    banned = {"pytest", "tests", "conftest"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in banned, f"baker imports {root}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root not in banned, f"baker imports from {root}"


def test_gh14_runner_line_budget():
    """GH-11 invariant: runner.py stays <= 200 lines."""
    n = len((_REPO / "tools" / "glyph_gpt" / "runner.py")
            .read_text().splitlines())
    assert n <= 200, f"runner.py grew to {n} lines"

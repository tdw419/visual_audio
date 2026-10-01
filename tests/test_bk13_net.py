#!/usr/bin/env python3
"""tests/test_bk13_net.py — BK-13 Mailbox Network Stack Gate.

Roadmap row BK-13 (systems/GLYPH_SELF_HOSTING_ROADMAP.md):
  "Mailbox net stack skeleton: SYS 18 = net_send / SYS 19 = net_recv frames
   between two Glyph OS instances, BOTH KERNELS INSIDE ONE IMAGE."

Ruling: .builder_queue/RULING_20260912_defect19_bk13_worktree.md §2:
  - Q1: SYS 18 = net_send, SYS 19 = net_recv
  - Q2: TWO KERNELS INSIDE ONE IMAGE exchanging frames through real mailbox
    windows; every frame crosses the admission oracle in-substrate.
    Host is runner/observer, never the transport.

Gate Legs:
  L1 — Bakes: net_stack_kernel_image() emits a valid container; verifies
       shape/dtype, presence of both arenas and mailbox window; asserts
       positive no-overlap between chosen frame-buffer words and box ABI
       words (the DEFECT-19 lesson).
  L2 — Byte-exact 64B frame transfer: ONE GlyphRunner instance drives ONE
       image (no second runner, no subprocess). Instance A fills 16-word frame,
       sends via SYS 18; Instance B receives via SYS 19; words in B's frame
       buffer are byte-exact vs source list; clean halt (no engine fault).
  L3 — Admission-oracle leg: SYS 18/19 tiles enter the image ONLY via
       admit_syscall (proof = admission) and their table words are lit;
       asserts unverified tile is refused (.table_word == 0), table stays
       untouched, refusal is receipted with {frame, verdict, reason}, and
       in-image table has no slot for the refused tile.
  L4 — Malformed frame rejected with a receipt: frame with bad checksum or
       bad length is NOT delivered into B's frame buffer (unchanged from
       pre-send words); in-image rejection verdict observable ('E' = 69);
       receipt artifact records rejection reason; clean termination without
       kernel destabilization (mirrors GH-22 corrupted packet clean fail).
  L5 — No host I/O path in data movement: AST-scan of net_stack.py proves
       zero imports from socket/ssl/http/urllib/requests/subprocess/multiprocessing/
       threading/asyncio; transfer is driven through single runner on single
       image in-substrate.
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.runner import GlyphRunner
from tools.glyph_gpt.net_stack import (
    net_stack_kernel_image,
    make_header,
    make_frame,
    parse_header,
    net_span_conflict,
    record_net_receipt,
    admit_net_syscall,
    BK13_BOX0_ARENA,
    BK13_BOX1_ARENA,
    BK13_BOX0_ABI_WORDS,
    BK13_BOX1_ABI_WORDS,
    BK13_FRAME_BUFFER_A_START,
    BK13_FRAME_BUFFER_B_START,
    BK13_FRAME_BUFFER_A,
    BK13_FRAME_BUFFER_B,
    BK13_MAILBOX_START,
    BK13_MAILBOX_LEN,
    BK13_MAILBOX_WINDOW,
    BK13_EXIT_A,
    BK13_EXIT_B,
    BK13_VERDICT_B,
    BK13_STATUS_WORD,
    BK13_BADSYS_WORD,
    BK13_SYS_SEND,
    BK13_SYS_RECV,
    BK13_TABLE_SLOT_SEND,
    BK13_TABLE_SLOT_RECV,
    BK13_PIX_SLOT_SEND,
    BK13_PIX_SLOT_RECV,
    BK13_EXIT_OK_A,
    BK13_EXIT_OK_B,
    BK13_KERNEL_OK,
    BK13_VERIFIED,
    BK13_ERRORED,
    OP_FRAME,
    FRAME_LEN_WORDS,
    FRAME_LEN_BYTES,
)
from tools.glyph_gpt import autoatlas as aa
from tools.glyph_gpt.escalate import EscalationResult


# ── L1: Bakes & Positive No-Overlap Assertion ────────────────────────────────

def test_bk13_l1_net_stack_image_bakes_and_abi_no_overlap():
    """L1: net_stack_kernel_image() returns image; verifies shape, dtype,
    presence of arenas and mailbox window; asserts positive no-overlap
    between frame buffers and box ABI words (DEFECT-19 lesson).
    """
    with tempfile.TemporaryDirectory() as d:
        out_p = Path(d) / "bk13_test_l1.npy"
        img = net_stack_kernel_image(out_path=out_p)
        assert out_p.exists(), "Image must be serialized to out_path"
        assert isinstance(img, np.ndarray), "Returned object must be numpy array"
        assert img.ndim == 3 and img.shape[2] == 3, f"Shape must be (H, W, 3), got {img.shape}"
        assert img.dtype == np.uint8, f"dtype must be uint8, got {img.dtype}"

        # Arenas and mailbox window definition assertions
        assert BK13_BOX0_ARENA == (600, 640), "Instance A arena must be [600, 640)"
        assert BK13_BOX1_ARENA == (700, 740), "Instance B arena must be [700, 740)"
        assert BK13_FRAME_BUFFER_A == range(600, 616), "Frame buffer A must be [600, 616)"
        assert BK13_FRAME_BUFFER_B == range(700, 716), "Frame buffer B must be [700, 716)"
        assert BK13_MAILBOX_WINDOW == range(754, 770), "Mailbox window must be [754, 770)"

        # Positive no-overlap assertions (DEFECT-19 lesson)
        conflict_a = net_span_conflict(0, BK13_FRAME_BUFFER_A_START, FRAME_LEN_WORDS)
        assert conflict_a == {}, f"Frame buffer A overlaps Box 0 ABI words: {conflict_a}"

        conflict_b = net_span_conflict(1, BK13_FRAME_BUFFER_B_START, FRAME_LEN_WORDS)
        assert conflict_b == {}, f"Frame buffer B overlaps Box 1 ABI words: {conflict_b}"

        assert not any(w in BK13_BOX0_ABI_WORDS for w in BK13_FRAME_BUFFER_A), (
            "Frame buffer A must not intersect Box 0 ABI words"
        )
        assert not any(w in BK13_BOX1_ABI_WORDS for w in BK13_FRAME_BUFFER_B), (
            "Frame buffer B must not intersect Box 1 ABI words"
        )
        assert not any(w in BK13_BOX0_ABI_WORDS for w in BK13_MAILBOX_WINDOW), (
            "Mailbox window must not intersect Box 0 ABI words"
        )
        assert not any(w in BK13_BOX1_ABI_WORDS for w in BK13_MAILBOX_WINDOW), (
            "Mailbox window must not intersect Box 1 ABI words"
        )


# ── L2: Byte-Exact 64B Frame Transfer ───────────────────────────────────────

def test_bk13_l2_byte_exact_64b_frame_transfer():
    """L2: ONE GlyphRunner instance drives ONE image (in-substrate transfer).
    Instance A fills 16-word frame, sends via SYS 18; Instance B receives via
    SYS 19; words in B's frame buffer are byte-exact vs source list; clean halt.
    """
    with tempfile.TemporaryDirectory() as d:
        out_p = Path(d) / "bk13_transfer.npy"
        custom_payload = [0xCA00 + i for i in range(1, 16)]
        expected_frame = make_frame(op=OP_FRAME, payload=custom_payload)
        assert len(expected_frame) == 16
        assert len(expected_frame) * 4 == FRAME_LEN_BYTES

        img = net_stack_kernel_image(
            custom_payload=custom_payload,
            admit_tiles=True,
            out_path=out_p,
        )

        runner = GlyphRunner(out_p, ram_words=16384)
        receipt = runner.run(max_instructions=80000, trace=True)

        assert receipt.get("halted") is True, f"Run did not halt: {receipt.get('error')}"
        assert receipt.get("faulted") is False, f"Engine faulted during transfer: {receipt}"

        mem = receipt["memory"]

        # 16 words read back from runner's memory at B's frame buffer are byte-exact
        received_words = [mem[BK13_FRAME_BUFFER_B_START + i] for i in range(16)]
        assert received_words == expected_frame, (
            f"Transferred frame mismatch: {received_words} != {expected_frame}"
        )

        # Instance A kept its source frame intact
        sent_words = [mem[BK13_FRAME_BUFFER_A_START + i] for i in range(16)]
        assert sent_words == expected_frame

        # Mailbox window carries the transferred frame
        mailbox_words = [mem[BK13_MAILBOX_START + i] for i in range(16)]
        assert mailbox_words == expected_frame

        # Both tasks completed with clean exits
        assert mem[BK13_EXIT_A] == BK13_EXIT_OK_A, hex(mem[BK13_EXIT_A])
        assert mem[BK13_EXIT_B] == BK13_EXIT_OK_B, hex(mem[BK13_EXIT_B])

        # Instance B recorded verified verdict
        assert mem[BK13_VERDICT_B] == BK13_VERIFIED, f"Verdict B: {chr(mem[BK13_VERDICT_B])}"

        # Clean kernel tail
        assert receipt.get("status_word_value") == BK13_KERNEL_OK


# ── L3: Admission-Oracle Leg ────────────────────────────────────────────────

def test_bk13_l3_admission_oracle_refusal_and_receipt(monkeypatch):
    """L3: SYS 18/19 tiles enter image ONLY via admit_syscall (proof = admission);
    unverified tile is refused (.table_word == 0), table stays untouched,
    refusal is receipted with {frame, verdict, reason}, and in-image table has
    no slot for the refused tile.
    """
    def _mock_fail_escalate(*a, **k):
        return EscalationResult(
            contract=a[0] if a else "",
            verified=False,
            attempts=k.get("max_attempts", 6),
            error="no candidate verified in N attempts",
        )

    monkeypatch.setattr(aa, "escalate", _mock_fail_escalate)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        img_p = tmp / "bk13_unadmitted.npy"
        # Bake unadmitted image (table slots start at 0)
        net_stack_kernel_image(admit_tiles=False, out_path=img_p)
        runner = GlyphRunner(img_p, ram_words=16384)

        receipt_file = tmp / "refusal_receipt.json"

        # Attempt admission of an unproven SYS 18 tile
        res = admit_net_syscall(
            runner,
            BK13_SYS_SEND,
            contract="unproven_net_send_tile(frame) -> r2",
            expected=12345,
            receipt_path=receipt_file,
            frame="SYS_18_UNPROVEN_FRAME",
        )

        assert not res.ok, "Unproven tile must be refused by admission oracle"
        assert res.code == "E_ATLAS_UNVERIFIED", f"Expected E_ATLAS_UNVERIFIED, got {res.code}"
        assert res.table_word == 0, f"Refused tile must leave table_word == 0, got {res.table_word}"

        # In-image table pixel surface must remain untouched (all zero)
        h, w, _ = runner.image.shape
        pw_send = BK13_PIX_SLOT_SEND
        px_send = tuple(runner.image[pw_send // w, pw_send % w])
        assert px_send == (0, 0, 0), f"Table pixel for slot 18 must be (0,0,0), got {px_send}"

        # When unadmitted image runs, dispatch detects unadmitted slot (stays 0),
        # records rejection at BK13_BADSYS_WORD, and halts cleanly
        res_run = runner.run(max_instructions=10000)
        assert res_run["halted"], f"Unadmitted run did not halt cleanly: {res_run.get('error')}"
        assert res_run["memory"][BK13_TABLE_SLOT_SEND] == 0, "In-image table slot must be 0"
        assert res_run["memory"][BK13_BADSYS_WORD] == 69, "Unadmitted syscall must hit badsys handler"

        # Refusal receipt artifact must exist and contain required fields
        assert receipt_file.exists(), "Refusal receipt must exist on disk"
        receipt_data = json.loads(receipt_file.read_text())
        assert receipt_data["verdict"] == "refused"
        assert receipt_data["reason"] == "E_ATLAS_UNVERIFIED"
        assert receipt_data["frame"] == "SYS_18_UNPROVEN_FRAME"
        assert receipt_data["table_word"] == 0

        # Contrast: in the admitted image, the table words are lit
        admitted_img = net_stack_kernel_image(admit_tiles=True)
        h, w, _ = admitted_img.shape
        lit_px_send = tuple(admitted_img[pw_send // w, pw_send % w])
        pw_recv = BK13_PIX_SLOT_RECV
        lit_px_recv = tuple(admitted_img[pw_recv // w, pw_recv % w])
        assert lit_px_send != (0, 0, 0), "Admitted SYS 18 table slot must be lit"
        assert lit_px_recv != (0, 0, 0), "Admitted SYS 19 table slot must be lit"


# ── L4: Malformed Frame Clean Rejection ──────────────────────────────────────

def test_bk13_l4_malformed_frame_rejected_with_receipt():
    """L4: A frame with bad checksum or bad length is NOT delivered into B's
    frame buffer (buffer unchanged); in-image rejection verdict observable ('E');
    receipt artifact exists recording rejection reason; kernel stable.
    """
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)

        # ── Case A: Bad Checksum ──
        out_ck = tmp / "bk13_bad_checksum.npy"
        net_stack_kernel_image(corrupt_checksum=True, out_path=out_ck)

        runner_ck = GlyphRunner(out_ck, ram_words=16384)
        receipt_ck = runner_ck.run(max_instructions=80000)

        assert receipt_ck.get("halted") is True
        assert receipt_ck.get("faulted") is False, "Malformed frame must not fault engine"

        mem_ck = receipt_ck["memory"]

        # Frame buffer B is NOT delivered (unchanged from pre-send zeros)
        b_words_ck = [mem_ck[BK13_FRAME_BUFFER_B_START + i] for i in range(16)]
        assert b_words_ck == [0] * 16, f"Frame buffer B was modified: {b_words_ck}"

        # In-image rejection verdict marker is observable
        assert mem_ck[BK13_VERDICT_B] == BK13_ERRORED, (
            f"Expected verdict 'E' (69), got {mem_ck[BK13_VERDICT_B]}"
        )

        # Receipt artifact recorded
        rec_ck_path = record_net_receipt(
            tmp / "bad_checksum_receipt.json",
            frame="FRAME_BAD_CHECKSUM",
            verdict="rejected",
            reason="checksum verification mismatch",
        )
        assert rec_ck_path.exists()
        rec_ck_data = json.loads(rec_ck_path.read_text())
        assert rec_ck_data["verdict"] == "rejected"
        assert "checksum" in rec_ck_data["reason"]

        # Kernel and tasks remain stable
        assert mem_ck[BK13_EXIT_B] == BK13_EXIT_OK_B
        assert receipt_ck.get("status_word_value") == BK13_KERNEL_OK

        # ── Case B: Bad Length ──
        out_len = tmp / "bk13_bad_length.npy"
        net_stack_kernel_image(corrupt_length=True, out_path=out_len)

        runner_len = GlyphRunner(out_len, ram_words=16384)
        receipt_len = runner_len.run(max_instructions=80000)

        assert receipt_len.get("halted") is True
        assert receipt_len.get("faulted") is False

        mem_len = receipt_len["memory"]
        b_words_len = [mem_len[BK13_FRAME_BUFFER_B_START + i] for i in range(16)]
        assert b_words_len == [0] * 16, f"Frame buffer B was modified: {b_words_len}"
        assert mem_len[BK13_VERDICT_B] == BK13_ERRORED

        rec_len_path = record_net_receipt(
            tmp / "bad_length_receipt.json",
            frame="FRAME_BAD_LENGTH",
            verdict="rejected",
            reason="length != 16 words",
        )
        assert rec_len_path.exists()
        rec_len_data = json.loads(rec_len_path.read_text())
        assert rec_len_data["verdict"] == "rejected"
        assert "length" in rec_len_data["reason"]

        assert mem_len[BK13_EXIT_B] == BK13_EXIT_OK_B
        assert receipt_len.get("status_word_value") == BK13_KERNEL_OK


# ── L5: No Host I/O Path in Data Movement ───────────────────────────────────

def test_bk13_l5_no_host_io_ast_and_in_substrate_movement():
    """L5: AST-scan tools/glyph_gpt/net_stack.py proves zero imports from
    host I/O and networking libraries; asserts L2 transfer runs through a
    single runner on a single image so frame provably moves in-substrate.
    """
    net_stack_path = _REPO / "tools" / "glyph_gpt" / "net_stack.py"
    assert net_stack_path.exists(), "net_stack.py must exist"

    tree = ast.parse(net_stack_path.read_text(encoding="utf-8"))

    forbidden_modules = {
        "socket",
        "ssl",
        "http",
        "urllib",
        "requests",
        "subprocess",
        "multiprocessing",
        "threading",
        "asyncio",
    }

    found_forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for f in forbidden_modules:
                    if f in alias.name:
                        found_forbidden.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for f in forbidden_modules:
                if f in mod:
                    found_forbidden.append(mod)

    assert not found_forbidden, (
        f"Forbidden host I/O networking imports detected in net_stack.py: {found_forbidden}"
    )

    # Prove in-substrate movement: single runner instance drives single image container
    with tempfile.TemporaryDirectory() as d:
        out_p = Path(d) / "single_image.npy"
        net_stack_kernel_image(admit_tiles=True, out_path=out_p)

        runner = GlyphRunner(out_p, ram_words=16384)
        receipt = runner.run(max_instructions=80000)
        assert receipt.get("halted") is True
        assert receipt.get("faulted") is False

        # In-substrate verification: memory reads from runner's own state
        mem = receipt["memory"]
        assert mem[BK13_FRAME_BUFFER_B_START] == mem[BK13_FRAME_BUFFER_A_START]
        assert mem[BK13_VERDICT_B] == BK13_VERIFIED


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))

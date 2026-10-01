#!/usr/bin/env python3
"""tools/glyph_gpt/net_stack.py — BK-13 Mailbox Network Stack Skeleton.

Roadmap row BK-13:
  "Mailbox net stack skeleton: SYS 18 = net_send / SYS 19 = net_recv frames
   between two Glyph OS instances, BOTH KERNELS INSIDE ONE IMAGE."

RULING (RULING_20260912_defect19_bk13_worktree.md §2):
  - Q1 syscall numbers: SYS 18 = net_send, SYS 19 = net_recv.
  - Q2 instance boundary: TWO KERNELS INSIDE ONE IMAGE exchanging frames
    through the REAL mailbox windows, with every frame crossing the admission
    oracle IN-SUBSTRATE. The host is runner/observer, never the transport.

FRAME FORMAT:
  64 bytes = 16 words (32-bit words).
  - Word 0: Header word
      bits [7:0]   : opcode (e.g. 1 = NET_OP_FRAME)
      bits [15:8]  : length in words (len == 16 for a well-formed frame)
      bits [23:16] : reserved (0)
      bits [31:24] : checksum = (op + len) & 0xFF
  - Words 1..15: Payload (15 32-bit words = 60 bytes)
  Total: 16 words = 64 bytes.

  The frame is copied word-by-word through the kernel-mediated mailbox
  (16 send/recv pairs) into a 16-word frame buffer at the LOW end of the
  receiving box's arena.

EXACT WORD INDICES (both frame buffers and ABI layout):
  - Instance A (BOX0) arena: words [600, 640)
    * Low end frame buffer A: words [600, 616) (indices 600..615)
    * Box 0 ABI words: word 620 (exit word), word 621 (status word)
    * Positive no-overlap: range(600, 616) ∩ {620, 621} == ∅ (DEFECT-19 lesson)

  - Instance B (BOX1) arena: words [700, 740)
    * Low end frame buffer B: words [700, 716) (indices 700..715)
    * Box 1 ABI words: word 720 (exit word), word 721 (verdict marker), word 722 (status)
    * Positive no-overlap: range(700, 716) ∩ {720, 721, 722} == ∅ (DEFECT-19 lesson)

  - Kernel-mediated Mailbox Window: words [754, 770) (indices 754..769)
    * Kernel status word: 950 (CAFE000D on clean completion)
    * Unknown syscall marker: 758 ('E' = 69)
    * Kernel fault marker: 759 (0xFA171)
    * Syscall table window: words [1568, 1584) (GH18_TABLE_WORD = 1568)
      SYS 18 slot: 1568 + (18 - 6) = 1580 (pixel word 1312 + 12 = 1324)
      SYS 19 slot: 1568 + (19 - 6) = 1581 (pixel word 1312 + 13 = 1325)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

# ── Memory Layout & ABI Constants ───────────────────────────────────────────

# Instance A (Box 0)
BK13_BOX0_LO = 600
BK13_BOX0_HI = 640
BK13_BOX0_LO_BYTE = 4 * BK13_BOX0_LO
BK13_BOX0_HI_BYTE = 4 * BK13_BOX0_HI
BK13_BOX0_ARENA = (BK13_BOX0_LO, BK13_BOX0_HI)

BK13_FRAME_BUFFER_A_START = 600
BK13_FRAME_BUFFER_A = range(600, 616)
BK13_EXIT_A = 620
BK13_STATUS_A = 621
BK13_BOX0_ABI_WORDS = {BK13_EXIT_A: "EXIT_A", BK13_STATUS_A: "STATUS_A"}

# Instance B (Box 1)
BK13_BOX1_LO = 700
BK13_BOX1_HI = 740
BK13_BOX1_LO_BYTE = 4 * BK13_BOX1_LO
BK13_BOX1_HI_BYTE = 4 * BK13_BOX1_HI
BK13_BOX1_ARENA = (BK13_BOX1_LO, BK13_BOX1_HI)

BK13_FRAME_BUFFER_B_START = 700
BK13_FRAME_BUFFER_B = range(700, 716)
BK13_EXIT_B = 720
BK13_VERDICT_B = 721
BK13_STATUS_B = 722
BK13_BOX1_ABI_WORDS = {
    BK13_EXIT_B: "EXIT_B",
    BK13_VERDICT_B: "VERDICT_B",
    BK13_STATUS_B: "STATUS_B",
}

# Kernel-mediated Mailbox Window
BK13_MAILBOX_START = 754
BK13_MAILBOX_LEN = 16
BK13_MAILBOX_WINDOW = range(754, 770)
BK13_MAILBOX_WORD = 754

# Kernel Markers
BK13_BADSYS_WORD = 758
BK13_FAULT_WORD = 759
BK13_STATUS_WORD = 950

# Syscall Numbers & Table Slots
BK13_SYS_SEND = 18
BK13_SYS_RECV = 19
GH18_TABLE_BASE = 1568
GH18_PIX_BASE = 1312
BK13_TABLE_SLOT_SEND = GH18_TABLE_BASE + (BK13_SYS_SEND - 6)  # 1580
BK13_TABLE_SLOT_RECV = GH18_TABLE_BASE + (BK13_SYS_RECV - 6)  # 1581
BK13_PIX_SLOT_SEND = GH18_PIX_BASE + (BK13_SYS_SEND - 6)      # 1324
BK13_PIX_SLOT_RECV = GH18_PIX_BASE + (BK13_SYS_RECV - 6)      # 1325

# Exit Status Signatures
BK13_EXIT_OK_A = 0xFEED0000 | 18
BK13_EXIT_OK_B = 0xFEED0000 | 19
BK13_KERNEL_OK = 0xCAFE0000 | 13

# Verdict Markers
BK13_VERIFIED = 86  # 'V'
BK13_ERRORED = 69   # 'E'

# Frame Specs
OP_FRAME = 1
FRAME_LEN_WORDS = 16
FRAME_LEN_BYTES = 64

# Internal packed pixel PC globals (bound during pass 1 of the bake)
_BK13_KSYS_PC = 0
_BK13_FAULT_PC = 0
_BK13_RET_PC = 0
_BK13_DISPATCH_B_PC = 0
_BK13_TASK_A_PC = 0
_BK13_TASK_B_PC = 0
_BK13_TILE_18_PC = 0
_BK13_TILE_19_PC = 0


# ── Frame Construction & Parsing Helpers ─────────────────────────────────────

def make_header(
    op: int = OP_FRAME,
    length: int = FRAME_LEN_WORDS,
    corrupt_checksum: bool = False,
    corrupt_length: bool = False,
) -> int:
    """Construct a 32-bit frame header word."""
    actual_len = 15 if corrupt_length else length
    cksum = (op + actual_len) & 0xFF
    if corrupt_checksum:
        cksum ^= 0xFF
    return ((cksum & 0xFF) << 24) | ((actual_len & 0xFF) << 8) | (op & 0xFF)


def make_frame(
    op: int = OP_FRAME,
    payload: Optional[List[int]] = None,
    corrupt_checksum: bool = False,
    corrupt_length: bool = False,
) -> List[int]:
    """Construct a complete 16-word (64-byte) frame."""
    if payload is None:
        payload = [0xA000 + i for i in range(1, 16)]
    assert len(payload) == 15, f"Payload must contain 15 words, got {len(payload)}"
    hdr = make_header(
        op=op,
        length=FRAME_LEN_WORDS,
        corrupt_checksum=corrupt_checksum,
        corrupt_length=corrupt_length,
    )
    return [hdr] + list(payload)


def parse_header(word: int) -> Dict[str, Union[int, bool]]:
    """Parse a 32-bit header word into component fields and validity."""
    op = word & 0xFF
    length = (word >> 8) & 0xFF
    cksum = (word >> 24) & 0xFF
    expected_cksum = (op + length) & 0xFF
    valid = (length == FRAME_LEN_WORDS) and (cksum == expected_cksum)
    return {
        "op": op,
        "len": length,
        "cksum": cksum,
        "expected_cksum": expected_cksum,
        "valid": valid,
    }


def net_span_conflict(box_id: int, dst_word: int, n_words: int) -> Dict[int, str]:
    """Return box ABI words that the span [dst_word, dst_word + n_words) would overwrite.

    Enforces the DEFECT-19 lesson: RAM spans copied into must be asserted
    not to collide with critical box ABI words.
    """
    abi_map = BK13_BOX0_ABI_WORDS if box_id == 0 else BK13_BOX1_ABI_WORDS
    return {w: name for w, name in abi_map.items() if dst_word <= w < dst_word + n_words}


def record_net_receipt(
    path: Union[str, Path],
    frame: Any,
    verdict: str,
    reason: str,
    table_word: int = 0,
) -> Path:
    """Record an admission/rejection receipt artifact."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "frame": frame,
        "verdict": verdict,
        "reason": reason,
        "table_word": table_word,
    }
    p.write_text(json.dumps(record, indent=2))
    return p


def admit_net_syscall(
    runner: Any,
    sys_n: int,
    contract: str = "",
    argv: Optional[Dict[int, int]] = None,
    expected: int = 0,
    receipt_path: Optional[Union[str, Path]] = None,
    frame: Optional[Any] = None,
    abi: str = "gh18",
) -> Any:
    """Admit a network syscall tile through the autoatlas admission oracle.

    Passes the request to `autoatlas.admit_syscall` and writes a verifiable
    receipt record on refusal or admission.
    """
    from glyph_gpt.autoatlas import admit_syscall
    res = admit_syscall(runner, sys_n, contract=contract, argv=argv, expected=expected, abi=abi)
    if receipt_path is not None:
        verdict = "admitted" if getattr(res, "ok", False) else "refused"
        reason = getattr(res, "code", "OK" if getattr(res, "ok", False) else "E_ATLAS_UNVERIFIED")
        record_net_receipt(
            receipt_path,
            frame=frame or f"SYS_{sys_n}_TILE",
            verdict=verdict,
            reason=reason,
            table_word=getattr(res, "table_word", 0),
        )
    return res


# ── Glyph Assembly Text Builder ─────────────────────────────────────────────

def _pack_const(v: int, reg: str = "r14", scratch: str = "r13") -> List[str]:
    """Generate glyph instructions to assemble a 32-bit immediate into a register."""
    v = v & 0xFFFFFFFF
    hi, lo = (v >> 16) & 0xFFFF, v & 0xFFFF
    lines = [f"LDI {reg} {lo}"]
    if hi:
        lines += [f"LDI {scratch} {hi}", "LDI r4 16", f"SHL {scratch} r4", f"OR {reg} {scratch}"]
    return lines


def _bk13_kernel_program_text(
    status_word: int = BK13_STATUS_WORD,
    corrupt_checksum: bool = False,
    corrupt_length: bool = False,
    custom_payload: Optional[List[int]] = None,
    admit_tiles: bool = True,
) -> str:
    """Generate the complete glyph assembly program for the BK-13 dual-kernel image."""
    from glyph_gpt.baker import (
        BOX0_LO_WORD, BOX1_LO_WORD,
        KFAULT_PC_WORD, KSYS_PC_WORD, MODE_LATCH_WORD,
        GH18_TABLE_WORD,
    )
    from glyph_isa_v2 import SYS_A0_ADDR, SYS_A1_ADDR, SYS_N_ADDR

    a: List[str] = []
    add = a.append

    add(":__entry")
    add("JMP :__kmain")
    add(":__kmain")

    # 1. Zero RAM span [600..770) via compact loop (avoids code bloat)
    add(f"LDI r15 {BK13_FRAME_BUFFER_A_START}")
    add("LDI r14 0")
    add(f"LDI r20 {BK13_MAILBOX_START + BK13_MAILBOX_LEN}")
    add(":__zero_loop")
    add("ST r15 r14")
    add("LDI r4 1")
    add("ADD r15 r4")
    add("CMP r15 r20")
    add("JZ :__zero_done")
    add("JMP :__zero_loop")
    add(":__zero_done")

    # Zero kernel status word
    add(f"LDI r15 {status_word}")
    add("LDI r14 0")
    add("ST r15 r14")

    # 2. Syscall table initialization via compact loop
    add(f"LDI r15 {GH18_TABLE_WORD}")
    add("LDI r14 0")
    add(f"LDI r20 {GH18_TABLE_WORD + 16}")
    add(":__zero_tbl")
    add("ST r15 r14")
    add("LDI r4 1")
    add("ADD r15 r4")
    add("CMP r15 r20")
    add("JZ :__zero_tbldone")
    add("JMP :__zero_tbl")
    add(":__zero_tbldone")

    # Light table slots if admitted
    if admit_tiles:
        add(f"LDI r15 {BK13_TABLE_SLOT_SEND}")
        add(f"LDI r14 {_BK13_TILE_18_PC}")
        add("ST r15 r14")
        add(f"LDI r15 {BK13_TABLE_SLOT_RECV}")
        add(f"LDI r14 {_BK13_TILE_19_PC}")
        add("ST r15 r14")

    # 3. Program BOX0 (Instance A) and BOX1 (Instance B) arenas
    add(f"LDI r15 {BOX0_LO_WORD}")
    add(f"LDI r14 {BK13_BOX0_LO_BYTE}")
    add("ST r15 r14")
    add(f"LDI r15 {BOX0_LO_WORD + 1}")
    add(f"LDI r14 {BK13_BOX0_HI_BYTE}")
    add("ST r15 r14")

    add(f"LDI r15 {BOX1_LO_WORD}")
    add(f"LDI r14 {BK13_BOX1_LO_BYTE}")
    add("ST r15 r14")
    add(f"LDI r15 {BOX1_LO_WORD + 1}")
    add(f"LDI r14 {BK13_BOX1_HI_BYTE}")
    add("ST r15 r14")

    # 4. Arm vectors
    add(f"LDI r15 {KSYS_PC_WORD}")
    add(f"LDI r14 {_BK13_KSYS_PC}")
    add("ST r15 r14")
    add(f"LDI r15 {KFAULT_PC_WORD}")
    add(f"LDI r14 {_BK13_FAULT_PC}")
    add("ST r15 r14")

    # 5. Enter Instance A in USER mode
    add(f"LDI r15 {MODE_LATCH_WORD}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r30 {_BK13_TASK_A_PC}")
    add("KJMP r30")
    add("JMP :__kdone")

    # 6. Syscall dispatcher (SUPER mode)
    add(":__ksys")
    add(f"LDI r15 {SYS_N_ADDR >> 2}")
    add("LD r5 r15")
    # Table lookup & bounds check
    add("LDI r4 6")
    add("SUB r5 r4")
    add("LDI r4 15")
    add("AND r5 r4")
    add(f"LDI r15 {GH18_TABLE_WORD}")
    add("ADD r15 r5")
    add("LD r6 r15")
    add("XOR r4 r4")
    add("CMP r6 r4")
    add("JZ :__ksys_unknown")

    # Dispatched admitted syscalls
    add(f"LDI r15 {SYS_N_ADDR >> 2}")
    add("LD r5 r15")
    add(f"LDI r4 {BK13_SYS_SEND}")
    add("CMP r5 r4")
    add("JZ :__ksys_18")
    add(f"LDI r4 {BK13_SYS_RECV}")
    add("CMP r5 r4")
    add("JZ :__ksys_19")
    add("KJMP r6")

    # SYS 18: net_send (a0 = index, a1 = value)
    add(":__ksys_18")
    add(f"LDI r15 {SYS_A0_ADDR >> 2}")
    add("LD r10 r15")
    add(f"LDI r15 {SYS_A1_ADDR >> 2}")
    add("LD r11 r15")
    add(f"LDI r15 {BK13_MAILBOX_START}")
    add("ADD r15 r10")
    add("ST r15 r11")
    add("SYSRET")

    # SYS 19: net_recv (a0 = index, returns value in a0)
    add(":__ksys_19")
    add(f"LDI r15 {SYS_A0_ADDR >> 2}")
    add("LD r10 r15")
    add(f"LDI r15 {BK13_MAILBOX_START}")
    add("ADD r15 r10")
    add("LD r11 r15")
    add(f"LDI r15 {SYS_A0_ADDR >> 2}")
    add("ST r15 r11")
    add("SYSRET")

    # Unknown / unadmitted syscall handler
    add(":__ksys_unknown")
    add(f"LDI r15 {BK13_BADSYS_WORD}")
    add("LDI r14 69")
    add("ST r15 r14")
    add("SYSRET")

    # Round-robin dispatch to Instance B
    add(":__dispatch_B")
    add(f"LDI r15 {MODE_LATCH_WORD}")
    add("LDI r14 1")
    add("ST r15 r14")
    add(f"LDI r30 {_BK13_TASK_B_PC}")
    add("KJMP r30")
    add("JMP :__kdone")

    # Kernel clean halt
    add(":__kdone")
    add("LDI r9 13")
    add("LDI r3 51966")
    add("LDI r4 16")
    add("SHL r3 r4")
    add("ADD r3 r9")
    add(f"LDI r15 {status_word}")
    add("ST r15 r3")
    add("HALT")

    # Kernel fault handler
    add(":__kfault")
    add(f"LDI r15 {BK13_FAULT_WORD}")
    add("LDI r14 1024369")
    add("ST r15 r14")
    add("JMP :__kdone")

    # Tile anchors
    add(":__tile_18")
    add("SYSRET")
    add(":__tile_19")
    add("SYSRET")

    # ── Task A (Instance A, USER mode, BOX0 [600..640)) ─────────────────────
    hdr = make_header(
        op=OP_FRAME,
        length=FRAME_LEN_WORDS,
        corrupt_checksum=corrupt_checksum,
        corrupt_length=corrupt_length,
    )
    add(":__task_A")
    # Store header at FRAME_BUFFER_A[0]
    for line in _pack_const(hdr, reg="r2", scratch="r3"):
        add(line)
    add(f"LDI r15 {BK13_FRAME_BUFFER_A_START}")
    add("ST r15 r2")

    # Populate words 1..15 in FRAME_BUFFER_A
    if custom_payload is not None:
        for idx, w in enumerate(custom_payload, start=1):
            for line in _pack_const(w, reg="r2", scratch="r3"):
                add(line)
            add(f"LDI r15 {BK13_FRAME_BUFFER_A_START + idx}")
            add("ST r15 r2")
    else:
        add("LDI r9 1")
        add(f"LDI r20 {FRAME_LEN_WORDS}")
        add(":__fill_payload")
        add("LDI r2 40960")  # 0xA000
        add("ADD r2 r9")     # 0xA000 + index
        add(f"LDI r15 {BK13_FRAME_BUFFER_A_START}")
        add("ADD r15 r9")
        add("ST r15 r2")
        add("LDI r4 1")
        add("ADD r9 r4")
        add("CMP r9 r20")
        add("JZ :__fill_done")
        add("JMP :__fill_payload")
        add(":__fill_done")

    # Send 16 words via SYS 18 word-by-word
    add(f"LDI r17 {BK13_SYS_SEND}")
    add("XOR r10 r10")
    add(f"LDI r20 {FRAME_LEN_WORDS}")
    add(":__send_loop")
    add(f"LDI r15 {BK13_FRAME_BUFFER_A_START}")
    add("ADD r15 r10")
    add("LD r11 r15")
    add("SYSCALL r12")
    add("LDI r4 1")
    add("ADD r10 r4")
    add("CMP r10 r20")
    add("JZ :__send_done")
    add("JMP :__send_loop")
    add(":__send_done")

    # Write exit status for Instance A
    for line in _pack_const(BK13_EXIT_OK_A, reg="r14", scratch="r13"):
        add(line)
    add(f"LDI r15 {BK13_EXIT_A}")
    add("ST r15 r14")
    add(f"LDI r30 {_BK13_DISPATCH_B_PC}")
    add("KJMP r30")

    # ── Task B (Instance B, USER mode, BOX1 [700..740)) ─────────────────────
    add(":__task_B")
    # Receive word 0 (header) via SYS 19
    add(f"LDI r17 {BK13_SYS_RECV}")
    add("XOR r10 r10")
    add("SYSCALL r12")
    add("XOR r2 r2")
    add("OR r2 r10")

    # Validate header:
    # Check 1: length == 16
    add("XOR r3 r3")
    add("OR r3 r2")
    add("LDI r4 8")
    add("SHR r3 r4")
    add("LDI r4 255")
    add("AND r3 r4")
    add(f"LDI r4 {FRAME_LEN_WORDS}")
    add("CMP r3 r4")
    add("JZ :__b_len_ok")
    add("JMP :__b_reject")

    add(":__b_len_ok")
    # Check 2: checksum == (op + len) & 0xFF
    add("XOR r5 r5")
    add("OR r5 r2")
    add("LDI r4 255")
    add("AND r5 r4")     # r5 = op

    add("LDI r6 0")
    add("ADD r6 r5")
    add("ADD r6 r3")
    add("LDI r4 255")
    add("AND r6 r4")     # r6 = expected cksum

    add("XOR r7 r7")
    add("OR r7 r2")
    add("LDI r4 24")
    add("SHR r7 r4")
    add("LDI r4 255")
    add("AND r7 r4")     # r7 = actual cksum
    add("CMP r7 r6")
    add("JZ :__b_valid")
    add("JMP :__b_reject")

    add(":__b_valid")
    # Frame valid: store word 0 into FRAME_BUFFER_B[0]
    add(f"LDI r15 {BK13_FRAME_BUFFER_B_START}")
    add("ST r15 r2")

    # Receive words 1..15 via SYS 19 word-by-word
    add("LDI r9 1")
    add(f"LDI r20 {FRAME_LEN_WORDS}")
    add(":__recv_loop")
    add(f"LDI r17 {BK13_SYS_RECV}")
    add("XOR r10 r10")
    add("OR r10 r9")
    add("SYSCALL r12")
    add(f"LDI r15 {BK13_FRAME_BUFFER_B_START}")
    add("ADD r15 r9")
    add("ST r15 r10")
    add("LDI r4 1")
    add("ADD r9 r4")
    add("CMP r9 r20")
    add("JZ :__recv_done")
    add("JMP :__recv_loop")
    add(":__recv_done")

    # Record verified verdict 'V' (86)
    add(f"LDI r15 {BK13_VERDICT_B}")
    add(f"LDI r14 {BK13_VERIFIED}")
    add("ST r15 r14")
    add("JMP :__b_exit")

    add(":__b_reject")
    # Frame rejected: FRAME_BUFFER_B is UNTOUCHED
    # Record rejection verdict 'E' (69)
    add(f"LDI r15 {BK13_VERDICT_B}")
    add(f"LDI r14 {BK13_ERRORED}")
    add("ST r15 r14")
    add("JMP :__b_exit")

    add(":__b_exit")
    # Write exit status for Instance B
    for line in _pack_const(BK13_EXIT_OK_B, reg="r14", scratch="r13"):
        add(line)
    add(f"LDI r15 {BK13_EXIT_B}")
    add("ST r15 r14")
    add(f"LDI r30 {_BK13_RET_PC}")
    add("KJMP r30")

    return "\n".join(a) + "\n"


# ── Public Entry Point: net_stack_kernel_image ──────────────────────────────

def net_stack_kernel_image(
    atlas: Any = None,
    status_word: int = BK13_STATUS_WORD,
    corrupt_checksum: bool = False,
    corrupt_length: bool = False,
    custom_payload: Optional[List[int]] = None,
    admit_tiles: bool = True,
    cols_instrs: int = 8,
    min_rows: int = 64,
    out_path: Optional[Union[str, Path]] = None,
) -> np.ndarray:
    """Bake ONE image containing two Glyph OS instances with mailbox net stack.

    Two-pass assembly fixes packed pixel PCs (:__ksys, :__kfault, :__kdone,
    :__dispatch_B, :__task_A, :__task_B, :__tile_18, :__tile_19).
    """
    from glyph_gpt.baker import bake_image
    from rv64i_to_glyph import assemble_glyph_to_pixels

    global _BK13_KSYS_PC, _BK13_FAULT_PC, _BK13_RET_PC, _BK13_DISPATCH_B_PC
    global _BK13_TASK_A_PC, _BK13_TASK_B_PC, _BK13_TILE_18_PC, _BK13_TILE_19_PC

    # Pass 1: measure coordinates
    txt1 = _bk13_kernel_program_text(
        status_word=status_word,
        corrupt_checksum=corrupt_checksum,
        corrupt_length=corrupt_length,
        custom_payload=custom_payload,
        admit_tiles=admit_tiles,
    )
    _, coords1 = assemble_glyph_to_pixels(txt1, cols_instrs=cols_instrs, min_rows=min_rows)

    def packed(lbl: str) -> int:
        col, row = coords1[lbl]
        return (col & 0xFFFF) | ((row & 0xFFFF) << 16)

    _BK13_KSYS_PC = packed(":__ksys")
    _BK13_FAULT_PC = packed(":__kfault")
    _BK13_RET_PC = packed(":__kdone")
    _BK13_DISPATCH_B_PC = packed(":__dispatch_B")
    _BK13_TASK_A_PC = packed(":__task_A")
    _BK13_TASK_B_PC = packed(":__task_B")
    _BK13_TILE_18_PC = packed(":__tile_18")
    _BK13_TILE_19_PC = packed(":__tile_19")

    try:
        # Pass 2: assemble with real packed PCs
        txt2 = _bk13_kernel_program_text(
            status_word=status_word,
            corrupt_checksum=corrupt_checksum,
            corrupt_length=corrupt_length,
            custom_payload=custom_payload,
            admit_tiles=admit_tiles,
        )
        img = bake_image(
            txt2,
            atlas=None,
            cols_instrs=cols_instrs,
            min_rows=min_rows,
            out_path=out_path,
        )
        # Stamp pixel-surface table entries if admitted
        h, w, _ = img.shape
        if admit_tiles:
            for sys_n, pc in [(BK13_SYS_SEND, _BK13_TILE_18_PC), (BK13_SYS_RECV, _BK13_TILE_19_PC)]:
                pw = GH18_PIX_BASE + (sys_n - 6)
                img[pw // w, pw % w] = ((pc >> 16) & 0xFF, (pc >> 8) & 0xFF, pc & 0xFF)
            # Re-save if out_path was specified
            if out_path is not None:
                p = Path(out_path)
                if p.suffix == ".npy":
                    np.save(p, img)
                elif p.suffix == ".npz":
                    np.savez(p, image=img)
                else:
                    from PIL import Image
                    Image.fromarray(img, "RGB").save(p, format="PNG")
        return img
    finally:
        _BK13_KSYS_PC = _BK13_FAULT_PC = _BK13_RET_PC = _BK13_DISPATCH_B_PC = 0
        _BK13_TASK_A_PC = _BK13_TASK_B_PC = _BK13_TILE_18_PC = _BK13_TILE_19_PC = 0

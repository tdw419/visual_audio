#!/usr/bin/env python3
"""Interactive terminal for Glyph apps: stdin-refill harness + a minimal echo shell.

The Glyph CPU has no native blocking I/O - SYSCALL_READ (0x02) just drains
whatever the harness has already seeded into the input ring (INPUT_LEN/CURSOR/
DATA), returning 0 immediately once it's exhausted. This harness supplies the
"blocking" behaviour at the HOST level: it's a turn-based loop, not low-level
interrupt-driven I/O -

  1. get one line of text (from a real human via input(), or from a
     pre-supplied list for batch/test mode - never both in the same run)
  2. seed the ring with that line's bytes
  3. run the CPU until it HALTs (the shell app reads-and-echoes the whole
     line, then hits :done and HALTs on ring exhaustion)
  4. print whatever the app printed this turn, go back to step 1

Non-negotiable test invariant: batch mode (lines=[...]) never calls input(),
so pytest/suite_iso_harness sweeps can never hang on a real tty.

The shell app itself: read one byte at a time via SYSCALL 0x02, PRT each byte
back, loop until the ring is exhausted (return value 0) this turn, HALT. Real
:label jumps (SE019), no hand-computed coordinates.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2,
    INPUT_LEN_ADDR, INPUT_CURSOR_ADDR, INPUT_DATA_ADDR, INPUT_DATA_CAP,
)
from tools.glyph_text_console import TextConsole  # noqa: E402  (DTF-2, item 10)

ECHO_SHELL = [
    "LDI r4 0",         # r4 stays 0: the "ring exhausted" sentinel to compare against
    ":read_loop",
    "LDI r1 700",       # buffer addr (RAM word, reused each byte)
    "LDI r2 1",         # want 1 byte
    "SYSCALL r3 0x02",  # r3 = bytes actually read (0 or 1)
    "CMP r3 r4",
    "JZ :done",         # r3==0 -> ring exhausted this turn
    "LD r5 r1",
    "PRT r5",
    "JMP :read_loop",
    ":done",
    "HALT",
]
W = 8


def build_shell():
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(ECHO_SHELL, width_instrs=W)
    om.close()
    return img


# --- TASK_SE020: dispatch-on-first-byte shell --------------------------------
# Promotes the shell from pure echo to branching on the first byte of each
# turn's line: 'e' echoes the rest, 's' speaks it (AUDIO_OUT), 'w' writes it
# to a fixed path (FILE_WRITE), 'r' reads that path back (FILE_READ + PRT),
# anything else fails loudly with DISPATCH_ERROR_MARKER instead of silently
# echoing. Uses the GH-8b pixel-resident FS window [1024, 1280) for the fixed
# paths and scratch buffers (same idiom as tests/test_glyph_app_echo.py /
# test_glyph_app_voice.py) - requires GlyphCPUv2(..., fs_pix_enabled=True).
DISPATCH_ERROR_MARKER = b"ERR:UNKNOWN_CMD"
DISPATCH_BUF_CAP = INPUT_DATA_CAP


def build_exec_shell(
    write_path: str,
    audio_path: str,
    runner_path: str,
    child_path: str,
    child_out_path: str,
    width_instrs: int = W,
):
    """TASK_SE021: the dispatch shell plus a glyph-on-glyph 'x' command.

    'x' = SYSCALL 0x07 RUN on the child-runner host script (baked path),
    which executes the child .glyph image and writes its PRT output to a
    fixed file; rc==0 → FILE_READ that file and PRT it (the child's
    observable output lands in the shell transcript); rc!=0 → PRT
    RUN_DENIED_MARKER (loud refusal — deny is a named outcome, not silence).
    Containment is the engine's GLYPH_RUN_ALLOW allowlist, unchanged.

    LAYOUT CONSTRAINT (measured, dbg19/dbg20): word w lives at linear pixel
    2w, i.e. image row w // (width_instrs*4//2... 32//2=16). FS word 1024
    lands at pixel row 64 — a program longer than 64 instruction rows would
    be CLOBBERED by the constant-stamp loops (SE020's ~250 instrs fit under
    row 64 by luck). This build's program is ~652 instrs (82 rows), so the
    constants base must sit BELOW the program: base = max(1024, prog_rows*16).
    Two-pass assemble: first with a placeholder to measure the instruction
    count, then with the real layout.
    """
    for _pass in (0, 1):
        try:
            return _build_exec_shell_pass(
                write_path, audio_path, runner_path, child_path,
                child_out_path, width_instrs, fs_base_word=None if _pass == 0 else _pass2_base[0],
            )
        except _ProgRowsMeasured as m:
            # LAYOUT v5.1 (2026-09-16, dbg-se021 leg-2 RCA): v5's
            # max(1024, ...) base default put Region B INSIDE the FS window
            # whenever the program was short enough (base stayed 1024) —
            # stamped paths, RUN2 args and the FILE_READ dests all shared
            # [1024,1280), so turn 1's FILE_READ overwrote the stamped paths
            # and turn 2's dispatch jumped into data (measured: HALT at
            # pc=(4,68), inside the window's own FILE_READ bytes). The
            # constants base must sit strictly ABOVE the window's top: the
            # window is for syscall dest buffers ONLY, exactly as the v5
            # comment intended.
            _pass2_base[0] = max(1280, 1024 + (m.rows + 2) * 16)
    raise AssertionError("unreachable")


RUN_DENIED_MARKER = b"ERR:RUN_DENIED"


class _ProgRowsMeasured(Exception):
    """Two-pass signal: pass 0 measured the program height in image rows."""

    def __init__(self, rows: int):
        super().__init__(str(rows))
        self.rows = rows


_pass2_base = [1024]


def _build_exec_shell_pass(
    write_path: str,
    audio_path: str,
    runner_path: str,
    child_path: str,
    child_out_path: str,
    width_instrs: int,
    fs_base_word: int | None,
):
    """Assemble the whole program (dispatch shell + x) as one image.

    fs_base_word=None is the measuring pass: constants go at a placeholder
    base and the function raises _ProgRowsMeasured with the program's image
    height instead of assembling. The real pass uses the measured height to
    place the constants base strictly BELOW the program rows (see the
    LAYOUT CONSTRAINT note on build_exec_shell).
    """
    # Program size depends on path LENGTHS (stamp loops), which are known
    # before assembly - but exactness matters (JMP :done targets), so the
    # measuring pass builds the same prog list with placeholder addresses.
    if fs_base_word is None:
        base = 1024
    else:
        base = fs_base_word

    runner_bytes = runner_path.encode("utf-8") + b"\0"
    child_bytes = child_path.encode("utf-8") + b"\0"
    cout_bytes = child_out_path.encode("utf-8") + b"\0"

    # LAYOUT v5 (2026-09-15, replaced v3/v4) / v6 (2026-09-16, backlog (d)
    # handler 2/5): the v3/v4 programs were ~82 instruction rows tall, but
    # FS-window words [1024, 1280) alias to pixel rows 64..80 - the v3/v4
    # path-stamp loops wrote path bytes OVER the program's own instruction
    # rows (SE020's ~250-instr shell fit under row 64 by luck; the exec
    # build never could). v5 rules, v6 correction to the read_addr rule:
    #   - NOTHING is stamped into the FS window. Paths live in Region B
    #     (>= base, above the program) - ST writes RAM, and _read_path
    #     reads the same RAM view (single-view since the 2026-09-22
    #     view-merge retirement; no image fallback).
    #   - v5 said the two FILE_READ dest buffers (read_addr, xread_addr)
    #     MUST sit in the window, because FILE_READ wrote via _mem_write
    #     (image pixels outside the window are invisible to LD). v6: this
    #     is now BACKWARDS. FILE_READ's dest migrated to RAM (self.memory)
    #     2026-09-16 - it no longer touches image pixels at all, and an
    #     in-window LD still reads via _fs_pix_read (image pixels,
    #     unconditionally) regardless of what FILE_READ wrote to RAM. The
    #     dest buffers now MUST be OUTSIDE the window, in Region B with
    #     everything else, so LD takes the plain self.memory[addr] path.
    #   - The window stays zero-filled in the image for path/data
    #     staging (min_pixels backs 2*1280 linear pixels, see padding
    #     below); it plays no role in the read-back path any more.
    write_bytes = write_path.encode("utf-8") + b"\0"
    audio_bytes = audio_path.encode("utf-8") + b"\0"
    path_addr = base
    audio_path_addr = path_addr + len(write_bytes) + 2
    data_addr = audio_path_addr + len(audio_bytes) + 2
    runner_addr = data_addr + DISPATCH_BUF_CAP + 2
    child_addr = runner_addr + len(runner_bytes) + 2
    cout_addr = child_addr + len(child_bytes) + 2
    rc_addr = cout_addr + len(cout_bytes) + 2
    read_addr = rc_addr + 2                              # RAM, outside the FS window (v6)
    xread_addr = read_addr + DISPATCH_BUF_CAP + 2         # RAM, outside the FS window (v6)
    max_word = xread_addr + DISPATCH_BUF_CAP
    assert max_word < 16384, f"Memory overflow: {max_word} >= 16384"

    # The dispatch shell program, minus its trailing :done/HALT, with the
    # 'x' comparison inserted into the dispatch chain, and the exec branch
    # inserted before :done.
    prog: list[str] = []

    for i, b in enumerate(write_bytes):
        prog += [f"LDI r10 {path_addr + i}", f"LDI r11 {b}", "ST r10 r11"]
    for i, b in enumerate(audio_bytes):
        prog += [f"LDI r10 {audio_path_addr + i}", f"LDI r11 {b}", "ST r10 r11"]
    for i, b in enumerate(runner_bytes):
        prog += [f"LDI r10 {runner_addr + i}", f"LDI r11 {b}", "ST r10 r11"]
    for i, b in enumerate(child_bytes):
        prog += [f"LDI r10 {child_addr + i}", f"LDI r11 {b}", "ST r10 r11"]
    for i, b in enumerate(cout_bytes):
        prog += [f"LDI r10 {cout_addr + i}", f"LDI r11 {b}", "ST r10 r11"]

    prog += [
        "LDI r4 0",
        "LDI r12 1",
        "LDI r1 700",
        "LDI r2 1",
        "SYSCALL r3 0x02",
        "CMP r3 r4",
        "JZ :done",
        "LD r6 r1",
        "LDI r7 101",   # 'e'
        "CMP r6 r7",
        "JZ :echo_branch",
        "LDI r7 115",   # 's'
        "CMP r6 r7",
        "JZ :speak_branch",
        "LDI r7 119",   # 'w'
        "CMP r6 r7",
        "JZ :write_branch",
        "LDI r7 114",   # 'r'
        "CMP r6 r7",
        "JZ :read_branch",
        "LDI r7 120",   # 'x' — TASK_SE021
        "CMP r6 r7",
        "JZ :exec_branch",
    ]

    for ch in DISPATCH_ERROR_MARKER:
        prog += [f"LDI r5 {ch}", "PRT r5"]
    # L3 sub-step 4: the error paths exit with status 1 through 0x05
    # (SYSCALL_EXIT) instead of falling into :done's status-0 arm -- the
    # engine-side exit status the L1 shell's `&&` short-circuit and `$?`
    # surface. Contract: 0x05 returns r1 into rd and stops the engine
    # (SYSCALL_ABI_SPEC 0x05; twin IMPLEMENTED, wgsl_glyph_isa_v2
    # syscall_num == 5u arm), so status travels in r9 (SYSCALL r9 0x05)
    # where run_turn's per-turn register reset leaves it readable.
    prog.append("JMP :exit_err")

    prog += [
        ":echo_branch",
        ":echo_loop",
        "LDI r1 700",
        "LDI r2 1",
        "SYSCALL r3 0x02",
        "CMP r3 r4",
        "JZ :done",
        "LD r5 r1",
        "PRT r5",
        "JMP :echo_loop",
    ]

    prog += [
        ":speak_branch",
        f"LDI r8 {data_addr}",
        "LDI r9 0",
        ":speak_collect",
        "LDI r1 700",
        "LDI r2 1",
        "SYSCALL r3 0x02",
        "CMP r3 r4",
        "JZ :speak_emit",
        "LD r5 r1",
        "ST r8 r5",
        "ADD r8 r12",
        "ADD r9 r12",
        "JMP :speak_collect",
        ":speak_emit",
        f"LDI r1 {audio_path_addr}",
        f"LDI r2 {data_addr}",
        "LDI r3 0",
        "ADD r3 r9",
        "SYSCALL r0 0x08",
        "JMP :done",
    ]

    prog += [
        ":write_branch",
        f"LDI r8 {data_addr}",
        "LDI r9 0",
        ":write_collect",
        "LDI r1 700",
        "LDI r2 1",
        "SYSCALL r3 0x02",
        "CMP r3 r4",
        "JZ :write_emit",
        "LD r5 r1",
        "ST r8 r5",
        "ADD r8 r12",
        "ADD r9 r12",
        "JMP :write_collect",
        ":write_emit",
        f"LDI r1 {path_addr}",
        f"LDI r2 {data_addr}",
        "LDI r3 0",
        "ADD r3 r9",
        "SYSCALL r0 0x03",
        "JMP :done",
    ]

    prog += [
        ":read_branch",
        f"LDI r1 {path_addr}",
        f"LDI r2 {read_addr}",
        f"LDI r3 {DISPATCH_BUF_CAP}",
        "SYSCALL r9 0x04",
        f"LDI r8 {read_addr}",
        ":read_print_loop",
        "CMP r9 r4",
        "JZ :done",
        "LD r5 r8",
        "PRT r5",
        "ADD r8 r12",
        "SUB r9 r12",
        "JMP :read_print_loop",
    ]

    # --- TASK_SE021 exec branch -------------------------------------------
    # SYSCALL 0x12 RUN2 on the runner (rc -> r9, also ST'd to rc_addr):
    # argv = [runner, child image, child out path] — 0x07 spawns [path] with
    # no argv, which made the runner exit rc=2 (usage) on every build (v3/v4
    # never got past this; measured 2026-09-15). rc != 0 ->
    # RUN_DENIED_MARKER; rc == 0 -> FILE_READ child_out and PRT it.
    # r8 (the LD pointer) is LDI'd DIRECTLY to xread_addr rather than after
    # the syscall: the assembler's image-space-write tracker keys FILE_READ's
    # dest off r2's known-constant value, and r2 here holds child_addr (an
    # arg address, not the dest) — a distinct constant keeps the tracker from
    # flagging the LD from the in-window dest as RAM-vs-pixel-space.
    prog += [
        ":exec_branch",
        f"LDI r1 {runner_addr}",
        f"LDI r2 {child_addr}",
        f"LDI r3 {cout_addr}",
        "SYSCALL r9 0x12",
        f"LDI r10 {rc_addr}",
        "ST r10 r9",
        "CMP r9 r4",
        "JZ :exec_read",
        ":exec_denied",
    ]
    for ch in RUN_DENIED_MARKER:
        prog += [f"LDI r5 {ch}", "PRT r5"]
    prog += [
        "JMP :done",
        ":exec_read",
        f"LDI r1 {cout_addr}",
        f"LDI r2 {xread_addr}",
        f"LDI r3 {DISPATCH_BUF_CAP}",
        "SYSCALL r9 0x04",
        f"LDI r8 {xread_addr}",
        ":exec_print_loop",
        "CMP r9 r4",
        "JZ :done",
        "LD r5 r8",
        "PRT r5",
        "ADD r8 r12",
        "SUB r9 r12",
        "JMP :exec_print_loop",
    ]

    prog += [
        ":done",
        # L3 sub-step 4: status-0 exit arm. Every SUCCESS path ends here;
        # 0x05 (SYSCALL_EXIT) copies r1 into rd (r9) and stops the engine
        # -- the same contract the :exit_err arm below uses with status 1.
        "LDI r1 0",
        "SYSCALL r9 0x05",
        ":exit_err",
        # status-1 exit arm: the grammar-gate/dispatch-failure paths land
        # here. 0x05 stops the engine with rd=r1=1.
        "LDI r1 1",
        "SYSCALL r9 0x05",
        # Defensive tail: 0x05 sets running=False, so these are unreachable
        # unless an engine change breaks the EXIT contract -- a HALT keeps
        # a degraded run from walking off the program into data pixels.
        "HALT",
    ]

    # Instruction count AFTER label-def filtering (labels consume no slot) -
    # replicate the assembler's pass-1 filter exactly.
    raw_instrs = 0
    for line in prog:
        code = line.split("#")[0].strip()
        toks = code.split()
        if len(toks) == 1 and toks[0].startswith(":") and len(toks[0]) > 1:
            continue
        raw_instrs += 1
    prog_rows = (raw_instrs + width_instrs - 1) // width_instrs

    if fs_base_word is None:
        # Measuring pass: report the program height so the caller can place
        # the constants base below the program pixels.
        raise _ProgRowsMeasured(prog_rows)

    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(prog, width_instrs=width_instrs)
    om.close()

    # Disjointness proof (the layout constraint this padding enforces):
    # program occupies pixel rows [0, prog_rows); Region B constants occupy
    # words [base, max_word] = linear pixels [2*base, 2*max_word+1]. With
    # base >= (prog_rows + 2) * 16 the Region B stamps start at pixel row
    # prog_rows + 2, so they can never overwrite an instruction. Region A is
    # the fixed FS window [1024,1280): SE020's stamp pixels land at rows
    # 64..80, disjoint from the program because this builder only accepts
    # programs up to 62 rows (assert below) — beyond that, Region B itself
    # would collide with the window, which the base assert catches first.
    assert base >= (prog_rows + 2) * 16, (
        f"constants base {base} overlaps program rows ({prog_rows})"
    )
    import numpy as np
    min_pixels = max((max_word + 1) * 2, 2 * 1280)  # always back the whole window
    rows_needed = max(prog_rows, (min_pixels + (width_instrs * 4) - 1) // (width_instrs * 4), 42)
    if img.shape[0] < rows_needed:
        pad = np.zeros((rows_needed - img.shape[0], width_instrs * 4, 3), dtype=np.uint8)
        img = np.vstack([img, pad])

    return img


def build_dispatch_shell(write_path: str, audio_path: str, width_instrs: int = W,
                         stamp_paths: bool = True, return_layout: bool = False,
                         runner_path: str | None = None,
                         child_path: str | None = None,
                         child_out_path: str | None = None):
    """Assemble the dispatch shell with write_path/audio_path baked in as the
    fixed paths for 'w'/'r' (FILE_WRITE/FILE_READ) and 's' (AUDIO_OUT).

    The path-building instructions run at the top of every turn (run_turn
    resets pc to (0, 0) each call) - harmless, they just rewrite the same
    constant bytes into memory each time.

    L1 shell personality (claim round 8, item 14):
      stamp_paths=False -> emit NO in-image path stamps; the CALLER owns
        the FS-window path region (per-turn argv-path routing). The layout
        arithmetic is identical either way, so the overflow asserts still
        guard long paths.
      return_layout=True -> return (image, layout_dict) exposing the
        FS-window word addresses, so a caller can stamp/inspect the path
        region without re-deriving the layout. Default False keeps the
        landed signature and every existing gate leg byte-identical.

    BK-21 (2026-09-24): runner_path+child_path+child_out_path (ALL three,
    or NONE -- a partial set is a loud ValueError, never a half-wired
    verb) promote the TASK_SE021 exec branch into the HUMAN dispatch
    shell:
      'x <child.glyph.npy>' -> SYSCALL 0x12 RUN2 on the runner with
      argv=[runner, child, child_out]; rc==0 -> FILE_READ child_out and
      PRT it; rc!=0 -> RUN_DENIED_MARKER. Containment is the engine's
      GLYPH_RUN_ALLOW allowlist, unchanged. The child path comes from the
      LINE PAYLOAD; runner/child/out paths are stamped as Region-B
      constants (words strictly ABOVE everything the plain shell uses --
      the window [1024,1280) plus the RAM read buffers up to max_word --
      so no existing address changes meaning; overflow-asserted below).
    The item-11 grammar carries over unchanged: bare 'x' and 'xf oo' stay
    ERR:UNKNOWN_CMD (only 'x<space><child>' dispatches). Default (no
    kwargs) builds byte-identically to the pre-promotion image.
    """
    _exec_args = (runner_path, child_path, child_out_path)
    if any(_exec_args) and not all(_exec_args):
        raise ValueError(
            "build_dispatch_shell: exec promotion needs ALL of "
            "runner_path, child_path, child_out_path (got a partial set)"
        )
    exec_enabled = all(_exec_args)
    write_bytes = write_path.encode("utf-8") + b"\0"
    audio_bytes = audio_path.encode("utf-8") + b"\0"

    # v6 (2026-09-16, backlog (d) handler 2/5): read_addr (FILE_READ's
    # dest) moved OUT of the FS window - same fix, same reason, as
    # build_exec_shell above. path/audio_path/data stay in-window (still
    # image-space: FILE_WRITE/AUDIO_OUT haven't migrated).
    path_addr = 1024
    audio_path_addr = path_addr + len(write_bytes) + 2
    data_addr = audio_path_addr + len(audio_bytes) + 2
    assert data_addr + DISPATCH_BUF_CAP < 1280, (
        f"Memory overflow in FS window: {data_addr + DISPATCH_BUF_CAP} >= 1280 (paths too long)"
    )
    read_addr = 1280
    max_word = read_addr + DISPATCH_BUF_CAP
    assert max_word < 16384, f"Memory overflow: {max_word} >= 16384"

    if exec_enabled:
        # BK-21 Region B: exec constants live strictly ABOVE everything the
        # plain shell uses (window [1024,1280) + RAM read buffers up to
        # max_word), so no existing address changes meaning. The CHILD path
        # is NOT a constant: it is the line payload, collected by the exec
        # branch into child_arg_addr (the payload buffer, DISPATCH_BUF_CAP
        # words — a long child path overflows nothing; RUN2's own
        # not-a-regular-file / not-in-allowlist checks refuse it loudly).
        runner_bytes = runner_path.encode("utf-8") + b"\0"
        cout_bytes = child_out_path.encode("utf-8") + b"\0"
        runner_addr = max_word + 2
        cout_addr = runner_addr + len(runner_bytes) + 2
        child_arg_addr = cout_addr + len(cout_bytes) + 2
        rc_addr = child_arg_addr + DISPATCH_BUF_CAP + 2
        xread_addr = rc_addr + 2  # RAM FILE_READ dest, outside the window
        exec_max_word = xread_addr + DISPATCH_BUF_CAP
        assert exec_max_word < 16384, (
            f"Memory overflow: {exec_max_word} >= 16384"
        )

    prog: list[str] = []

    if exec_enabled:
        for blob, blob_addr in (
            (runner_bytes, runner_addr),
            (cout_bytes, cout_addr),
        ):
            for i, b in enumerate(blob):
                prog += [f"LDI r10 {blob_addr + i}", f"LDI r11 {b}", "ST r10 r11"]

    if stamp_paths:
        for i, b in enumerate(write_bytes):
            prog += [f"LDI r10 {path_addr + i}", f"LDI r11 {b}", "ST r10 r11"]
        for i, b in enumerate(audio_bytes):
            prog += [f"LDI r10 {audio_path_addr + i}", f"LDI r11 {b}", "ST r10 r11"]

    # ITEM 11 (2026-09-23, dispatch grammar collision): the FIRST-BYTE-ONLY
    # dispatch silently misexecuted natural English -- 'what time is it'
    # parsed as 'w' + 'hat time is it' (SILENT FILE WRITE), 'seems fine to
    # me' parsed as 's' (SILENT SPEECH), 'read me the news' echoed a tail.
    # Grammar now enforced IN the glyph program:
    #   - byte 2 of a multi-char line must be ' ' (0x20), else the named
    #     ERR:UNKNOWN_CMD marker; the payload is ALL bytes after byte 0
    #     (delimiter space included), so 'w  x' writes '  x'.
    #   - only bare 'r' is legitimate (the one zero-payload command); bare
    #     'w'/'s'/'e' and any other single byte go to the error marker.
    #   - the length gate reads INPUT_LEN_ADDR (per-turn authoritative --
    #     run_turn resets it every turn), never the stale data ring.
    prog += [
        "LDI r4 0",     # ring-exhausted sentinel; never overwritten
        "LDI r12 1",    # increment/decrement constant
        "LDI r1 700",
        "LDI r2 1",
        "SYSCALL r3 0x02",
        "CMP r3 r4",
        "JZ :done",     # empty line this turn -> nothing to dispatch
        "LD r6 r1",     # r6 = first byte

        # --- ITEM 11 grammar gate: len(line) > 1 REQUIRES byte 2 == ' ' ---
        # Peek byte 2 DIRECTLY from the harness input ring (word
        # INPUT_DATA_ADDR+1), not from the 0x02 scratch buffer: the syscall
        # copy consumes ring bytes, and re-reading it would shift the
        # payload. The ring is not consumed by a peek, and INPUT_LEN (word
        # INPUT_LEN_ADDR>>2) is per-turn authoritative -- run_turn rewrites
        # both every turn, so no stale-line contamination.
        f"LDI r7 {INPUT_LEN_ADDR >> 2}",
        "LD r9 r7",     # r9 = this turn's line length (host-written)
        "CMP r9 r12",   # r0 = 1 iff len == 1
        "JZ :bare_cmd", # single-char line -> only bare 'r' is legal
        f"LDI r7 {(INPUT_DATA_ADDR >> 2) + 1}",
        "LD r8 r7",     # r8 = ring byte 1 (the would-be delimiter)
        "LDI r7 32",    # ' '
        "CMP r8 r7",
        "JNZ :err_cmd", # <cmd><non-space> -> loud error, never silent
        "JMP :dispatch",
        ":bare_cmd",
        "LDI r7 114",   # 'r'
        "CMP r6 r7",
        "JZ :read_branch",
        # bare e/s/w/x... -> fall through to the error marker
        ":err_cmd",
    ]
    for ch in DISPATCH_ERROR_MARKER:
        prog += [f"LDI r5 {ch}", "PRT r5"]
    prog.append("JMP :exit_err")

    prog += [
        ":dispatch",
        "LDI r7 101",   # 'e'
        "CMP r6 r7",
        "JZ :echo_branch",
        "LDI r7 115",   # 's'
        "CMP r6 r7",
        "JZ :speak_branch",
        "LDI r7 119",   # 'w'
        "CMP r6 r7",
        "JZ :write_branch",
        "LDI r7 114",   # 'r'
        "CMP r6 r7",
        "JZ :read_branch",
    ]

    if exec_enabled:
        # BK-21: 'x' joins the dispatch chain. The item-11 grammar gate has
        # already guaranteed len>1 AND byte-1==' ' for anything reaching
        # here, so the payload is the child path (ring bytes 2..len).
        # SYSCALL 0x12 RUN2 (SE021): r1=runner, r2=child, r3=child_out;
        # rc!=0 -> RUN_DENIED_MARKER; rc==0 -> FILE_READ child_out, PRT it.
        # r8 is LDI'd DIRECTLY to xread_addr (not derived from r2): the
        # assembler's image-space-write tracker keys FILE_READ's dest off
        # r2's known-constant value (build_exec_shell precedent, SE021).
        prog += [
            "LDI r7 120",   # 'x'
            "CMP r6 r7",
            "JZ :exec_branch",
        ]

    # unrecognized first byte: fail loudly, never fall through to echo.
    # (ITEM 11: the :err_cmd grammar-gate marker block above shares this
    # emit loop; this second block remains the fallthrough target for the
    # dispatch chain's own unknown first byte.)
    for ch in DISPATCH_ERROR_MARKER:
        prog += [f"LDI r5 {ch}", "PRT r5"]
    prog.append("JMP :exit_err")

    if exec_enabled:
        prog += [
            ":exec_branch",
            # Collect the child path payload (every byte after "x ") into
            # the exec data buffer, NUL-terminated. The 0x02 ring read
            # consumes bytes VERBATIM (the item-11 payload convention
            # includes the delimiter space), so strip it: the first byte
            # this loop would store is the delimiter itself -- skip it by
            # storing byte 2 onward via the first-iteration flag in r11.
            f"LDI r8 {child_arg_addr}",
            "LDI r9 0",
            "LDI r11 1",
            ":exec_collect",
            "LDI r1 700",
            "LDI r2 1",
            "SYSCALL r3 0x02",
            "CMP r3 r4",
            "JZ :exec_emit",
            "LD r5 r1",
            "CMP r11 r4",
            "JZ :exec_store",
            "LDI r11 0",            # delimiter consumed, drop it
            "JMP :exec_collect",
            ":exec_store",
            "ST r8 r5",
            "ADD r8 r12",
            "ADD r9 r12",
            "JMP :exec_collect",
            ":exec_emit",
            "LDI r11 0",            # NUL terminator
            "ST r8 r11",
            # RUN2 argv = [runner, child, child_out]
            f"LDI r1 {runner_addr}",
            f"LDI r2 {child_arg_addr}",
            f"LDI r3 {cout_addr}",
            "SYSCALL r9 0x12",
            f"LDI r10 {rc_addr}",
            "ST r10 r9",
            "CMP r9 r4",
            "JZ :exec_read",
            ":exec_denied",
        ]
        for ch in RUN_DENIED_MARKER:
            prog += [f"LDI r5 {ch}", "PRT r5"]
        prog += [
            "JMP :done",
            ":exec_read",
            f"LDI r1 {cout_addr}",
            f"LDI r2 {xread_addr}",
            f"LDI r3 {DISPATCH_BUF_CAP}",
            "SYSCALL r9 0x04",
            f"LDI r8 {xread_addr}",
            ":exec_print_loop",
            "CMP r9 r4",
            "JZ :done",
            "LD r5 r8",
            "PRT r5",
            "ADD r8 r12",
            "SUB r9 r12",
            "JMP :exec_print_loop",
        ]

    prog += [
        ":echo_branch",
        ":echo_loop",
        "LDI r1 700",
        "LDI r2 1",
        "SYSCALL r3 0x02",
        "CMP r3 r4",
        "JZ :done",
        "LD r5 r1",
        "PRT r5",
        "JMP :echo_loop",
    ]

    prog += [
        ":speak_branch",
        f"LDI r8 {data_addr}",
        "LDI r9 0",
        ":speak_collect",
        "LDI r1 700",
        "LDI r2 1",
        "SYSCALL r3 0x02",
        "CMP r3 r4",
        "JZ :speak_emit",
        "LD r5 r1",
        "ST r8 r5",
        "ADD r8 r12",
        "ADD r9 r12",
        "JMP :speak_collect",
        ":speak_emit",
        f"LDI r1 {audio_path_addr}",
        f"LDI r2 {data_addr}",
        "LDI r3 0",
        "ADD r3 r9",
        "SYSCALL r0 0x08",
        "JMP :done",
    ]

    prog += [
        ":write_branch",
        f"LDI r8 {data_addr}",
        "LDI r9 0",
        ":write_collect",
        "LDI r1 700",
        "LDI r2 1",
        "SYSCALL r3 0x02",
        "CMP r3 r4",
        "JZ :write_emit",
        "LD r5 r1",
        "ST r8 r5",
        "ADD r8 r12",
        "ADD r9 r12",
        "JMP :write_collect",
        ":write_emit",
        f"LDI r1 {path_addr}",
        f"LDI r2 {data_addr}",
        "LDI r3 0",
        "ADD r3 r9",
        "SYSCALL r0 0x03",
        "JMP :done",
    ]

    prog += [
        ":read_branch",
        f"LDI r1 {path_addr}",
        f"LDI r2 {read_addr}",
        f"LDI r3 {DISPATCH_BUF_CAP}",
        "SYSCALL r9 0x04",
        f"LDI r8 {read_addr}",
        ":read_print_loop",
        "CMP r9 r4",
        "JZ :done",
        "LD r5 r8",
        "PRT r5",
        "ADD r8 r12",
        "SUB r9 r12",
        "JMP :read_print_loop",
    ]

    prog += [
        ":done",
        # L3 sub-step 4: status-0 exit arm (mirrors build_exec_shell's).
        # 0x05 (SYSCALL_EXIT) copies r1 into rd (r9) and stops the engine;
        # :exit_err below reuses the same 0x05 contract with status 1.
        "LDI r1 0",
        "SYSCALL r9 0x05",
        ":exit_err",
        # status-1 exit arm: the grammar-gate/dispatch-failure paths land
        # here. 0x05 stops the engine with rd=r1=1.
        "LDI r1 1",
        "SYSCALL r9 0x05",
        # Defensive tail: 0x05 sets running=False, so this HALT is
        # unreachable unless an engine change breaks the EXIT contract.
        "HALT",
    ]

    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(prog, width_instrs=width_instrs)
    om.close()

    # Pad image so the FS window words [1024, 1280) have backing pixels
    # (same padding idiom as assemble_echo_app / assemble_voice_app).
    import numpy as np
    min_pixels = (max_word + 1) * 2
    rows_needed = max(img.shape[0] + 2, (min_pixels // (width_instrs * 4)) + 2, 42)
    if img.shape[0] < rows_needed:
        pad = np.zeros((rows_needed - img.shape[0], width_instrs * 4, 3), dtype=np.uint8)
        img = np.vstack([img, pad])

    # L1 shell personality (round 8, item 14): expose the FS-window word
    # addresses so a caller can stamp/inspect the path region without
    # re-deriving the layout. path_cap = words from path_addr to the audio
    # region minus one separator word (the same gap the stamps leave).
    layout = {
        "path_addr": path_addr,
        "audio_path_addr": audio_path_addr,
        "data_addr": data_addr,
        "read_addr": read_addr,
        "path_cap": audio_path_addr - path_addr - 2,
    }
    if return_layout:
        return img, layout
    return img


def run_turn(cpu: GlyphCPUv2, image, line: str) -> list[int]:
    """Seed the input ring with one line's bytes, run one turn, return what
    the app printed this turn (cpu.output is cleared before each turn so
    successive turns don't re-report earlier output)."""
    data = line.encode("utf-8", errors="replace")
    if len(data) > INPUT_DATA_CAP:
        data = data[:INPUT_DATA_CAP]  # ring cap, same bound the engine enforces
    cpu.memory[INPUT_LEN_ADDR >> 2] = len(data)
    cpu.memory[INPUT_CURSOR_ADDR >> 2] = 0
    for i, b in enumerate(data):
        cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
    cpu.pc = (0, 0)
    cpu.registers = [0] * 32
    cpu.output = []
    cpu.running = True
    cpu.halted = False
    cpu.faulted = False
    # Bumped for TASK_SE020: dispatch turns re-run fixed-path setup plus a
    # branch/collect loop every turn, needing more headroom than pure echo.
    # Bumped again for TASK_SE021: five ST-stamped path/buffer regions
    # (~70 instrs) + the full dispatch chain + longest branch. The 'z'
    # regression leg measred the exec build at ~270 steps; 1024 covers all
    # branches with margin without changing the turn-based semantics.
    cpu.run(image, max_instructions=max(2048, len(data) * 16 + 512))
    return list(cpu.output)


def repl(
    lines: list[str] | None = None,
    quit_word: str = "quit",
    image=None,
    fs_pix_enabled: bool = False,
    console: "TextConsole | None" = None,
) -> list[str]:
    """lines=None -> real interactive stdin (blocks on a human).
    lines=[...]  -> batch/non-blocking mode (the pytest-safe path); never
    touches stdin, always terminates.

    image/fs_pix_enabled default to the plain echo shell (unchanged
    behavior); TASK_SE020 callers pass image=build_dispatch_shell(...),
    fs_pix_enabled=True.

    console (DTF-2, item 10): optional TextConsole; each turn's PRT byte
    stream is fed into it so the session is renderable into the in-image
    text band. Pass a console to opt in; None (default) reproduces the
    pre-DTF-2 behavior exactly.

    Returns the list of echoed lines (as text) for assertion in tests.
    """
    if image is None:
        image = build_shell()
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=W, fs_pix_enabled=fs_pix_enabled)
    cpu.memory = [0] * 16384

    transcript: list[str] = []
    source = iter(lines) if lines is not None else None
    while True:
        if source is not None:
            try:
                line = next(source)
            except StopIteration:
                break
        else:
            try:
                line = input("glyph> ")
            except EOFError:
                break
        if line.strip() == quit_word:
            break
        echoed_bytes = run_turn(cpu, image, line)
        echoed = "".join(chr(b) for b in echoed_bytes)
        transcript.append(echoed)
        if console is not None:
            console.feed_bytes(bytes(echoed_bytes))
        if lines is None:
            print(f"  echo: {echoed}")
    return transcript


def _default_dispatch_paths() -> tuple[str, str]:
    """Fixed write/audio paths for the human entry surface (item 9, DTF-1
    follow-through). Short so build_dispatch_shell's FS-window assert holds;
    overridable via env so a user can redirect without editing code."""
    import os
    write_path = os.environ.get("GLYPH_SH_WRITE_PATH", "/tmp/glyph_sh_write.dat")
    audio_path = os.environ.get("GLYPH_SH_AUDIO_PATH", "/tmp/glyph_sh_audio.wav")
    return write_path, audio_path


if __name__ == "__main__":
    # ITEM 9 (2026-09-22, DTF-1 follow-through): the human entry point must
    # run the DISPATCH shell (e/s/w/r), not the always-echo shell. The old
    # default (build_shell via repl's image=None) made DTF-1 invisible to a
    # first-time user: 'w hello' echoed instead of writing a file.
    #
    # ITEM 10 (2026-09-22, DTF-2): each turn's PRT byte stream is also fed
    # into a TextConsole so the session renders into the in-image text band
    # (tools/glyph_text_console.py). The band is persisted to PNG after the
    # session ends — glass-TTY: rendering is a host-side renderer concern.
    write_path, audio_path = _default_dispatch_paths()
    print("Glyph interactive shell (dispatch mode). Commands:")
    print("  e <text>   echo the text back")
    print(f"  s <text>   speak the text (AUDIO_OUT -> {audio_path})")
    print(f"  w <text>   write the text to {write_path}")
    print("  r          read that file back")
    print("  quit       exit")
    print("  grammar: the byte after the command MUST be a space ('w note');")
    print("           anything else answers ERR:UNKNOWN_CMD -- nothing is")
    print("           ever executed silently (item 11). Payload is every")
    print("           byte after the command char, verbatim.")
    import os

    from tools.glyph_text_console import save_png
    console = TextConsole()
    repl(
        lines=None,
        image=build_dispatch_shell(write_path, audio_path),
        fs_pix_enabled=True,
        console=console,
    )
    band_path = os.environ.get(
        "GLYPH_SH_CONSOLE_PNG", "/tmp/glyph_sh_console_band.png")
    save_png(console.render_band(), band_path)
    print(f"  console band -> {band_path}")

#!/usr/bin/env python3
"""L1 shell personality (CLAIM QUEUE ROUND 8, item 14) — word verbs.

Layer contract (SUPPLY_ROUND8.json L1-PERSONALITY, operator direct):

  (a) "verbs become words ... parsed host-side INTO the existing glyph
      dispatch program — the GPU still executes the command body, the
      parser just routes argv";
  (b) "per-file paths: w/r take a filename argument via the existing
      FILE_WRITE/FILE_READ syscalls (0x03/0x04 already accept path_addr)";
  (c) "ERR:UNKNOWN_CMD grammar unchanged and re-gated".

Architecture (exactly the brief's split, disclosed in the receipt):

  GlyphL1Shell.turn(line) parses the verb host-side and routes:

    - echo/speak/write/read bodies execute ON THE GLYPH (the landed
      dispatch image, item-11 grammar intact): the harness seeds the input
      ring with the internal single-letter form and, for file ops, stamps
      the resolved absolute path into the FS window's path region BEFORE
      the turn — routing argv, not doing the I/O. The 0x03/0x04 syscalls
      execute on the CPU engine against a real on-disk path.
    - ls/pwd/cd/env/which/time/date/wc/head/tail/grep/cp/mv/rm are
      host-computed in L1 (the brief's own list; each is disclosed as a
      personality shim in RECEIPT_L1_shell_personality.md, with its
      in-image migration home named in L2/L3).
    - anything else -> ERR:UNKNOWN_CMD (same marker, same grammar class;
      single-letter legacy forms e/s/w/r stay live so the item-11 gate's
      legit legs keep their subjects).

Containment: guest paths resolve under the session root
(L1Session.resolve — absolute paths, `..` escapes and long components
refused; the shell's GLYPH_RUN_ALLOW analogue). Missing files refuse
host-side (ERR:NOENT:<name>) BEFORE the GPU turn, so the engine's
read-returns--1 PRT-garbage path is never armed (engine untouched).
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time as _time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from glyph_interactive_shell import (  # noqa: E402
    DISPATCH_ERROR_MARKER,
    DISPATCH_BUF_CAP,
    build_dispatch_shell,
    run_turn as _gpu_turn,
)
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    GlyphCPUv2,
    OpcodeMapV2,
)

ERR = DISPATCH_ERROR_MARKER.decode("ascii")          # ERR:UNKNOWN_CMD

RING_CAP = 64                                        # INPUT_DATA_CAP

# L3 sub-step 2: the `|` pipe. The brief's arm: "stdout of program A feeds
# stdin ring of program B — the host-side splice loop with backpressure,
# documented window-size limits". The window IS the input ring
# (INPUT_DATA_CAP = 64 bytes): producer output moves through the consumer
# one window per turn, and the loop is HARD-CAPPED so a big stream
# terminates (the supply gate's backpressure leg: 3x window across
# multiple turns terminates, not hangs).
PIPE_WINDOW = RING_CAP                               # 64-byte splice window
PIPE_MAX_TURNS = 4096                                # backpressure hard cap

# Reserved guest-path capacity (bytes, NUL included). The dispatch image's
# path region is sized by the write_path passed at build time, so the L1
# shell pads the seed path to this capacity: any argv path up to PATH_CAP-1
# chars stamps cleanly. Upper bound: the FS-window assert (data_addr +
# DISPATCH_BUF_CAP < 1280) allows 2*PATH_CAP + 134 < 256 -> PATH_CAP < 61.
PATH_CAP = 48
SEED_WRITE_PATH = "w.dat"

# L2-FILES sub-step 2: the ls/files listing is served by the engine's
# SYSCALL_FILE_LIST (0x13) arm — a baked LDI/SYSCALL/HALT program (the
# test_bk15 L1 baked-image precedent), not a host os.listdir shim.
# Address map: the dir argv re-uses the 0x02 scratch buffer at 700 (the
# per-turn echo scratch is dead by the time the listing arm runs, and
# run_turn's register/output resets make turn-to-turn reuse safe); the
# NUL-separated listing dest is plain RAM above the FS window (2100,
# outside 1024..1280, so names decode from memory[] directly). The rc is
# rd (r9): entry count, 0 for empty, -1 on refusal — the -1 is the
# deny-by-default propagation path (GLYPH_FS_ALLOW unset / outside
# roots); the shell turns it into ERR text and NEVER falls back to a
# host listing (gate test_m4/test_m5).
L2_LIST_DIR_ADDR = 700
L2_LIST_DEST_ADDR = 2100
L2_LIST_MAX_BYTES = 256
L2_LIST_PROG_STEPS = 64

# ── item 20 (CLAIM QUEUE ROUND 9): shell-native swap ─────────────────────
# Eligible verbs route through the TRANSPILED GLYPH BINARIES (item-19 /
# BK-25 volume port + BK-11 port #1: riscv64-unknown-elf-gcc -> RV32I ELF
# -> _load_posix_program -> libc_runtime_kernel_image -> GlyphRunner) on
# the file's CONTENT. The file's bytes ride as a C literal in the seed
# .data (the loader's parse_elf_data_sections contract), so the swap is
# DYNAMIC — any session file, any args; no fixture table at runtime.
#
# Phase doctrine (ledger, PHASE BOUNDARIES): this is a real Phase-2 ->
# Phase-3 transition leg — the tool's LOGIC executes on the glyph
# substrate (halted/faulted receipts from the engine), the host only
# stamps argv and reads the output ring. Fallback contract: if the
# cross-toolchain is absent the swap REFUSES LOUDLY
# (ERR:SHELLNATIVE:<verb>) instead of silently degrading to the host
# shim — a silent fallback would let a Phase-3 claim stand on
# host-Python output. _SHELL_NATIVE=False (instance attr, test hook)
# restores the host shim to prove the branch is live.
SHELL_NATIVE_DEFAULT = True
SHELLNATIVE_RUN_STEPS = 300000        # engine budget per swap turn


def _padded_seed(path: str) -> str:
    """Pad a seed path with NULs so the layout reserves PATH_CAP bytes."""
    assert len(path) <= PATH_CAP - 1, path
    return path + "\0" * (PATH_CAP - len(path))


def _strip_outer_quotes(s: str) -> str:
    """Strip matching single or double outer quotes if present."""
    s = s.strip()
    if len(s) >= 2:
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            return s[1:-1]
    return s


def _split_outside_quotes(line: str, sep: str) -> list[str]:
    """Split line by sep, but only when sep is outside single and double quotes."""
    segments = []
    current = []
    in_single = False
    in_double = False
    i = 0
    sep_len = len(sep)
    while i < len(line):
        ch = line[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
            i += 1
        elif ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
            i += 1
        elif not in_single and not in_double and line[i:i + sep_len] == sep:
            segments.append("".join(current))
            current = []
            i += sep_len
        else:
            current.append(ch)
            i += 1
    segments.append("".join(current))
    return segments


class L1Session:
    """Guest-visible root + cwd. Every guest path resolves inside root."""

    def __init__(self, root: str | None = None):
        self.root = os.path.realpath(
            os.environ.get("GLYPH_L1_ROOT") or root
            or tempfile.mkdtemp(prefix="glyph_l1_"))
        self.cwd = ""                                # guest-relative, "" == root
        Path(self.root).mkdir(parents=True, exist_ok=True)

    def resolve(self, guest_name: str) -> str:
        name = (guest_name or "").strip()
        if not name:
            raise ValueError("empty path")
        if name.startswith("/"):
            raise ValueError(f"absolute path refused: {name!r}")
        parts: list[str] = []
        for seg in name.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if parts:
                    parts.pop()
                    continue
                raise ValueError(f"path escapes the session root: {name!r}")
            if len(seg) > 64:
                raise ValueError(f"name component too long: {seg!r}")
            parts.append(seg)
        real = os.path.join(self.root, *parts) if parts else self.root
        real_real = os.path.realpath(real)
        if real_real != self.root and not real_real.startswith(self.root + os.sep):
            raise ValueError(f"path escapes the session root: {name!r}")
        return real

    def expand(self, guest_name: str) -> str:
        name = (guest_name or "").strip()
        if self.cwd:
            return self.resolve(os.path.join(self.cwd, name))
        return self.resolve(name)

    @property
    def cwd_display(self) -> str:
        return self.root if (not self.cwd or self.cwd == ".") else os.path.join(self.root, self.cwd)


L1_VERBS = (
    "echo", "speak", "write", "read", "cat", "ls", "files", "wc", "head",
    "tail", "grep", "tr", "time", "date", "pwd", "env", "which", "cp", "mv",
    "rm", "cd", "mkdir", "rmdir", "python", "python3",
)


class GlyphL1Shell:
    """The word-verb shell. One CPU instance; turns reset the PC like the
    dispatch harness (run_turn semantics)."""

    def __init__(self, session: L1Session | None = None, audio_path: str | None = None):
        self.session = session or L1Session()
        self.audio_path = audio_path or os.path.join(self.session.root, "out.wav")
        # Build the dispatch image WITHOUT in-image path stamps (the stamps
        # would clobber the harness's per-turn argv-path routing); the
        # harness owns path-region contents from here on.
        self.image, self.layout = build_dispatch_shell(
            _padded_seed(SEED_WRITE_PATH),
            self.audio_path,
            stamp_paths=False,
            return_layout=True,
        )
        self.cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=8, fs_pix_enabled=True)
        self.cpu.memory = [0] * 16384
        self._seed_paths()
        self.last_status: int = 0
        # item 20: the shell-native swap arm (True -> eligible verbs run
        # the transpiled glyph binaries; False -> the host shims, the
        # pre-item-20 behavior). Exposed as an attribute so the gate can
        # flip it and prove the branch point is live (L5b).
        self._SHELL_NATIVE = SHELL_NATIVE_DEFAULT
        # BK-27: the shell-native bake cache. Key = the FULL bake input
        # vector (verb, argv, data length, data bytes hash) — everything
        # the generated C source depends on. Data length rides the key
        # explicitly: TR_LEN seeds differ between sources, so a
        # (verb, argv, hash) triple whose length matches implies identical
        # bytes. Bypass (set to False) for non-vacuity proofs.
        self._SHELLNATIVE_BAKE_CACHE = True
        self._bake_cache: dict = {}

    # -- path-region ownership --------------------------------------------
    def _seed_paths(self) -> None:
        # Both FS-window path regions the dispatch program reads: the
        # write/read path (path_addr, shared by the 'w' and 'r' arms) and
        # the audio path (audio_path_addr, the 's' arm). stamp_paths=False
        # left both zeroed -- an unstamped audio region made AUDIO_OUT
        # target an empty path (silent no-write, out.wav never created).
        self._stamp_path(os.path.join(self.session.root, SEED_WRITE_PATH))
        self._stamp_path(self.audio_path, base=self.layout["audio_path_addr"])

    def _stamp_path(self, real_path: str, base: int | None = None) -> None:
        # BK-44: the engine's 0x03/0x04 host arms now require the path's
        # realpath under a GLYPH_FS_ALLOW root (same deny-by-default model
        # the 0x13 listing arm already had). The shell's own containment
        # scope IS the session root, so arm it here — the single choke
        # point every file verb (write/read/cat) stamps through. Same
        # append-only policy as _arm_fs_allow/_l2_list: pre-existing roots
        # preserved, nothing narrowed.
        self._arm_fs_allow()
        base = self.layout["path_addr"] if base is None else base
        cap = self.layout["path_cap"]
        blob = real_path.encode() + b"\0"
        if len(blob) > cap:
            raise ValueError(f"path too long for the FS window: {real_path!r}")
        # Stamp through the FS-PIXEL view (glyph_isa_v2._mem_write ->
        # _fs_pix_write): inside the window (1024..1280) the pixels are
        # the persisted truth and memory[] is only the write-through
        # mirror. _read_path decodes through _fs_pix_read, so a
        # memory-only stamp decodes as the empty string and every
        # 0x03/0x04/0x08 syscall refuses its path. Same mechanism the
        # in-image ST stamps use.
        for i, byte in enumerate(blob):
            self.cpu._mem_write(self.image, base + i, byte)

    # -- one turn ----------------------------------------------------------
    def turn(self, line: str) -> str:
        """Execute one shell line; return the turn's text output (PRT stream
        for glyph bodies, host text for personality shims, '' for silent
        ops like write — the dispatch contract)."""
        stripped = line.strip()
        if stripped == "quit":
            raise EOFError("quit")
        # L3 sub-step 4: `;` command sequencing (lowest precedence)
        semi_segs = _split_outside_quotes(stripped, ";")
        if len(semi_segs) > 1:
            if ";;" in stripped:
                self.last_status = 1
                return ERR
            segments = [s.strip() for s in semi_segs]
            if any(not s for s in segments[:-1]):
                self.last_status = 1
                return ERR
            outputs = []
            for seg in segments:
                if not seg:
                    continue
                res = self.turn(seg)
                if res:
                    outputs.append(res)
            return "\n".join(outputs) if outputs else ""

        # L3 sub-step 4: `&&` conditional sequencing (short-circuit on failure)
        and_segs = _split_outside_quotes(stripped, "&&")
        if len(and_segs) > 1:
            if "&&&" in stripped or stripped.startswith("&&") or stripped.endswith("&&"):
                self.last_status = 1
                return ERR
            segments = [s.strip() for s in and_segs]
            if any(not s for s in segments):
                self.last_status = 1
                return ERR
            outputs = []
            for seg in segments:
                res = self.turn(seg.strip())
                if self.last_status != 0 or res.startswith("ERR:"):
                    self.last_status = 1
                    if res:
                        outputs.append(res)
                    return "\n".join(outputs) if outputs else res
                if res:
                    outputs.append(res)
            self.last_status = 0
            return "\n".join(outputs) if outputs else ""

        # L3 sub-step 4: expand $? exit status
        if "$?" in stripped:
            stripped = stripped.replace("$?", str(self.last_status))

        # Dispatch single command turn
        res = self._turn_single(stripped)
        if res.startswith("ERR:"):
            if not self.last_status:
                self.last_status = 1
        else:
            self.last_status = 0
        return res

    def _turn_single(self, stripped: str) -> str:

        # L3 sub-step 2: `|` splits BEFORE verb dispatch; a pipe line never
        # reaches the single-verb grammar (which would ERR or mis-parse the
        # `|` as a filename byte). Empty segments refuse with the grammar
        # marker; the splice loop runs the producer, streams its stdout
        # through the 64-byte window into the consumer, and returns the
        # consumer's output only.
        if len(_split_outside_quotes(stripped, "|")) > 1:
            return self._pipe(stripped)

        # L3 sub-step 3: `<` input redirection, also split BEFORE verb
        # dispatch (the file-arg shims would mis-read `< f.txt` as a
        # filename and raise FileNotFoundError out of turn()).
        if len(_split_outside_quotes(stripped, "<")) > 1:
            return self._lt(stripped)

        parts = stripped.split(" ", 2)
        verb = parts[0]

        # legacy single-letter forms pass straight through to the glyph
        if verb in ("e", "s", "w", "r", "x"):
            return self._gpu_line(stripped)

        try:
            if verb == "echo":
                rest = stripped[len("echo"):].lstrip()
                if ">>" in rest:
                    text, _, dest = rest.partition(">>")
                    dest_name = dest.strip()
                    if not dest_name:
                        return ERR
                    real = self.session.expand(dest_name)
                    if os.path.isdir(real):
                        return f"ERR:EISDIR:{dest_name}"
                    parent = os.path.dirname(real)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    payload = b" " + _strip_outer_quotes(text.strip()).encode("utf-8")
                    with open(real, "ab") as f:
                        f.write(payload)
                    return ""
                # L3 sub-step 1: single-`>` TRUNCATE redirection
                # (POSIX `echo text > file`): create-or-truncate, payload
                # honors the dispatch convention (" " + text) so `cat`
                # reads back byte-exact with the append/write arms. The
                # `>>` arm above already matched, so a bare `>` here is
                # unambiguous. Containment via session.expand (the outer
                # ValueError handler emits ERR:PATH).
                if ">" in rest:
                    text, _, dest = rest.partition(">")
                    dest_name = dest.strip()
                    if not dest_name:
                        return ERR
                    real = self.session.expand(dest_name)
                    if os.path.isdir(real):
                        return f"ERR:EISDIR:{dest_name}"
                    parent = os.path.dirname(real)
                    if parent:
                        os.makedirs(parent, exist_ok=True)
                    payload = b" " + _strip_outer_quotes(text.strip()).encode("utf-8")
                    with open(real, "wb") as f:
                        f.write(payload)
                    return ""
                return self._gpu_line("e " + rest.removeprefix(""))
            if verb == "speak":
                payload = stripped[len("speak"):].lstrip()
                return self._gpu_line("s " + payload)
            if verb == "write":
                rest = stripped[len("write"):].lstrip()
                append_mode = False
                if rest.startswith(">>"):
                    append_mode = True
                    rest = rest[2:].lstrip()
                name, sep, text = rest.partition(" ")
                if not name and sep:
                    name, sep, text = text.partition(" ")
                if sep and text.startswith(">>"):
                    append_mode = True
                    text = text[2:].lstrip()
                if not name:
                    return ERR
                real = self.session.expand(name)
                if os.path.isdir(real):
                    return f"ERR:EISDIR:{name}"
                parent = os.path.dirname(real)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                if append_mode:
                    with open(real, "ab") as f:
                        f.write(b" " + text.encode("utf-8"))
                    return ""
                self._stamp_path(real)
                return self._gpu_line("w " + text)
            if verb == "read":
                rest = stripped[len(verb):].strip()
                if not rest:
                    return self._gpu_line("r")
                if " " in rest:
                    # 'read me the news' is a sentence, not a filename --
                    # refuse with the GRAMMAR marker, not a path error
                    # (the item-11 grammar class carries through the word
                    # surface; a path error here would leak a host path).
                    return ERR
                real = self.session.expand(rest)
                if not os.path.isfile(real):
                    # Host-side NOENT refusal BEFORE the GPU turn: a
                    # missing file makes FILE_READ return -1 and the
                    # glyph print loop walks the stale read buffer
                    # wrapping through NULs (never arm that path).
                    return f"ERR:NOENT:{rest}"
                self._stamp_path(real)
                return self._gpu_line("r")
            if verb == "cat":
                rest = stripped[len(verb):].strip()
                if not rest:
                    return self._gpu_line("r")
                names = rest.split()
                if len(names) == 1:
                    real = self.session.expand(names[0])
                    if not os.path.isfile(real):
                        return f"ERR:NOENT:{names[0]}"
                    self._stamp_path(real)
                    return self._gpu_line("r")
                # BK-22: multi-file cat concatenates each file's content in
                # argument order; a missing file emits its ERR:NOENT marker
                # in place while the rest still process (partial failure).
                segments = []
                for name in names:
                    real = self.session.expand(name)
                    if not os.path.isfile(real):
                        segments.append(f"ERR:NOENT:{name}")
                        continue
                    self._stamp_path(real)
                    segments.append(self._gpu_line("r"))
                return "\n".join(segments)
            if verb == "ls":
                return self._ls(stripped[len("ls"):].strip())
            if verb == "files":
                # L2-FILES sub-step 2: `files` is the BK-15 backlog row's
                # verb over SYSCALL_FILE_LIST; alias of ls.
                return self._ls(stripped[len("files"):].strip())
            if verb == "pwd":
                return self.session.cwd_display
            if verb == "cd":
                return self._cd(stripped[len("cd"):].strip())
            if verb == "env":
                return f"GLYPH_L1_ROOT={self.session.root}"
            if verb == "which":
                target = stripped[len("which"):].strip()
                if target in L1_VERBS:
                    return target
                return ERR
            if verb in ("time", "date"):
                return str(int(_time.time()))
            if verb == "wc":
                # BK-46 (2026-10-01): SWAPPED. The old "NOT swapped —
                # 16-byte window truncates" refusal was falsified twice
                # over (RESEARCH_wc_swap_refusal_af3e.md): the real
                # blockers were a latent compile failure (the dynamic
                # seed block omitted _COMMON + the wc_name seed — the
                # swap never ran at all) and the V1 body's 2-digit
                # counter renderer ('310' -> 'O0'). Both fixed; the
                # BK-24 streaming ring carries any report size (measured
                # 60-word / 945-byte stream clean, probe_bk47_ring_af3e);
                # past the ring's 64-word extent the swap refuses LOUDLY
                # (never a silent host fallback — the phase doctrine).
                target = stripped[len("wc"):].strip()
                if self._SHELL_NATIVE and target and " " not in target and not target.startswith("-"):
                    return self._shell_native("wc", target)
                return self._wc(target)
            if verb == "head":
                # BK-47: SWAPPED — same root cause as wc (missing
                # _COMMON killed the dynamic TU at LINK; the recorded
                # "empty ring" symptom was the ERR string misread).
                # Native == host shim byte-exact on every landed edge
                # (n-exceeds, no trailing newline, blank lines).
                if self._SHELL_NATIVE:
                    return self._shell_native("head", stripped[len("head"):].strip())
                return self._head_tail(stripped[len("head"):].strip(), head=True)
            if verb == "tail":
                return self._head_tail(stripped[len("tail"):].strip(), head=False)
            if verb == "grep":
                if self._SHELL_NATIVE:
                    return self._shell_native("grep", stripped[len("grep"):].strip())
                return self._grep(stripped[len("grep"):].strip())
            if verb == "tr":
                if self._SHELL_NATIVE:
                    return self._shell_native("tr", stripped[len("tr"):].strip())
                # no host tr shim ever existed (item 14 personality list);
                # with the native arm off, tr has no executor -> grammar ERR.
                return ERR
            if verb in ("python", "python3"):
                return self._python(stripped[len(verb):].strip())
            if verb == "cp":
                return self._cp_mv(stripped[len("cp"):].strip(), copy=True)
            if verb == "mv":
                return self._cp_mv(stripped[len("mv"):].strip(), copy=False)
            if verb == "rm":
                return self._rm(stripped[len("rm"):].strip())
            if verb == "mkdir":
                return self._mkdir(stripped[len("mkdir"):].strip())
            if verb == "rmdir":
                return self._rmdir(stripped[len("rmdir"):].strip())
        except (ValueError, FileNotFoundError) as exc:
            return str(exc) if str(exc).startswith("ERR:") else f"ERR:PATH:{exc}"
        return ERR

    # -- L3 sub-step 2: the `|` pipe (host-side splice loop) -----------------
    def _pipe(self, line: str) -> str:
        """`A | B`: run producer A, stream its stdout through the window
        (RING_CAP bytes per consumer turn — the input ring's own capacity,
        the brief's documented window-size limit) into consumer B, return
        B's output. Backpressure termination: the loop is bounded by both
        the stream length and PIPE_MAX_TURNS — it always terminates.

        Error semantics: producer ERR propagates and the consumer NEVER
        runs (short-circuit, POSIX order). Empty segments refuse with the
        grammar marker. Producers may be glyph bodies (echo/cat) or host
        shims (grep/head/tail/ls/...); consumers are the host shims that
        can read stdin (wc/head/tail/grep) — a consumer without stdin
        support refuses with the grammar marker, never silently drops the
        stream.
        """
        segs = [s.strip() for s in _split_outside_quotes(line, "|")]
        if any(not s for s in segs):
            return ERR
        if len(segs) != 2:
            return ERR

        prod_line, cons_line = segs

        # Producer: capture stdout by temporarily swapping the transcript
        # sink. turn() returns text for every verb, so the capture is just
        # the producer's return value — no process plumbing needed.
        #
        # item-20 SCOPING (receipt-honest, not a silent fallback): pipe
        # producers run the HOST shims — the native arm is OFF for the
        # producer turn only. Why: the BK-24 write tile appends without
        # ring saturation (documented non-goal, libc_runtime.py —
        # "every landed fixture flushes at most twice (32 words < 64)"),
        # and the glyph-executed grep FAULTS once its appended stream
        # outgrows the ring neighborhood (measured: clean at 24 lines /
        # ~576B, faults at 25+; .builder_queue/dbg_item20_budget_af3e.py).
        # P7's pinned producer streams 2399 bytes — far past the boundary.
        # A saturated/paged write tile is engine-side work (stamped
        # branch = the defect class BK-24 deliberately avoids) and stays
        # backlog; until it lands, the pipe splice needs the uncapped
        # host producer. Top-level turns keep the swap (the item-20 gate
        # pins it live); this flag is the SAME branch point L4b tests.
        saved_native = self._SHELL_NATIVE
        self._SHELL_NATIVE = False
        try:
            producer_out = self.turn(prod_line)
        finally:
            self._SHELL_NATIVE = saved_native
        if producer_out.startswith("ERR"):
            return producer_out
        stream = producer_out.encode("utf-8")

        # Consumer: feed the stream through the window, one turn at a time.
        # Each consumer turn receives at most PIPE_WINDOW bytes — the
        # multi-turn splice the supply gate's backpressure leg demands.
        # wc/head/tail/grep are STREAM consumers: each window's result
        # accumulates (chars) or merges (lines) across turns; the final
        # (eof) turn's result is the pipe's answer. This is what makes
        # 3x-window input produce 3x-window numbers, not last-window ones.
        cons_verb = cons_line.split(" ", 1)[0]
        if cons_verb not in ("wc", "head", "tail", "grep", "python", "python3"):
            return ERR
        offset = 0
        result = ""
        turns = 0
        acc_lines: list[str] = []
        acc_chars = 0
        buf = ""                                # partial line carried across windows
        while offset < len(stream) or (offset == 0 and not stream):
            chunk = stream[offset:offset + PIPE_WINDOW]
            offset += len(chunk)
            eof = offset >= len(stream)
            turns += 1
            if turns > PIPE_MAX_TURNS:      # pragma: no cover — unreachable
                return "ERR:PIPE_OVERFLOW"  # (defensive; bounded above too)
            # line-aware splice: only COMPLETE lines (newline-terminated)
            # are processed per window; a line split across a window
            # boundary is carried in buf so wc/grep/head/tail never see a
            # phantom line break. (chars accounting uses raw chunk bytes —
            # byte-exact regardless of line boundaries.)
            text = buf + chunk.decode("utf-8", errors="replace")
            buf = ""
            if not eof and "\n" in text:
                cut = text.rfind("\n") + 1
                buf, text = text[cut:], text[:cut]
            elif not eof:
                buf, text = text, ""
            if cons_verb == "wc":
                # byte-exact accounting: count THIS window's chars, merge
                # lines; the final number covers the WHOLE stream.
                acc_chars += len(chunk)
                acc_lines.extend(text.splitlines())
                if eof:
                    if buf:
                        acc_lines.extend(buf.splitlines())
                    result = f"{len(acc_lines)} {len(' '.join(acc_lines).split())} {acc_chars}"
            elif cons_verb in ("head", "tail"):
                # accumulate every window's lines; head/tail pick at eof
                # (bounded by stream length, so termination holds).
                acc_lines.extend(text.splitlines())
                if eof:
                    if buf:
                        acc_lines.extend(buf.splitlines())
                    count = self._head_tail_count(cons_line)
                    picked = acc_lines[:count] if cons_verb == "head" else acc_lines[-count:]
                    result = "\n".join(picked)
            elif cons_verb in ("python", "python3"):
                if eof:
                    result = self._python_stdin(cons_line, stream.decode("utf-8", errors="replace"))
            else:  # grep
                if text:
                    partial = self._turn_stdin(cons_line, text)
                    if partial:
                        acc_lines.extend(partial.splitlines())
                if eof and buf:
                    partial = self._turn_stdin(cons_line, buf)
                    if partial:
                        acc_lines.extend(partial.splitlines())
                if eof:
                    result = "\n".join(acc_lines)
            if offset >= len(stream):
                break
        return result

    def _head_tail_count(self, cons_line: str) -> int:
        """Extract the -n N count from a head/tail consumer line (default 1)."""
        _, _, arg = cons_line.partition(" ")
        arg = arg.strip()
        if arg.startswith("-n "):
            n, _, rest = arg[3:].partition(" ")
            try:
                return max(1, int(n))
            except ValueError:
                return 1
        return 1

    # -- L3 sub-step 3: `<` input redirection --------------------------------
    def _lt(self, line: str) -> str:
        """`cmd < file`: feed file content to the command's stdin.

        POSIX order: the file argument is resolved (containment via
        session.expand — escapes raise ValueError -> ERR:PATH) and must
        exist BEFORE the command runs; a missing source refuses with
        ERR:NOENT and the command NEVER runs (P5's `<` analogue). Only
        one `<` per line: a second refuses with the grammar marker
        (multi-stream stdin is not this sub-step). Consumers are the
        stdin-capable shims via _turn_stdin (wc/head/tail/grep); anything
        else refuses with the grammar marker, never silently drops input.
        A glyph-body command (echo/cat/read) has no stdin surface — the
        grammar refusal covers that too.
        """
        segs = _split_outside_quotes(line, "<")
        if len(segs) != 2:
            return ERR
        left, source = segs[0], segs[1]
        cmd = left.strip()
        source_name = source.strip()
        if not cmd or not source_name:
            return ERR
        if len(_split_outside_quotes(source_name, "<")) > 1:
            return ERR
        try:
            real = self.session.expand(source_name)
        except ValueError as exc:
            return f"ERR:PATH:{exc}"
        if not os.path.isfile(real):
            return f"ERR:NOENT:{source_name}"
        # The `cat f | cmd` keep-contract pins cat's kernel-added trailing
        # newline; `<` reads the FILE bytes directly, so a wc on the same
        # fixture sees the file's true size — the POSIX distinction, and
        # the non-vacuity trip for an implementation that secretly pipes
        # through the cat glyph body.
        stream = Path(real).read_bytes()
        return self._turn_stdin(cmd, stream.decode("utf-8", errors="replace"))

    def _turn_stdin(self, cons_line: str, chunk: str) -> str:
        """One consumer turn with `chunk` as its stdin. Line-consumer
        helpers for the pipe splice; file-arg consumers take the piped
        text instead of their file argument (POSIX `wc` with no args)."""
        verb, _, arg = cons_line.partition(" ")
        arg = arg.strip()
        if verb == "wc":
            lines = len(chunk.splitlines())
            words = len(chunk.split())
            chars = len(chunk)
            return f"{lines} {words} {chars}"
        if verb in ("head", "tail"):
            count = self._head_tail_count(cons_line)
            # stdin form: no file arg after the optional -n N
            if arg and not arg.startswith("-n"):
                return ERR
            lines = chunk.splitlines()
            picked = lines[:count] if verb == "head" else lines[-count:]
            return "\n".join(picked)
        if verb == "grep":
            pat = _strip_outer_quotes(arg.strip())
            if not pat:
                return ERR
            hits = [ln for ln in chunk.splitlines() if pat in ln]
            return "\n".join(hits)
        if verb in ("python", "python3"):
            return self._python_stdin(cons_line, chunk)
        return ERR

    # -- glyph-body turns ---------------------------------------------------
    def _gpu_line(self, internal: str) -> str:
        if len(internal.encode()) > RING_CAP:
            raise ValueError(f"line exceeds the {RING_CAP}-byte input ring")
        out = _gpu_turn(self.cpu, self.image, internal)
        return "".join(chr(b) for b in out)

    # -- engine-served listing (L2-FILES sub-step 2) ------------------------
    def _l2_list(self, guest_dir: str) -> list[str]:
        """Serve a listing through the engine's SYSCALL_FILE_LIST (0x13) arm.

        Resolves the (contained, root-relative) dir path, arms the 0x13
        containment with the session root, stamps the dir path into the
        listing program's OWN FS-window pixels (fs_pix_enabled: the pixels
        of the image the PC walks are the persisted truth), runs the baked
        LDI/SYSCALL r9 0x13/HALT program, and parses the NUL-separated RAM
        dest blob into names. rc -1 (refusal: dir outside GLYPH_FS_ALLOW)
        propagates as ValueError so the caller emits ERR text; there is
        NO host os.listdir fallback.
        """
        real = self.session.expand(guest_dir)
        if not os.path.isdir(real):
            raise FileNotFoundError(f"ERR:NOENT:{guest_dir or '.'}")
        # Arm the 0x13 containment for THIS listing: the session root is
        # the shell's own containmentscope (L1Session.resolve is the
        # GLYPH_RUN_ALLOW analogue for argv paths), so it is also the one
        # root the listing arm may enumerate. Pre-existing GLYPH_FS_ALLOW
        # roots are preserved (append, not overwrite) — the shell NARROWS
        # nothing it did not itself grant.
        roots = [
            r for r in os.environ.get("GLYPH_FS_ALLOW", "").split(":")
            if r.strip()
        ]
        if self.session.root not in roots:
            roots.append(self.session.root)
        os.environ["GLYPH_FS_ALLOW"] = ":".join(roots)
        om = OpcodeMapV2()
        asm = GlyphAssemblerV2(om)
        prog = [
            f"LDI r1 {self.layout['path_addr']}",
            f"LDI r2 {L2_LIST_DEST_ADDR}",
            f"LDI r3 {L2_LIST_MAX_BYTES}",
            "SYSCALL r9 0x13",
            "HALT",
        ]
        image = asm.assemble(prog, width_instrs=8)
        # Pad so the FS-window words have backing pixels (word w maps to
        # pixel 2w — the build_dispatch_shell idiom), then stamp the argv
        # path into THE PROGRAM'S OWN pixels: with fs_pix_enabled the
        # pixels of the image the PC walks are the persisted truth, and a
        # program on a fresh image reads its OWN window, not the dispatch
        # image's (measured: unpadded -> rc -1 not-a-directory; padded +
        # own-pixel stamp is the only working combination).
        import numpy as np
        min_pixels = (L2_LIST_DEST_ADDR + 1) * 2
        rows_needed = max((min_pixels // (8 * 4)) + 2, 42)
        if image.shape[0] < rows_needed:
            pad = np.zeros((rows_needed - image.shape[0], 8 * 4, 3), dtype=np.uint8)
            image = np.vstack([image, pad])
        for i, b in enumerate(real.encode() + b"\0"):
            self.cpu._mem_write(image, self.layout["path_addr"] + i, b)
        cpu = self.cpu
        cpu.pc = (0, 0)
        cpu.registers = [0] * 32
        cpu.output = []
        cpu.running = True
        cpu.faulted = False
        n = 0
        while cpu.running and n < L2_LIST_PROG_STEPS:
            cpu.step(image)
            n += 1
        rc = cpu.registers[9]
        if rc == 0xFFFFFFFF or rc < 0:
            raise ValueError(f"ERR:FILE_LIST:{guest_dir or '.'}")
        raw = bytes(self.cpu.memory[L2_LIST_DEST_ADDR:L2_LIST_DEST_ADDR + L2_LIST_MAX_BYTES])
        names = [p.decode("utf-8", errors="replace") for p in raw.split(b"\0") if p]
        # rc is the engine's ENTRY COUNT; the blob can't carry more names
        # than that (whole-name truncation is the engine's own contract).
        return names[:rc]

    # -- host personality verbs ---------------------------------------------
    def _ls(self, arg: str = "") -> str:
        # Resolve the listing directory from argv (cwd-honoring): `ls sub`
        # lists the subdirectory; bare ls lists the cwd.
        argv = arg.split() if arg else []
        flags = [a for a in argv if a.startswith("-")]
        positional = [a for a in argv if not a.startswith("-")]
        if len(positional) > 1:
            return ERR
        # Bare ls lists the cwd; an argv path is cwd-relative. NOTE: the
        # cwd itself must NOT be pre-expanded through expand() — expand
        # joins guest paths against the cwd, so expand(cwd) would double
        # the prefix (root/sub/sub). Pass the raw guest path and let
        # _l2_list's single expand() do the join.
        guest_dir = positional[0] if positional else "."
        try:
            names = self._l2_list(guest_dir)
        except (FileNotFoundError, ValueError) as exc:
            return str(exc)
        if flags and set(flags) <= {"-l", "-la", "-al"}:
            # L2-FILES sub-step 1 columns over the 0x13-served names:
            # size/mtime are stat() facts about the files the 0x03/0x04
            # arms wrote (engine-side FSTAB created-ts is a later sub-step).
            d = self.session.expand(guest_dir)
            rows = []
            for n in names:
                st = os.stat(os.path.join(d, n))
                rows.append(f"{st.st_size} {_time.strftime('%Y-%m-%d %H:%M', _time.localtime(st.st_mtime))} {n}")
            return "\n".join(rows)
        return "\n".join(names)

    def _cd(self, target: str) -> str:
        if not target or target == "~":
            self.session.cwd = ""
            return ""
        real = self.session.expand(target)
        if not os.path.isdir(real):
            return f"ERR:NODIR:{target}"
        rel = os.path.relpath(real, self.session.root)
        self.session.cwd = "" if rel == "." else rel
        return ""

    def _read_guest(self, name: str) -> str:
        real = self.session.expand(name)
        if not os.path.isfile(real):
            raise FileNotFoundError(f"ERR:NOENT:{name}")
        return Path(real).read_text()

    # -- item 20: shell-native swap (transpiled glyph binaries) ------------
    def _shell_native(self, verb: str, arg: str) -> str:
        """Run `verb` through the transpiled glyph binary on a session
        file's content and return the tool's stdout text (the same turn
        contract the host shims honor — parity is the swap's premise).

        Loud-refusal contract: no cross-toolchain -> ERR:SHELLNATIVE:<verb>
        (never a silent host-shim fallback); missing file -> ERR:NOENT
        BEFORE any compile; engine halt/fault -> ERR:SHELLNATIVE:<verb>
        with the receipt shape in the message. The compile+transpile+bake
        runs per turn (~1.7s measured, dbg_item20_probe_af3e.py) — honest
        cost of keeping the swap dynamic (any file, any args)."""
        if shutil.which("riscv64-unknown-elf-gcc") is None:
            return f"ERR:SHELLNATIVE:{verb}"
        # ── parse argv host-side (the shell's job in both phases) ────────
        try:
            if verb == "grep":
                pat, _, name = arg.partition(" ")
                pat = _strip_outer_quotes(pat.strip())
                if not pat or not name:
                    return ERR
                argv = {"pattern": pat}
                data = self._read_guest(name.strip())
            elif verb == "tr":
                set1, _, rest = arg.partition(" ")
                set2, _, name = rest.partition(" ")
                if not set1 or not set2 or not name:
                    return ERR
                if len(set1) != len(set2):
                    return "ERR:RANGE:tr sets differ"
                argv = {"set1": set1, "set2": set2}
                data = self._read_guest(name.strip())
            elif verb == "head":
                n, name = 1, arg
                if name.startswith("-n "):
                    n_raw, _, name = name[3:].partition(" ")
                    n = max(1, int(n_raw))
                if not name:
                    return ERR
                argv = {"n": n}
                data = self._read_guest(name.strip())
            elif verb == "wc":
                name = arg.strip()
                if not name or " " in name:
                    return ERR
                argv = {"name": name}
                data = self._read_guest(name)
            else:
                return f"ERR:SHELLNATIVE:{verb}"
        except FileNotFoundError as exc:
            return str(exc)
        except ValueError as exc:
            return ERR

        # ── compile the tool against THIS file's bytes ───────────────────
        from tools.glyph_gpt.coreutils_port import (
            _TOOL_SOURCES,
            _VOL2_TOOL_SOURCES,
            _COMMON,
            _c_literal,
        )
        from tests.test_gh23_libc_runtime import (
            _load_posix_program,
            LIBC_C,
            SHIM_S,
        )
        from tools.glyph_gpt.baker import libc_runtime_kernel_image
        from tools.glyph_gpt.atlas import build_default_atlas
        from tools.glyph_gpt.runner import GlyphRunner

        src_tool = verb if verb in _VOL2_TOOL_SOURCES else verb
        body = (_VOL2_TOOL_SOURCES.get(verb)
                or _TOOL_SOURCES.get(verb))
        if body is None:
            return f"ERR:SHELLNATIVE:{verb}"

        # BK-46/47: the V1 (BK-11) tool bodies are compiled against the
        # _COMMON emit preamble (bk11_out_ch/out_str/flush — the BK-11
        # fixture builder prepends it at coreutils_port.py), which this
        # dynamic seed block OMITTED — every wc/head swap died at gcc
        # ('_n' undeclared) / ld ('undefined reference to bk11_out_ch')
        # and surfaced as an opaque ERR:SHELLNATIVE (measured
        # probe_bk46_red_af3e.py P1..P3). Prepend the same preamble the
        # landed BK-11 harness uses. VOL2 bodies (grep/tr) carry their
        # own _VOL2_COMMON inside the source and must NOT get _COMMON.
        preamble = "" if verb in _VOL2_TOOL_SOURCES else _COMMON

        # seed block: the session file rides as initialized .data (the
        # loader's parse_elf_data_sections contract — the same mechanism
        # the landed gates use, generated per-turn instead of per-fixture).
        data_len = len(data)
        seeds = [f'static const char *{verb}_data = "{_c_literal(data)}";']
        derived: list[str] = []
        aliases: list[str] = []
        if verb == "grep":
            seeds.append(
                f'static const char *{verb}_pattern = "{_c_literal(pat)}";')
            aliases.append("#define GREP_DATA grep_data")
            aliases.append("#define GREP_PAT grep_pattern")
            derived.append(f"static unsigned TR_LEN = {data_len};")
        elif verb == "tr":
            seeds.append(f'static const char *tr_set1 = "{_c_literal(set1)}";')
            seeds.append(f'static const char *tr_set2 = "{_c_literal(set2)}";')
            aliases.append("#define TR_DATA tr_data")
            aliases.append("#define TR_SET1 tr_set1")
            aliases.append("#define TR_SET2 tr_set2")
            derived.append(f"static unsigned TR_LEN = {data_len};")
        elif verb == "wc":
            seeds.append(
                f'static const char *wc_name = "{_c_literal(name)}";')
            aliases.append("#define WC_DATA wc_data")
            aliases.append("#define WC_NAME wc_name")
            derived.append(f"static unsigned WC_LEN = {data_len};")
        elif verb == "head":
            derived.append(f"static long HEAD_N = {int(n)};")
            aliases.append("#define HEAD_DATA head_data")

        # ── BK-27: consult the bake cache keyed on the full input ──────────
        cache_key = None
        if self._SHELLNATIVE_BAKE_CACHE:
            cache_key = (
                verb,
                json.dumps(argv, sort_keys=True),
                data_len,
                hashlib.sha256(data.encode("utf-8")).hexdigest(),
            )
            cached = self._bake_cache.get(cache_key)
            if cached is not None:
                # byte-exact image replay of the previous turn's bake —
                # the same runner.run contract, same receipt shape.
                runner = GlyphRunner(cached, ram_words=16384)
                receipt = runner.run(max_instructions=SHELLNATIVE_RUN_STEPS,
                                     trace=True)
                if receipt.get("halted") and not receipt.get("faulted"):
                    mem = receipt["memory"]
                    return self._shell_native_collect(mem, verb)
                # a cached image that faults now would have faulted then;
                # treat as corruption and fall through to a fresh bake.
                self._bake_cache.pop(cache_key, None)

        try:
            with tempfile.TemporaryDirectory(prefix="glyph_native_") as td:
                tmp = Path(td)
                src = tmp / "tool.c"
                src.write_text(
                    preamble + "\n" + "\n".join(seeds) + "\n"
                    + "\n".join(derived) + "\n"
                    + "\n".join(aliases) + "\n" + body
                )
                libc = tmp / "gh23_libc.c"
                libc.write_text(LIBC_C)
                shim = tmp / "shim.S"
                shim.write_text(SHIM_S)
                gcc = "riscv64-unknown-elf-gcc"
                objs = []

                # BK-47 L4 diagnostic contract: a compile/link failure
                # previously surfaced as a bare ERR:SHELLNATIVE:<verb>
                # (indistinguishable from a missing toolchain — the
                # wc/head defect hid behind exactly this mask). The ERR
                # string now carries the FIRST stderr 'error:' line.
                def _gcc_err(proc) -> str:
                    for ln in proc.stderr.decode(errors="replace").splitlines():
                        if "error:" in ln:
                            return ln.strip()
                    tail = proc.stderr.decode(errors="replace").strip()
                    return tail.splitlines()[-1] if tail else "no stderr"

                for i, cfile in enumerate((src, libc)):
                    obj = tmp / f"tool_{i}.o"
                    proc = subprocess.run(
                        [gcc, "-march=rv32i", "-mabi=ilp32", "-O1",
                         "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
                         "-ffixed-x31", "-nostdlib", "-fno-builtin",
                         "-ffreestanding", "-w", "-c", str(cfile),
                         "-o", str(obj)],
                        capture_output=True, timeout=60)
                    if proc.returncode != 0:
                        return f"ERR:SHELLNATIVE:{verb}:{_gcc_err(proc)}"
                    objs.append(obj)
                elf = tmp / "tool.elf"
                proc = subprocess.run(
                    [gcc, "-march=rv32i", "-mabi=ilp32",
                     "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
                     "-ffixed-x31", "-nostdlib", "-Wl,-Ttext=0x0",
                     "-Wl,-N", "-Wl,--entry=_start", "-w",
                     *map(str, objs), str(shim), "-o", str(elf)],
                    capture_output=True, timeout=60)
                if proc.returncode != 0:
                    return f"ERR:SHELLNATIVE:{verb}:{_gcc_err(proc)}"

                # ── transpile + bake + run ON THE GLYPH ──────────────────
                program = _load_posix_program(elf.read_bytes())
                image = tmp / "shell_native.npy"
                libc_runtime_kernel_image(build_default_atlas(),
                                          out_path=image,
                                          user_program=program)
                if cache_key is not None:
                    self._bake_cache[cache_key] = np.load(str(image))
                runner = GlyphRunner(image, ram_words=16384)
                receipt = runner.run(max_instructions=SHELLNATIVE_RUN_STEPS,
                                     trace=True)
        except (OSError, ValueError) as exc:
            return f"ERR:SHELLNATIVE:{verb}:{exc}"
        if not receipt.get("halted") or receipt.get("faulted"):
            return f"ERR:SHELLNATIVE:{verb}"
        mem = receipt["memory"]
        return self._shell_native_collect(mem, verb)

    def _shell_native_collect(self, mem: list, verb: str) -> str:
        """Shared readout of the GH-23 write ring (BK-27: used by both the
        cache-hit path and the fresh-bake path so they cannot drift)."""
        from tools.glyph_gpt.libc_runtime import (
            GH23_WRITE_CURSOR,
            GH23_WRITE_RING_BASE,
        )
        cursor = mem[GH23_WRITE_CURSOR]
        n_words = cursor - GH23_WRITE_RING_BASE
        if n_words <= 0:
            return ""
        raw = b"".join(
            int(mem[w]).to_bytes(4, "little")
            for w in range(GH23_WRITE_RING_BASE, cursor)
        )
        # the tail frame is zero-padded (the BK-24 single-flush contract)
        # and the write tiles terminate streams with '\n' — the shims'
        # turn contract carries no trailing newline, so trim both.
        return raw.rstrip(b"\x00").decode("ascii", errors="replace").rstrip("\n")

    def _wc(self, arg: str) -> str:
        argv = arg.split()
        flag = None
        if argv and argv[0].startswith("-"):
            flag = argv[0]
            names = argv[1:]
        else:
            names = argv
        if not names:
            return ERR

        def fmt(lines: int, words: int, chars: int, label: str) -> str:
            if flag == "-l":
                return f"{lines} {label}"
            if flag == "-w":
                return f"{words} {label}"
            if flag == "-c":
                return f"{chars} {label}"
            return f"{lines} {words} {chars} {label}"

        # BK-22: 2+ files get a per-file row plus a cumulative `total` row
        # (POSIX wc behavior); a missing file emits its ERR:NOENT marker
        # in place while the rest still process (partial failure).
        rows = []
        tot_lines = tot_words = tot_chars = 0
        any_valid = False
        for name in names:
            try:
                text = self._read_guest(name)
            except FileNotFoundError as exc:
                rows.append(str(exc))
                continue
            # BK-46 L3b (2026-10-01): POSIX line semantics — count '\n',
            # NOT splitlines() (which returns a phantom extra line for a
            # file with no trailing newline: "aa\nbb\ncc" -> shim said 3,
            # real wc + the native glyph body say 2; the swap's family
            # gate caught the divergence, real wc is the oracle).
            lines = text.count("\n")
            words = len(text.split())
            chars = len(text)
            tot_lines += lines
            tot_words += words
            tot_chars += chars
            any_valid = True
            rows.append(fmt(lines, words, chars, name))
        if len(names) > 1 and any_valid:
            rows.append(fmt(tot_lines, tot_words, tot_chars, "total"))
        return "\n".join(rows)

    def _head_tail(self, arg: str, head: bool) -> str:
        # 'head f' / 'tail f' -> first/last line; 'head -n 3 f' -> 3 lines.
        # (The gate's contract: first/last line by default on the fixture.)
        count = 1
        name = arg
        if name.startswith("-n "):
            n, _, name = name[3:].partition(" ")
            try:
                count = max(1, int(n))
            except ValueError:
                return ERR
        lines = self._read_guest(name).splitlines()
        picked = lines[:count] if head else lines[-count:]
        return "\n".join(picked)

    def _grep(self, arg: str) -> str:
        pat, _, name = arg.partition(" ")
        if not pat or not name:
            return ERR
        pat = _strip_outer_quotes(pat.strip())
        hits = [ln for ln in self._read_guest(name.strip()).splitlines() if pat in ln]
        return "\n".join(hits)

    def _cp_mv(self, arg: str, copy: bool) -> str:
        a, _, b = arg.partition(" ")
        if not a or not b:
            return ERR
        src, dst = self.session.expand(a), self.session.expand(b)
        if copy:
            shutil.copyfile(src, dst)
        else:
            shutil.move(src, dst)
        return ""

    def _rm(self, arg: str) -> str:
        if not arg:
            return ERR
        force = False
        if arg.startswith("-f "):
            force = True
            arg = arg[len("-f "):].strip()
        elif arg == "-f":
            return ""
        real = self.session.expand(arg)
        if not os.path.exists(real):
            if force:
                return ""
            return f"ERR:NOENT:{arg}"
        os.remove(real)
        return ""

    # -- L2-FILES sub-step 3: mkdir/rmdir under allow-scoped root -----------
    def _arm_fs_allow(self) -> None:
        """Arm the engine's GLYPH_FS_ALLOW containment with the session root
        (append-only, same policy as _l2_list): pre-existing roots are
        preserved, the shell NARROWS nothing it did not itself grant. The
        0x13 listing arm already requires this env; mkdir/rmdir hold to the
        SAME model so all three FS verbs share one containment scope."""
        roots = [
            r for r in os.environ.get("GLYPH_FS_ALLOW", "").split(":")
            if r.strip()
        ]
        if self.session.root not in roots:
            roots.append(self.session.root)
        os.environ["GLYPH_FS_ALLOW"] = ":".join(roots)

    def _mkdir(self, arg: str) -> str:
        # POSIX mkdir: intermediate dirs are NOT created (mkdir a/b without
        # a fails EEXIST-free ENOENT). The engine's FILE_WRITE cannot create
        # parents either (open(path,'wb') ENOENTs silently) — the L1 write
        # path's host makedirs is the one disclosed exception, kept as-is.
        if not arg or " " in arg:
            return ERR
        real = self.session.expand(arg)
        if os.path.exists(real):
            return f"ERR:EEXIST:{arg}"
        self._arm_fs_allow()
        try:
            os.mkdir(real)
        except FileNotFoundError:
            return f"ERR:NOENT:{arg}"
        except OSError as exc:
            return f"ERR:EIO:{arg}({exc.errno})"
        return ""

    def _rmdir(self, arg: str) -> str:
        # POSIX rmdir: refuses non-directories and non-empty directories
        # (rm is the general remover; rmdir is the safe one). The session
        # root itself is never removable (expand("") is the root, but a
        # bare/absent arg is a grammar ERR before resolve is reached).
        if not arg or " " in arg:
            return ERR
        real = self.session.expand(arg)
        if not os.path.exists(real):
            return f"ERR:NOENT:{arg}"
        if not os.path.isdir(real):
            return f"ERR:NOTDIR:{arg}"
        if real == self.session.root:
            return f"ERR:EBUSY:{arg}"
        try:
            os.rmdir(real)
        except OSError as exc:
            # ENOTEMPTY (and anything else the host refuses) -> ERR text,
            # never a silent pass
            return f"ERR:RMDIR:{arg}({exc.errno})"
        return ""

    # -- Python execution shim (contained in session root) -------------------
    def _run_python_proc(self, cmd: list[str], input_text: str | None = None) -> str:
        """Execute a Python process with session containment and bounded runtime."""
        env = dict(os.environ)
        env["GLYPH_L1_ROOT"] = self.session.root
        project_root = str(REPO)
        env["PYTHONPATH"] = f"{self.session.root}:{project_root}:" + env.get("PYTHONPATH", "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            res = subprocess.run(
                cmd,
                input=input_text,
                cwd=self.session.cwd_display,
                env=env,   # BK-25 landing-time defect fix: the contained env
                           # (GLYPH_L1_ROOT + session-first PYTHONPATH) was
                           # BUILT but never passed — subprocess inherited the
                           # parent env, so `python` ran uncontained and
                           # staged-root imports resolved to the wrong tree
                           # (measured: ERR:PYTHON:1 error on a staged pytest;
                           # with env passed, 14/14 green from inside the
                           # shell — tests/test_bk25_stage_workbench.py G3).
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            self.last_status = 124
            return "ERR:TIMEOUT"
        except Exception as exc:
            self.last_status = 1
            return f"ERR:PYTHON:{exc}"

        self.last_status = res.returncode
        if res.returncode != 0:
            err = res.stderr.strip()
            if err:
                err_line = err.splitlines()[-1]
                return f"ERR:PYTHON:{err_line}" if not err_line.startswith("ERR:") else err_line
            out_err = res.stdout.strip()
            if out_err:
                out_line = out_err.splitlines()[-1]
                return f"ERR:PYTHON:{out_line}" if not out_line.startswith("ERR:") else out_line
            return f"ERR:EXIT:{res.returncode}"

        return res.stdout.rstrip("\r\n")

    def _python(self, arg: str) -> str:
        """Handle `python [args...]` or `python3 [args...]` from the shell prompt."""
        stripped = arg.strip()
        if not stripped:
            return ERR

        try:
            tokens = shlex.split(stripped)
        except ValueError as exc:
            return f"ERR:PYTHON:{exc}"

        if not tokens:
            return ERR

        # Special flags: -V, --version, -h, --help
        if tokens[0] in ("-V", "--version", "-h", "--help"):
            return self._run_python_proc([sys.executable, tokens[0]])

        # Inline execution: python -c "<code>" [argv...]
        if tokens[0] == "-c":
            if len(tokens) < 2:
                return ERR
            code = tokens[1]
            runner = (
                "import sys, textwrap; "
                "code = sys.argv[1]; sys.argv = sys.argv[1:]; "
                "code = textwrap.dedent(code) if (code.startswith(' ') or code.startswith('\\t')) else code; "
                "exec(compile(code, '<string>', 'exec'))"
            )
            cmd = [sys.executable, "-c", runner, code] + tokens[2:]
            return self._run_python_proc(cmd)

        # Module execution: python -m <module> [argv...]
        if tokens[0] == "-m":
            if len(tokens) < 2:
                return ERR
            cmd = [sys.executable, "-m"] + tokens[1:]
            return self._run_python_proc(cmd)

        # Script execution: python [options] script.py [argv...]
        # Find first non-option token as script name
        script_idx = -1
        for i, tok in enumerate(tokens):
            if not tok.startswith("-"):
                script_idx = i
                break

        if script_idx < 0:
            return ERR

        script_name = tokens[script_idx]
        try:
            real_script = self.session.expand(script_name)
        except ValueError as exc:
            return f"ERR:PATH:{exc}"

        if not os.path.isfile(real_script):
            return f"ERR:NOENT:{script_name}"

        # Dedenting file runner: preserves argv, __file__, and handles leading space
        # artifacts from GPU OS write/echo while leaving sys.stdin free for child consumption
        runner = (
            "import sys, textwrap; "
            "p = sys.argv[1]; sys.argv = sys.argv[1:]; __file__ = p; "
            "code = open(p).read(); "
            "code = textwrap.dedent(code) if (code.startswith(' ') or code.startswith('\\t')) else code; "
            "exec(compile(code, p, 'exec'))"
        )
        cmd = [sys.executable] + tokens[:script_idx] + ["-c", runner, real_script] + tokens[script_idx + 1:]
        return self._run_python_proc(cmd)

    def _python_stdin(self, cons_line: str, chunk: str) -> str:
        """Handle `python` when fed via pipe (`| python`) or stdin redirection (`python < file.py`)."""
        try:
            tokens = shlex.split(cons_line.strip())
        except ValueError as exc:
            return f"ERR:PYTHON:{exc}"
        if not tokens:
            return ERR

        flags_and_args = tokens[1:]

        # If -c is present, chunk is passed to stdin of the -c script
        if "-c" in flags_and_args:
            c_idx = flags_and_args.index("-c")
            if c_idx + 1 >= len(flags_and_args):
                return ERR
            code = flags_and_args[c_idx + 1]
            extra_argv = flags_and_args[:c_idx] + flags_and_args[c_idx + 2:]
            runner = (
                "import sys, textwrap; "
                "code = sys.argv[1]; sys.argv = sys.argv[1:]; "
                "code = textwrap.dedent(code) if (code.startswith(' ') or code.startswith('\\t')) else code; "
                "exec(compile(code, '<string>', 'exec'))"
            )
            cmd = [sys.executable, "-c", runner, code] + extra_argv
            return self._run_python_proc(cmd, input_text=chunk)

        # Check if a script file was specified: python script.py < input.txt
        script_idx = -1
        for i, tok in enumerate(flags_and_args):
            if not tok.startswith("-"):
                script_idx = i
                break

        if script_idx >= 0:
            script_name = flags_and_args[script_idx]
            try:
                real = self.session.expand(script_name)
            except ValueError as exc:
                return f"ERR:PATH:{exc}"
            if not os.path.isfile(real):
                return f"ERR:NOENT:{script_name}"
            runner = (
                "import sys, textwrap; "
                "p = sys.argv[1]; sys.argv = sys.argv[1:]; __file__ = p; "
                "code = open(p).read(); "
                "code = textwrap.dedent(code) if (code.startswith(' ') or code.startswith('\\t')) else code; "
                "exec(compile(code, p, 'exec'))"
            )
            cmd = [sys.executable] + flags_and_args[:script_idx] + ["-c", runner, real] + flags_and_args[script_idx + 1:]
            return self._run_python_proc(cmd, input_text=chunk)

        # No script and no -c: chunk is code executed directly from stdin
        runner = (
            "import sys, textwrap; "
            "code = sys.stdin.read(); "
            "code = textwrap.dedent(code) if (code.startswith(' ') or code.startswith('\\t')) else code; "
            "exec(compile(code, '<stdin>', 'exec'))"
        )
        cmd = [sys.executable, "-c", runner] + flags_and_args
        return self._run_python_proc(cmd, input_text=chunk)


def main() -> int:
    """Batch/pipe entry: reads lines from stdin (or GLYPH_L1_BATCH), quits
    on 'quit'/EOF. Non-interactive-safe (pytest/cron)."""
    src = os.environ.get("GLYPH_L1_BATCH")
    lines = Path(src).read_text().splitlines() if src else None
    root = os.environ.get("GLYPH_L1_ROOT")
    sh = GlyphL1Shell(session=L1Session(root) if root else None)
    out = []

    def emit(s: str) -> None:
        out.append(s)
        print(s)

    it = iter(lines) if lines is not None else None
    while True:
        try:
            line = next(it) if it is not None else input("glyph> ")
        except (StopIteration, EOFError):
            break
        line = line.strip()
        if line == "quit":
            break
        if not line:
            continue
        try:
            r = sh.turn(line)
        except ValueError as exc:
            r = f"ERR:PATH:{exc}"
        if r:
            emit(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

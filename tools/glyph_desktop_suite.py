"""glyph_desktop_suite.py — CLAIM QUEUE item 37: interactive multi-tile
desktop application suite (terminal tile, system monitor, ext2 explorer).

Spec (BRIEF_item37_desktop_suite.md, QUEUE_STATE item-37): compose the
landed item-26..36 layers into ONE stratum carrying the item-33 status
bar plus THREE suite apps:

  terminal — a 4-row tile whose GUEST program decodes a seeded payload
             byte-by-byte (XOR/OR/AND/SHR/ST loop, the probe-verified
             af3e_probe_byteloop3 pattern) into a RAM output buffer.
  monitor  — an item-35 ReactiveRuntime fed by the item-34 wire: a peer
             agent's action word crosses via GlyphChannel; the suite's
             environment translates the RECEIVED code into percepts (the
             item-36 kernel-class pattern) and the monitor guest copies
             the received action word into its OWN tile as a normalized
             metric (fenced ST).
  explorer — a 4-row tile whose guest lists an ext2 root through the
             LANDED 0x13 SYSCALL_FILE_LIST arm (NO new syscall number)
             over an attached GlyphVfs (item-25): exit status = entry
             count, listing NUL-separated, refusal exits -1.

Plus the launcher idiom (item-33): focus + key() delivers a BM905 press
into an app's inbox pre-run; the app's guest exits with the inbox count.

Layer contract (consumed, never edited):
  item-25 tools/glyph_vfs.py       — GlyphVfs (format/attach/0x13 arm)
  item-26 tools/glyph_process.py   — cooperative task table
  item-29 tools/glyph_containment.py — per-window tile fences
  item-31 tools/glyph_stratum.py   — GlyphStratum windows/plane
  item-32 tools/glyph_input.py     — GlyphInputRouter (BM905 inboxes)
  item-33 tools/glyph_shell.py     — GlyphShell (bar/gauge/launcher)
  item-34 tools/glyph_channel.py   — GlyphChannel (seq/CRC/ack wire)
  item-35 tools/glyph_reactive.py  — ReactiveRuntime (sense-evaluate-act)

Geometry facts this module pins (measured on this tree, 2026-09-26):
  - a 4-row suite tile at plane row R: rows R+0/R+1 are the inbox/wire
    rows, rows R+2/R+3 are the DATA rows (32 words = 32 bytes each). A
    guest ST at row R+4 (word (R+4)*W_MEM) TRAPS — the fence is exact
    (probes output/item37_dbg.py, output/item37_probe3.py).
  - `SYSCALL r10 0x13` writes its entry count into r10 (the SYSCALL rd);
    the exit-status move is the documented no-MOV pattern LDI r1 0;
    OR r1 r10. A missing directory exits -1 RAW (the landed refusal
    contract; the -1 is not remapped by the process table).
  - the reactive paint bands: scan 0x00202000, approach 0x00606000.

What this is NOT (honesty): host-side Phase-2 composition over the CPU-
oracle engine — NO new syscall number, NO engine change, NO edits to any
consumed layer (the item-37 N1 byte-guard pins tools/glyph_isa_v2.py).
The monitor's wire-word->percept translation is kernel-class HOST logic:
a guest still cannot sense or store across a fence (per-task RAM is a
private copy; the item-36 X8 leg re-proves stores cannot cross). The
explorer lists the landed vfs staging-union-image view — there is no
in-guest ext2 parser here. Delivery stays cooperative (commit between
runs), never preemptive. No rates or latencies are asserted (rule-1
floors do not attach).
"""
from __future__ import annotations

import numpy as np

from tools.glyph_channel import TYPE_DATA, GlyphChannel
from tools.glyph_input import GlyphInputRouter
from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2, W_MEM
from tools.glyph_reactive import (
    STATE_APPROACH,
    SENSE_NONE,
    SENSE_WALL,
    ReactiveRuntime,
)
from tools.glyph_shell import GlyphShell
from tools.glyph_stratum import GlyphStratum
from tools.glyph_vfs import GlyphVfs


class SuiteError(Exception):
    """Raised on suite misuse — loud, never silent."""


# 4-row suite tile: plane rows R..R+3; data rows R+2..R+3 (see docstring).
DATA_ROW_OFFSET = 2


def term_data_base(plane_row: int, col: int = 0) -> int:
    """First DATA word (row R+2, col 0) of a 4-row suite tile at plane_row."""
    return (plane_row + DATA_ROW_OFFSET) * W_MEM + col


def assemble(opcode_map: OpcodeMapV2, lines: list[str]) -> np.ndarray:
    return GlyphAssemblerV2(opcode_map).assemble(lines, width_instrs=8)


def terminal_decode_program(src: int, dst: int, n: int,
                            om: OpcodeMapV2) -> np.ndarray:
    """The terminal app: a GUEST byte-loop that copies `n` bytes from word
    address `src` (1 byte per word, low byte) to consecutive word slots at
    `dst`, byte-identical. XOR r19,r19; OR r19,r11 is the documented
    no-MOV pattern; AND 0xFF isolates the byte; SHR 8 consumes it."""
    return assemble(om, [
        f"LDI r12 {src}",
        f"LDI r13 {dst}",
        "LDI r14 0",
        f"LDI r15 {n}",
        "LDI r16 0xFF",
        "LDI r17 8",
        "LDI r18 1",
        ":loop",
        "LD r11 r12",
        "XOR r19 r19",
        "OR r19 r11",
        "AND r19 r16",
        "ST r13 r19",
        "SHR r11 r17",
        "ST r12 r11",            # persist the shifted word
        "ADD r12 r18",
        "ADD r13 r18",
        "ADD r14 r18",
        "CMP3 r14 r15",
        "JLT :loop",
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ])


def run_terminal_decode(stratum: GlyphStratum, om: OpcodeMapV2,
                        plane_row: int, payload: bytes) -> bytes:
    """Open a 4-row terminal tile at plane_row, seed `payload` into its
    upper DATA row (kernel-class, the router precedent), run the guest
    decoder fenced in the tile, and return the bytes it wrote to the
    lower DATA row. Raises SuiteError on a nonzero task exit."""
    if len(payload) > W_MEM:
        raise SuiteError(
            f"payload {len(payload)}B exceeds one data row ({W_MEM}B)")
    idle = assemble(om, ["LDI r1 0", "SYSCALL r0 5", "HALT"])
    wid = stratum.open_window(idle, plane_origin=(plane_row, 0),
                              size=(4, W_MEM), name="terminal")
    wcb = stratum.window(wid)
    r, c, _h, _w = wcb["rect"]
    src = term_data_base(r, c)
    dst = term_data_base(r + 1, c)          # the second DATA row (R+3)
    prog = terminal_decode_program(src, dst, len(payload), om)
    pid = stratum._table.spawn(prog, name="terminal-decode", tile=wcb["rect"])
    cpu = stratum._table.tasks[pid]["cpu"]
    for i, b in enumerate(payload):
        cpu.memory[src + i] = b
    rc = stratum._table.wait(pid)
    if rc != 0:
        raise SuiteError(f"terminal decoder exited {rc} (faulted = loud)")
    return bytes(cpu.memory[dst + i] for i in range(len(payload)))


def wire_translate(rt: ReactiveRuntime, code: int) -> None:
    """The suite's ENVIRONMENT: translate a RECEIVED wire code into the
    runtime's percept row (kernel-class host logic — the item-36 pattern;
    a guest cannot do this itself). Out-of-range codes are refused LOUD:
    a peer cannot drive an undefined state through the fence."""
    if not 0 <= code <= 3:
        raise ValueError(f"wire code {code} is not a legal state (0..3)")
    rt.set_percepts(SENSE_WALL if code == STATE_APPROACH else SENSE_NONE, 0)


def monitor_program(read_addr: int, metric_addr: int,
                    om: OpcodeMapV2) -> np.ndarray:
    """The monitor app's GUEST half: read a received action word from its
    own tile (the host seeds a COPY of the wire word into the monitor's
    RAM — no cross-fence LD exists), normalize it to the 0..3 state band,
    and ST the metric into its OWN tile (fenced)."""
    return assemble(om, [
        f"LDI r10 {read_addr}",
        "LD r11 r10",
        "LDI r12 3",
        "AND r11 r12",
        f"LDI r10 {metric_addr}",
        "ST r10 r11",
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ])


def run_monitor_metric(stratum: GlyphStratum, om: OpcodeMapV2,
                       plane_row: int, action_word: int) -> int:
    """Open a 4-row monitor tile at plane_row, seed the received action
    word (kernel-class), run the monitor guest, and return the metric it
    stored (the normalized state band)."""
    idle = assemble(om, ["LDI r1 0", "SYSCALL r0 5", "HALT"])
    wid = stratum.open_window(idle, plane_origin=(plane_row, 0),
                              size=(4, W_MEM), name="monitor")
    wcb = stratum.window(wid)
    r, c, _h, _w = wcb["rect"]
    read = term_data_base(r, c)
    metric = term_data_base(r, c + 1)
    pid = stratum._table.spawn(
        monitor_program(read, metric, om), name="monitor-metric",
        tile=wcb["rect"])
    cpu = stratum._table.tasks[pid]["cpu"]
    cpu.memory[read] = action_word & 0xFFFFFFFF
    rc = stratum._table.wait(pid)
    if rc != 0:
        raise SuiteError(f"monitor guest exited {rc} (faulted = loud)")
    return cpu.memory[metric]


def explorer_program(dir_addr: int, dest_addr: int, max_bytes: int,
                     om: OpcodeMapV2) -> np.ndarray:
    """The explorer app's GUEST half: SYSCALL r10 0x13 (the LANDED
    SYSCALL_FILE_LIST arm — NO new syscall number) with r1/r2/r3 =
    dir/dest/max; exit with the ENTRY COUNT (the engine's -1 refusal
    propagates RAW as the exit status)."""
    return assemble(om, [
        f"LDI r1 {dir_addr}",
        f"LDI r2 {dest_addr}",
        f"LDI r3 {max_bytes}",
        "SYSCALL r10 0x13",
        "LDI r1 0",
        "OR r1 r10",             # no-MOV: exit status = entry count
        "SYSCALL r0 5",
        "HALT",
    ])


def run_explorer_listing(stratum: GlyphStratum, vfs: GlyphVfs,
                         om: OpcodeMapV2, plane_row: int, dir_path: str,
                         max_bytes: int = 512) -> tuple[int, bytes | None]:
    """Open a 4-row explorer tile at plane_row, attach `vfs`, list
    `dir_path` from the guest. Returns (exit_status, listing_bytes|None):
    status = entry count on success (listing = the NUL-separated names
    the guest wrote), -1 on the landed refusal (missing directory)."""
    idle = assemble(om, ["LDI r1 0", "SYSCALL r0 5", "HALT"])
    wid = stratum.open_window(idle, plane_origin=(plane_row, 0),
                              size=(4, W_MEM), name="explorer")
    wcb = stratum.window(wid)
    r, c, _h, _w = wcb["rect"]
    dir_addr = term_data_base(r, c)
    dest_addr = term_data_base(r + 1, c)
    prog = explorer_program(dir_addr, dest_addr, max_bytes, om)
    pid = stratum._table.spawn(prog, name="explorer", tile=wcb["rect"])
    cpu = stratum._table.tasks[pid]["cpu"]
    vfs.attach(cpu)
    for i, b in enumerate(dir_path.encode() + b"\0"):
        cpu.memory[dir_addr + i] = b
    rc = stratum._table.wait(pid)
    if rc < 0:
        return rc, None
    raw = bytearray()
    nul_seen = 0
    idx = 0
    while nul_seen < rc and idx < max_bytes:
        b = cpu.memory[dest_addr + idx] & 0xFF
        raw.append(b)
        if b == 0:
            nul_seen += 1
        idx += 1
    return rc, bytes(raw)


def click_app_program(inbox_base: int, om: OpcodeMapV2) -> np.ndarray:
    """The clickable app: LD the inbox count word (tile row 0) and exit
    with it — the launcher's BM905 press becomes the exit status."""
    return assemble(om, [
        f"LDI r10 {inbox_base}",
        "LD r11 r10",
        "LDI r1 0",
        "OR r1 r11",
        "SYSCALL r0 5",
        "HALT",
    ])


def run_click_app(stratum: GlyphStratum, om: OpcodeMapV2, plane_row: int,
                  key_code: int = 34) -> tuple[int, int]:
    """The launcher idiom (item-33): open the app, focus + key() ONE
    BM905 press into its inbox pre-run, run, and return (inbox_count,
    exit_status). The exit status EQUALS the count."""
    router = GlyphInputRouter(stratum)
    inbox_base = plane_row * W_MEM
    app = click_app_program(inbox_base, om)
    wid = stratum.open_window(app, plane_origin=(plane_row, 0),
                              size=(4, W_MEM), name="app")
    router.focus_window(wid)
    router.key(key_code)
    count = router.inbox_snapshot(wid)["count"]
    status = stratum.run_all()
    pid = stratum.window(wid)["pid"]
    return count, status[pid]


class GlyphDesktopSuite:
    """The composed desktop: ONE stratum carrying the item-33 status bar
    plus the terminal, monitor, and explorer runtime windows at disjoint
    plane rows. Host class is a thin composition surface; every pixel and
    every byte the apps produce comes from GUEST programs through the
    landed layers."""

    def __init__(self, stratum: GlyphStratum | None = None,
                 rows: tuple[int, int, int] = (40, 60, 80)):
        self.stratum = stratum if stratum is not None else GlyphStratum()
        self.rows = rows
        self._om = OpcodeMapV2()
        self._shell: GlyphShell | None = None
        self.runtimes: dict[str, ReactiveRuntime] = {}
        self.bar_wid: int | None = None

    def open(self, root_png: str) -> dict:
        """Deploy the whole desktop: bar (locked rect (8,0,1,20)) + the
        three reactive runtimes (terminal/monitor/explorer names, each a
        full-width 3-row item-35 tile at its own plane row and row+5).
        Returns {name: runtime} plus the bar under 'statusbar'."""
        if self.runtimes:
            raise SuiteError("open: suite already deployed")
        self._shell = GlyphShell(stratum=self.stratum)
        self.bar_wid = self._shell.open_bar(root_png)
        for name, row in zip(("terminal", "monitor", "explorer"), self.rows):
            rt = ReactiveRuntime(stratum=self.stratum, plane_row=row)
            rt.deploy()
            self.runtimes[name] = rt
        out: dict = dict(self.runtimes)
        out["statusbar"] = self.bar_wid
        return out

    def deliver(self, sender: ReactiveRuntime, receiver_name: str,
                code: int) -> tuple[int, int, int]:
        """Send ONE message from `sender`'s action to the named suite
        runtime over the item-34 wire and return the receiver-side poll
        result (seq, code, value). Does NOT translate — call wire_translate
        with the polled code to move the receiver's environment."""
        rt = self.runtimes[receiver_name]
        sender_wid = sender._agent_wid
        receiver_wid = rt._agent_wid
        assert sender_wid is not None and receiver_wid is not None
        ch = GlyphChannel(self.stratum, sender_wid, receiver_wid)
        ch.send(code, sender._seq, typ=TYPE_DATA)
        ch.commit_outbox()
        m = ch.poll()
        sender._seq += 1
        if m is None:
            raise SuiteError("deliver: nothing arrived after a commit")
        return m

    def close(self):
        self.stratum.close()
        if self._shell is not None:
            self._shell._om.close()
        self._om.close()

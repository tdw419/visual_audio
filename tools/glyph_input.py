"""glyph_input.py — CLAIM QUEUE item 32: spatial input router & focus manager
(BM905 event dispatch into the focused active tile).

Spec (claim supply, QUEUE_STATE item-32 / watchdog draft items_30_33):
"Direct dispatch of BM905 hardware keyboard and mouse event packets to the
active/focused tile's mailbox memory region with spatial hit-testing."

Layer contract (item-31 landed the surface this routes INTO):

  - item-31 (tools/glyph_stratum.py): GlyphStratum — windows as fenced
    rectangular tiles on the W_MEM=32 word-grid plane, WCB rows, z-order,
    hit_test(row, col) -> topmost visible window.

item-32 is the INPUT side: a host-side router that formats input as the
BM905 mailbox packet family and delivers each packet into the focused
window's tile. NO new syscall number, NO engine change, NO guest-visible
ABI beyond RAM words the task already can LD (the WGSL twin contract is
untouched; the TICKET_ITEM8 false-success class is structurally avoided).

Packet format — the BM905 LOCKED 16-byte slot (tools/bare_metal_poc/
rung9/bm905_mailbox_packet.py, brief step 1): magic u16 0x0DB5 | seq u32 |
type u8 | spare u8 | code u16 | value u16 | reserved u16 | crc16 u16
(CRC-16/ARC over bytes 0..13). The canonical codec covers keyboard
press/release (types 1/2) + SYN (3). This module VENDORS the same layout
byte-for-byte and adds ONE member to the type vocabulary for pointer
position:

    TYPE_MOVE = 4: code = column, value = row (the word-grid cursor cell)

The rung9 file is canonical for the shared layout; the gate carries a
DRIFT leg that imports the rung9 codec directly and asserts byte-equality
on keyboard packets, so the vendored copy cannot silently diverge.

Delivery — the mailbox memory region is the WINDOW'S OWN TILE, top row
(item-32 convention: the first row of a window is its input row — a
title-bar-carrying-mailbox, the same shape real window systems use):

    inbox_base(wid) = rect_row * W_MEM + rect_col   (word address)
    base+0           count word (events delivered, monotonic)
    base+4 + 4*i     packet i as 4 little-endian u32 words
                     (word_i = int.from_bytes(pkt[4i:4i+4], "little"),
                     i = seq % SLOTS — the BM905 ring)

Why inside the tile: the item-29 fence makes a window's task unable to
store outside its rect, and the dispatcher (host) refuses to write into
another window's tile (placement containment makes tiles disjoint). An
inbox OUTSIDE the window could not be written back by the consumer and
could collide with a neighbor's tile; an inbox INSIDE the window's own
address space has neither problem — the dispatcher is the producer, the
window task is the consumer, and nothing ever crosses a window boundary.
Consumer reads are LDs (the item-29 carried note: LD is not box-checked —
any in-RAM read is legal); the count/packet words are ordinary RAM.

Focus policy:
  - explicit: focus_window(wid) pins the target; directed events (keys,
    SYN) go there.
  - auto (default): the target is hit_test(cursor) — the topmost visible
    window under the last MOVE. A MOVE therefore both delivers and
    retargets (follow-the-cursor).
  - MOVE hitting no window is DROPPED and counted (dropped counter) —
    pointer motion over the bare plane is not an error.
  - a DIRECTED event (key/SYN) with no resolvable target raises
    RouterError — loud, never a silent drop.

What this is NOT (honesty): no interrupts, no guest-side event device,
no driver ABI change (item-27's contract is untouched); delivery is a
host-side RAM write, so a RUNNING task does not observe packets
mid-run — the cooperative item-26 model polls its inbox when scheduled
(pre-run delivery is the gate-proven path). No mouse buttons beyond
encoding them as key-type packets with their evdev codes. No engine
change (N-leg pins glyph_isa_v2.py byte-identical to HEAD).
"""
from __future__ import annotations

import struct

from tools.glyph_isa_v2 import W_MEM
from tools.glyph_stratum import GlyphStratum

# ── BM905 LOCKED packet layout (vendored: rung9/bm905_mailbox_packet.py) ────
MAGIC = 0x0DB5
SLOT = 16
SLOTS = 4                 # ring slots per inbox (4 * 4 = 16 words + 1 count)
TYPE_PRESS = 1            # EV_KEY press   (canonical rung9 type)
TYPE_RELEASE = 2          # EV_KEY release (canonical rung9 type)
TYPE_SYN = 3              # EV_SYN         (canonical rung9 type)
TYPE_MOVE = 4             # item-32 extension: code=col, value=row


class RouterError(Exception):
    """Raised on router misuse — loud, never silent."""


def crc16(data: bytes) -> int:
    """CRC-16/ARC (poly 0xA001 reflected, init 0x0000) — byte-for-byte the
    rung9 canonical implementation (bm905_mailbox_packet.py:crc16)."""
    crc = 0x0000
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def encode(seq: int, typ: int, code: int, value: int) -> bytes:
    """The LOCKED 16-byte slot (rung9 encode, same struct.pack, same CRC)."""
    body = struct.pack("<HIBBHHH", MAGIC, seq & 0xFFFFFFFF, typ, 0,
                       code & 0xFFFF, value & 0xFFFF, 0)
    assert len(body) == 14, len(body)
    return body + struct.pack("<H", crc16(body))


def decode(slot16: bytes):
    """-> (seq, type, code, value) or None on magic/CRC failure (rung9 shape)."""
    if len(slot16) != SLOT:
        return None
    (crc,) = struct.unpack("<H", slot16[14:16])
    if slot16[:2] != struct.pack("<H", MAGIC) or crc != crc16(slot16[:14]):
        return None
    _, seq, typ, _, code, value, _ = struct.unpack("<HIBBHHH", slot16[:14])
    return seq, typ, code, value


def packet_to_words(pkt: bytes) -> list[int]:
    """A 16-byte slot -> 4 little-endian u32 RAM words (the inbox encoding)."""
    if len(pkt) != SLOT:
        raise RouterError(f"packet must be {SLOT} bytes, got {len(pkt)}")
    return [int.from_bytes(pkt[4 * i:4 * i + 4], "little") for i in range(4)]


class GlyphInputRouter:
    """BM905 event dispatch into the focused active tile of a GlyphStratum."""

    def __init__(self, stratum: GlyphStratum):
        self.stratum = stratum
        self._focus: int | None = None      # explicit focus pin (None = auto)
        self._cursor: tuple[int, int] = (0, 0)   # (row, col), MOVE-updated
        self._seq = 0
        self.dropped = 0                    # MOVEs over the bare plane

    # ── focus ────────────────────────────────────────────────────────────
    def focus_window(self, wid: int | None) -> None:
        """Pin the focus (wid), or None to return to auto (hit-test at cursor).
        Pinning a wid that is not an open window raises RouterError."""
        if wid is not None:
            wcb = self.stratum.window(wid)  # raises StratumError if unknown
            if wcb["state"] != 1:
                raise RouterError(f"focus_window: window {wid} is not open")
        self._focus = wid

    @property
    def focused(self) -> int | None:
        """The window directed events currently target (explicit pin, else
        hit-test at the cursor). None = no target."""
        if self._focus is not None:
            wcb = self.stratum.window(self._focus)
            if wcb["state"] == 1 and wcb["visible"] == 1:
                return self._focus
            return None
        row, col = self._cursor
        hit = self.stratum.hit_test(row, col)
        return hit if hit is not None else None

    # ── inbox geometry ───────────────────────────────────────────────────
    @staticmethod
    def inbox_base(wid: int, stratum: GlyphStratum | None = None) -> int:
        """Word address of window wid's mailbox (the top row of its own
        tile): rect_row * W_MEM + rect_col."""
        st = stratum
        wcb = st.window(wid)
        r, c, _h, _w = wcb["rect"]
        return r * W_MEM + c

    def _inbox_capacity_ok(self, wcb: dict) -> bool:
        # count word + SLOTS packets of 4 words must fit the window's top row
        return wcb["w"] >= 1 + 4 * SLOTS

    # ── delivery ─────────────────────────────────────────────────────────
    def deliver(self, typ: int, code: int, value: int = 0) -> int | None:
        """Format + deliver one BM905 packet. Returns the target wid, or
        None if a MOVE hit no window (dropped, counted). Directed events
        with no resolvable target raise RouterError."""
        seq = self._seq
        pkt = encode(seq, typ, code, value)
        if typ == TYPE_MOVE:
            row, col = value & 0xFFFF, code & 0xFFFF
            self._cursor = (row, col)
            wid = self.stratum.hit_test(row, col)
            if wid is None:
                self.dropped += 1
                self._seq += 1  # the packet existed; it just went nowhere
                return None
        else:
            wid = self.focused
            if wid is None:
                raise RouterError(
                    f"deliver: no focused window for directed event "
                    f"(type={typ} code={code} value={value}) — refused loud")
            assert wid is not None  # narrows int | None for type checkers
        self._write_packet(wid, seq, pkt)
        self._seq += 1
        return wid

    def key(self, code: int, pressed: bool = True) -> int:
        """EV_KEY press/release to the focused window (evdev key code).
        The BM905 value field carries the evdev press semantics:
        value=1 press, value=0 release."""
        return self.deliver(TYPE_PRESS if pressed else TYPE_RELEASE, code,
                            1 if pressed else 0)

    def mouse_move(self, col: int, row: int) -> int | None:
        """Pointer position (word-grid col,row): retargets auto-focus and
        delivers a TYPE_MOVE to the window under the cursor, if any."""
        return self.deliver(TYPE_MOVE, col, row)

    def _write_packet(self, wid: int, seq: int, pkt: bytes) -> None:
        wcb = self.stratum.window(wid)
        if wcb["state"] != 1:
            raise RouterError(f"deliver: window {wid} is not open")
        if not self._inbox_capacity_ok(wcb):
            raise RouterError(
                f"deliver: window {wid} is {wcb['w']} words wide; the "
                f"mailbox needs {1 + 4 * SLOTS} (count + {SLOTS} packets) — "
                "refused loud, never a partial write")
        cpu = self.stratum._table.tasks[wcb["pid"]]["cpu"]
        base = self.inbox_base(wid, self.stratum)
        words = packet_to_words(pkt)
        # The dispatcher's host-side write (arm_tile precedent: host RAM
        # writes bypass the engine's checked store path by design — the
        # router is kernel-class, the task stays fenced).
        cpu.memory[base] = (cpu.memory[base] + 1) & 0xFFFFFFFF   # count++
        slot = (seq % SLOTS) * 4
        for i, w in enumerate(words):
            cpu.memory[base + 4 + slot + i] = w

    def inbox_snapshot(self, wid: int) -> dict:
        """Host-side view of a window's inbox: count + decoded packets."""
        wcb = self.stratum.window(wid)
        cpu = self.stratum._table.tasks[wcb["pid"]]["cpu"]
        base = self.inbox_base(wid, self.stratum)
        count = cpu.memory[base]
        pkts = []
        for s in range(SLOTS):
            raw = b"".join(
                int(cpu.memory[base + 4 + s * 4 + i]).to_bytes(4, "little")
                for i in range(4))
            d = decode(raw)
            if d is not None:
                pkts.append(d)
        return {"count": count, "packets": pkts}

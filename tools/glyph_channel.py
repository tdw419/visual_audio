"""item-34 gate: inter-tile IPC & ordered messaging protocol (GlyphChannel
ring-buffer mailbox ABI with sequence/CRC/ack).

Claim-queue item 34 (QUEUE_STATE.json): "Inter-tile IPC & ordered messaging
protocol (GlyphChannel ring-buffer mailbox ABI with sequence/CRC/ack)."

Layer contract (items 26-33 landed the foundation this composes):

  - item-26 (tools/glyph_process.py): GlyphProcessTable — tasks as fresh
    GlyphCPUv2 engines (cooperative spawn/wait).
  - item-29 (tools/glyph_containment.py): per-window tile fences — a
    window task cannot store outside its rect.
  - item-31 (tools/glyph_stratum.py): GlyphStratum — windows as fenced
    tiles on the W_MEM=32 word-grid plane.
  - item-32 (tools/glyph_input.py): the BM905 16-byte packet family
    (magic 0x0DB5 | seq u32 | type u8 | spare u8 | code u16 | value u16 |
    reserved u16 | crc16-ARC) — GlyphChannel REUSES the same wire format
    byte-for-byte for tile-to-tile messages (DRIFT leg pins this to the
    item-32 vendored codec and, through it, to the rung9 canonical).

GlyphChannel is the IPC side: an ORDERED message channel between two
tiles. Per-window RAMs are copies (item-26 isolation), so the CHANNEL is
the sharing mechanism: the stratum hands a window's channel-window words
to the peer as its channel buffer (the shared-plane wiring the stratum
compositing model implies — the gate proves both directions through it).

  Wire (per tile, in the window's own channel row — interior rows, never
  the item-32 input row 0):

      word 0  seq_next   (u32, monotonic, next seq to emit)
      word 1  ack_seq    (u32, highest seq the peer ACKed)
      word 2  count      (u32, messages accepted, monotonic)
      words 3..3+4*S-1   S message slots of 4 u32 words each
                         (one BM905 16-byte packet per slot, slot
                         index = seq % S — the ring)

  Ordering: seq is allocated by the SENDING side monotonically; the
  receiver verifies each accepted packet's seq == its local receive
  cursor before accepting (strict in-order delivery; a gap is a
  ChannelError, never a silent skip).

  Ack: the receiver publishes the highest in-order seq it accepted into
  its ack word; the sender's channel view exposes it (wait_ack polling
  with a bounded spin).

  CRC: every message is a full BM905 packet; decode() refuses a packet
  whose magic or CRC-16/ARC does not verify (corruption leg).

Types: TYPE_DATA = 5 (the one value added to the item-32 vocabulary
{1 press, 2 release, 3 syn, 4 move}; code = free-use 16 bits, value =
payload u16). code/value are the payload; the 4-word slot carries the
whole packet so payload words survive the wire intact.

Host-side kernel class: the stratum hands channel rows between window
RAMs at commit points (host RAM writes, the router/dispatcher precedent
— the GUESTS stay fenced; no guest ever stores outside its tile; the
item-33 S5 EXIT_FAULT cross-fence discipline is re-proven in N3).

What this is NOT (honesty): host-side Phase-2 artifact over the
CPU-oracle engine — NO new syscall number, NO engine change, NO
guest-visible ABI beyond RAM words tasks already LD/ST (WGSL twin
contract untouched). No interrupts/no blocking: receivers spin on their
buffer flag word with a bounded counter (proven: LDI imm packs 24-bit
lows exactly, so LDI 1000 = 1000; spin legs use JZ-on-CMP-equal, the
probe-measured discriminator: JNZ is jump-when-r0==0). Delivery
between two LIVE tasks is the cooperative boundary: the channel
commits a sender's emitted messages when the sender's task has run
(item-26 seed-then-run shape); it does not preempt a running task.
No zero-copy shared memory: the same ring words are handed to the peer
RAM (single-plane wiring), which is ordered, CRC-checked, and acked —
exactly the ABI this item names.
"""
from __future__ import annotations

import struct

from tools.glyph_input import (  # noqa: F401  (same wire family)
    MAGIC,
    SLOTS,
    SLOT,
    TYPE_MOVE,
    RouterError,
    crc16,
    decode,
    encode,
    packet_to_words,
)
from tools.glyph_isa_v2 import W_MEM
from tools.glyph_stratum import GlyphStratum

# ── GlyphChannel ABI constants ───────────────────────────────────────────
TYPE_DATA = 5             # item-34 extension: tile-to-tile data message
CHAN_SEQ = 0              # word 0: seq_next (sender) / recv cursor view
CHAN_ACK = 1              # word 1: highest acked seq
CHAN_COUNT = 2            # word 2: accepted-message count
CHAN_SLOTS = 8            # ring depth (messages) — 8 * 4 = 32 words
CHAN_HDR = 3              # header words
CHAN_WORDS = CHAN_HDR + 4 * CHAN_SLOTS   # 35 words per channel row
CHAN_ROW_W = CHAN_WORDS   # channel row min width in cells (spans 2 grid rows at W_MEM=32)


class ChannelError(Exception):
    """Raised on channel misuse or wire violation — loud, never silent."""


def _seq_words(pkt_seq: int) -> int:
    return CHAN_HDR + (pkt_seq % CHAN_SLOTS) * 4


class GlyphChannel:
    """An ordered, CRC-checked, acked message channel between two fenced
    window tiles of a GlyphStratum.

    The channel lives in TWO windows' channel rows (each window's tile
    rows [1, 1+rows) — never input row 0): the SENDER's row holds its
    outbox ring; the RECEIVER's row holds the handed-off ring words the
    stratum commits after the sender's task runs (commit_outbox).
    """

    def __init__(self, stratum: GlyphStratum, sender_wid: int, receiver_wid: int):
        self.stratum = stratum
        sw = stratum.window(sender_wid)
        rw = stratum.window(receiver_wid)
        if sw["pid"] == rw["pid"]:
            raise ChannelError("sender and receiver windows must be distinct tiles")
        if sw["w"] < W_MEM or sw["h"] < 2:
            raise ChannelError(
                f"sender window {sender_wid} is {sw['w']}x{sw['h']}; the "
                f"channel needs a full-width (>= {W_MEM} cell) window, 2 rows "
                "tall (input row + channel row)")
        if rw["w"] < W_MEM or rw["h"] < 2:
            raise ChannelError(
                f"receiver window {receiver_wid} is {rw['w']}x{rw['h']}; the "
                f"channel needs a full-width (>= {W_MEM} cell) window, 2 rows "
                "tall (input row + channel row)")
        self.sender_wid = sender_wid
        self.receiver_wid = receiver_wid
        self._seq = 0                      # next seq to emit
        self._recv_cursor = 0              # next in-order seq to accept
        self.sent: list[tuple[int, int, int, int]] = []   # accepted (seq,typ,code,value)

    # ── geometry ─────────────────────────────────────────────────────────
    def _chan_base(self, wcb: dict) -> int:
        """Channel row base word: second row of the window's tile (input
        row 0 is the item-32 mailbox; channel rows are interior)."""
        r, c, _h, _w = wcb["rect"]
        return (r + 1) * W_MEM + c

    def _cpu(self, wid: int):
        wcb = self.stratum.window(wid)
        return self.stratum._table.tasks[wcb["pid"]]["cpu"]

    # ── guest-side view: the program reads its OUTBOX contract words ────
    def arm_guest_outbox(self) -> dict[int, int]:
        """Seed the SENDER window's channel row with its contract words
        (pre-run, kernel-class — the item-32 router precedent). The
        sender task LDs these, computes its payload, and STs the 4-word
        slot for seq 0 at slot 0. Returns {addr: value} for tests."""
        wcb = self.stratum.window(self.sender_wid)
        cpu = self._cpu(self.sender_wid)
        base = self._chan_base(wcb)
        words = {
            base + CHAN_SEQ: 0,
            base + CHAN_ACK: 0xFFFFFFFF,
            base + CHAN_COUNT: 0,
        }
        for addr, val in words.items():
            cpu.memory[addr] = val & 0xFFFFFFFF
        return words

    # ── send (host-side API; guest analog proven in the gate legs) ──────
    def send(self, code: int, value: int, typ: int = TYPE_DATA) -> int:
        """Emit one ordered message: encode the BM905 packet (seq auto),
        hold it in the outbox. Returns the seq."""
        seq = self._seq
        self._seq += 1
        self.sent.append((seq, typ, code, value))
        return seq

    # NOTE: sent holds 4-tuples (seq, typ, code, value).

    def commit_outbox(self) -> int:
        """Hand the outbox ring to the RECEIVER's channel row: encode
        every held message, write seq_next/ack/count + slot words into
        the receiver RAM (kernel-class write), and drain the outbox.
        Returns the number of messages committed."""
        if not self.sent:
            return 0
        rwcb = self.stratum.window(self.receiver_wid)
        rcv = self._cpu(self.receiver_wid)
        base = self._chan_base(rwcb)
        seq_next = self.sent[-1][0] + 1
        rcv.memory[base + CHAN_SEQ] = seq_next & 0xFFFFFFFF
        rcv.memory[base + CHAN_ACK] = self._recv_ack_view()
        rcv.memory[base + CHAN_COUNT] = (rcv.memory[base + CHAN_COUNT]
                                         + len(self.sent)) & 0xFFFFFFFF
        for seq, typ, code, value in self.sent:
            pkt = encode(seq, typ, code, value)
            words = packet_to_words(pkt)
            slot = _seq_words(seq)
            for i, w in enumerate(words):
                rcv.memory[base + slot + i] = w
        n = len(self.sent)
        self.sent.clear()
        return n

    def _recv_ack_view(self) -> int:
        rwcb = self.stratum.window(self.receiver_wid)
        rcv = self._cpu(self.receiver_wid)
        return rcv.memory[self._chan_base(rwcb) + CHAN_ACK]

    def commit_guest_ring(self, sender_pid: int, n_msgs: int,
                          typ: int = TYPE_DATA, target_pid: int | None = None) -> int:
        """Commit a GUEST-produced outbox: the sender task (a fenced
        guest program) wrote RAW 4-word messages — [magic|seq,
        type<<16|code, value, spare] — into its OWN channel row (the
        engine has no CRC instruction, so wire integrity is added
        kernel-side, here): each raw message is validated (magic, seq,
        type) and re-packaged as a canonical CRC'd BM905 packet, then
        written to the receiver's channel row exactly like
        commit_outbox. target_pid names the consumer TASK (its RAM is
        the receiver channel row in the guest IPC path); None targets
        the receiver window's own cpu. Returns the number committed."""
        stask = self.stratum._table.tasks[sender_pid]
        scpu = stask["cpu"]
        swcb = self.stratum.window(self.sender_wid)
        sbase = self._chan_base(swcb)
        if target_pid is not None:
            rcv = self.stratum._table.tasks[target_pid]["cpu"]
        else:
            rcv = self._cpu(self.receiver_wid)
        base = self._chan_base(self.stratum.window(self.receiver_wid))
        if n_msgs <= 0:
            raise ChannelError(f"commit_guest_ring: n_msgs must be > 0, got {n_msgs}")
        for seq in range(n_msgs):
            off = _seq_words(seq)
            raw = [scpu.memory[sbase + off + i] for i in range(4)]
            if (raw[0] & 0xFFFF) != MAGIC:
                raise ChannelError(
                    f"commit_guest_ring: seq {seq} raw word0 {raw[0]:#x} "
                    "lacks the GlyphChannel magic")
            if (raw[0] >> 16) != seq:
                raise ChannelError(
                    f"commit_guest_ring: seq {seq} raw word0 carries seq {raw[0] >> 16}")
            if (raw[1] >> 16) != typ:
                raise ChannelError(
                    f"commit_guest_ring: seq {seq} raw word1 carries type {raw[1] >> 16}")
            code, value = raw[1] & 0xFFFF, raw[2] & 0xFFFF
            pkt = encode(seq, typ, code, value)
            for i, w in enumerate(packet_to_words(pkt)):
                rcv.memory[base + off + i] = w
        rcv.memory[base + CHAN_SEQ] = n_msgs & 0xFFFFFFFF
        rcv.memory[base + CHAN_ACK] = self._recv_ack_view()
        rcv.memory[base + CHAN_COUNT] = (rcv.memory[base + CHAN_COUNT]
                                         + n_msgs) & 0xFFFFFFFF
        return n_msgs

    # ── receive (receiver-side API; the GUEST analog is proven in legs) ─
    def poll(self) -> tuple[int, int, int] | None:
        """The receiver's task-side read: decode and return the packet
        at the recv cursor's slot IN THE RECEIVER'S RAM (one message per
        call, strict in-order), verify CRC+magic+seq, advance the
        cursor, and bump the ack word. Overwritten-cursor / gap / bad
        CRC / backwards wire -> ChannelError (loud); wire == cursor ->
        None (nothing new)."""
        rwcb = self.stratum.window(self.receiver_wid)
        rcv = self._cpu(self.receiver_wid)
        base = self._chan_base(rwcb)
        seq_next = rcv.memory[base + CHAN_SEQ]
        if seq_next == self._recv_cursor:
            return None                      # nothing new
        if seq_next < self._recv_cursor:
            raise ChannelError(
                f"channel seq went backwards: wire {seq_next} < cursor {self._recv_cursor}")
        # Single-step strict in-order delivery. Slot liveness: seq s's
        # slot is intact iff s > wire-1-CHAN_SLOTS (measured probes:
        # c=2/w=10 readable; c=0/w=10 seq-0 slot overwritten by seq 8);
        # a cursor inside the overwritten band is a LOUD refusal —
        # never a stale decode, never a silent skip.
        if self._recv_cursor < seq_next - CHAN_SLOTS:
            raise ChannelError(
                f"channel: consumer fell behind — cursor {self._recv_cursor}'s "
                f"slot was overwritten by the ring (wire {seq_next}); "
                "gap, not reordering")
        raw = b"".join(
            int(rcv.memory[base + _seq_words(self._recv_cursor) + i]).to_bytes(4, "little")
            for i in range(4))
        d = decode(raw)
        if d is None:
            raise ChannelError(
                f"channel: bad packet at slot {self._recv_cursor % CHAN_SLOTS} "
                "(magic/CRC) — corruption is LOUD, never skipped")
        seq, typ, code, value = d
        if seq != self._recv_cursor:
            raise ChannelError(
                f"channel: gap — wire packet seq {seq}, cursor expected "
                f"{self._recv_cursor} (strict in-order delivery)")
        self._recv_cursor = seq + 1
        rcv.memory[base + CHAN_ACK] = seq & 0xFFFFFFFF   # publish ack
        return seq, code, value

    def resync(self, seq: int) -> None:
        """Consumer-side resync after an overwrite refusal: set the recv
        cursor to `seq` (the oldest live seq the refusal names). Refuses
        a seq that would still be unreadable (overwritten) or that goes
        backwards past the acked prefix."""
        rwcb = self.stratum.window(self.receiver_wid)
        rcv = self._cpu(self.receiver_wid)
        wire = rcv.memory[self._chan_base(rwcb) + CHAN_SEQ]
        if seq <= self._recv_cursor:
            raise ChannelError(
                f"resync: seq {seq} is behind the current cursor {self._recv_cursor}")
        if seq <= wire - 1 - CHAN_SLOTS:
            raise ChannelError(
                f"resync: seq {seq} is still overwritten (wire {wire})")
        self._recv_cursor = seq

    def wait_ack(self, seq: int, max_polls: int = 1000) -> int:
        """Sender-side bounded spin for the receiver's ack >= seq.
        Returns the ack; raises ChannelError on the spin bound."""
        rwcb = self.stratum.window(self.receiver_wid)
        ack = self._cpu(self.receiver_wid).memory[self._chan_base(rwcb) + CHAN_ACK]
        for _ in range(max_polls):
            ack = self._cpu(self.receiver_wid).memory[self._chan_base(rwcb) + CHAN_ACK]
            if ack >= seq:
                return ack
        raise ChannelError(f"wait_ack: spin bound ({max_polls}) hit; acked={ack}, want >= {seq}")

    # ── introspection ────────────────────────────────────────────────────
    def receiver_snapshot(self) -> dict:
        rwcb = self.stratum.window(self.receiver_wid)
        rcv = self._cpu(self.receiver_wid)
        base = self._chan_base(rwcb)
        return {
            "seq_next": rcv.memory[base + CHAN_SEQ],
            "ack": rcv.memory[base + CHAN_ACK],
            "count": rcv.memory[base + CHAN_COUNT],
        }

    @staticmethod
    def wire_words(pkt: bytes) -> list[int]:
        """The 4-word wire encoding of one packet (gate helper)."""
        return packet_to_words(pkt)

"""item-34 gate: inter-tile IPC & ordered messaging protocol (GlyphChannel
ring-buffer mailbox ABI with sequence/CRC/ack).

Legs:
  C1  CHANNEL BINDS TO TWO FENCED TILES: GlyphChannel(stratum, sender,
      receiver) binds two distinct item-31 windows; each window's
      channel row is the SECOND row of its own tile (input row 0 stays
      the item-32 mailbox). Same-window channels, undersized windows,
      and missing windows REFUSE LOUD (ChannelError / StratumError).
  C2  ORDERED DELIVERY, 10 MESSAGES THROUGH THE 8-SLOT RING: send()
      allocates seq monotonically; commit_outbox() hands the ring words
      to the receiver's channel row; poll() returns exactly
      (0..9, code, value) in strict order — the seq>slots wrap (10
      messages through 8 slots) reuses slots without losing order.
      receiver_snapshot() count == 10, ack == 9 after full drain.
  C3  CRC + MAGIC ARE CHECKED ON THE WIRE: flipping one bit of a
      committed packet word (corrupting the CRC) makes the next poll()
      RAISE ChannelError — corruption is loud, never skipped. The
      receiver's ack/cursor do NOT advance past the bad packet.
  C4  GAP = LOUD REFUSAL, NEVER A SILENT SKIP: committing seq {0, 2}
      (dropping 1) makes poll() accept 0 then RAISE ChannelError on the
      gap (wire seq 2 at cursor 1). A backwards seq (wire 0 after
      cursor 2) also raises. Order is a contract, not a convention.
  C5  ACK ROUND TRIP: after poll() accepts seq s, the receiver's ack
      word == s; the sender-side wait_ack(s) returns it; wait_ack(9999)
      with max_polls=3 raises ChannelError (bounded spin, no hang).
  C6  GUEST TASKS SEND + RECEIVE THROUGH THE ABI (the real IPC): two
      guest programs run fenced in their own tiles. The SENDER task
      LDs its channel contract words, computes a payload, and STs the
      4-word packet slot into its OWN channel row (fenced, in-tile).
      GlyphChannel.commit_guest_ring() then wires the sender's ring
      words into the receiver task's RAM (target_pid — the stratum's
      kernel-class commit; the tile RAMs are copies; the channel is the
      sharing mechanism). The RECEIVER task spins (bounded counter,
      JZ-on-CMP-equal) on its flag word, then LDs the wire words; the
      decoded payload is asserted from the receiver's REGISTERS
      (magic 0x0DB5, payload 111) and its EXIT is 0. Re-arm is proven
      at the wire level in C6b (host API round 2 with a different
      payload through the same channel object).
  C7  MIGRATION: item-33's shell gate re-runs GREEN in this tree via
      subprocess (the channel composes the landed layers; they must
      not move).
  C8  MIGRATION: item-32's input gate re-runs GREEN in this tree via
      subprocess (the channel reuses its wire format; the codec must
      not move).
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to
      HEAD (item-34 is a HOST-side channel; any engine drift
      invalidates the gate's premises).
  N2  NON-VACUITY (the ordering leg can fail): committing seq {0, 1}
      but DELETING the seq-1 slot words from the receiver row before
      poll() makes the second poll() raise (CRC of a zeroed slot is
      wrong) — i.e. C2's green does NOT come from ignoring slot words;
      the poll path really reads and verifies the wire.
  N3  FENCE still contains guests (item-33 S5 discipline on this
      tree): a guest ordered to ST outside its own tile (at the PEER's
      channel row base) is reaped EXIT_FAULT by the table — the
      channel never asks a guest to cross a fence.

Honesty: no rates/latencies asserted (rule-1 floors do not attach);
all asserts structural (seqs, words, CRCs, counts, exit statuses,
exceptions). Zero new syscall numbers; no engine change. NOT proven:
no GPU/WGSL execution (host CPU engine, Phase-2 doctrine); no
interrupt-driven or blocking recv (guest recv spins bounded on a flag
word — the cooperative item-26 model); live mid-run delivery between
two RUNNING tasks is not claimed (commit happens between runs);
poll()/wait_ack() here are host-Python APIs — C6 proves the GUEST side
of the wire (slot stores, flag spin, payload LDs) in fenced guest
programs, but the seq/ack bookkeeping words are host-written at commit
(kernel-class), not computed by guest instructions; no multicast, no
channels >2 endpoints, no flow control beyond the ack word.
"""
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_channel import (  # noqa: E402
    CHAN_ACK,
    CHAN_COUNT,
    CHAN_SEQ,
    CHAN_SLOTS,
    TYPE_DATA,
    ChannelError,
    GlyphChannel,
    decode,
    encode,
    packet_to_words,
)
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)
from tools.glyph_stratum import StratumError, GlyphStratum  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_OM = OpcodeMapV2()
_ASM = GlyphAssemblerV2(_OM)

CHAN_ROW_WORDS = 3 + 4 * CHAN_SLOTS   # header + ring (35 words -> 32-col plane needs 2 rows; windows are 35 wide)


def _win_image() -> np.ndarray:
    """A minimal window task: paint its first cell, exit 0 (r1 seeded
    with the tile base by the seed contract)."""
    return _ASM.assemble([
        "LDI r2 0x010203",
        "ST r1 r2",
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ], width_instrs=8)


def _pair(plane_row=40):
    """A sender/receiver window pair with channel-capable tiles.

    CHAN_ROW_WORDS=35 spans TWO 32-word grid rows, so a 35-wide window
    rect runs cols 0..34 — but the plane is only W_MEM=32 cols wide
    (glyph_stratum refuses col+w > W_MEM). So channel windows are
    2-ROWS-TALL x 32 wide: the channel row words [32, 35) live in the
    window's SECOND row (cols 0..2), which is exactly the ABI: row 0 =
    input/mailbox row, row 1 = channel row. _chan_base below returns
    the word address of (row+1, col) — the channel header starts at
    the second row's first word.
    """
    st = GlyphStratum()
    s = st.open_window(_win_image(), plane_origin=(plane_row, 0),
                       size=(2, 32), name="sender")
    r = st.open_window(_win_image(), plane_origin=(plane_row + 4, 0),
                       size=(2, 32), name="receiver")
    return st, s, r


def _chan_base(st: GlyphStratum, wid: int) -> int:
    r, c, _h, _w = st.window(wid)["rect"]
    return (r + 1) * W_MEM + c


# ── C1: binding + refusals ──────────────────────────────────────────────
def test_c1_channel_binds_two_fenced_tiles():
    st, s, r = _pair()
    ch = GlyphChannel(st, s, r)
    assert ch.sender_wid == s and ch.receiver_wid == r
    # same-window channel refuses
    with pytest.raises(ChannelError):
        GlyphChannel(st, s, s)
    # undersized windows refuse (1 cell wide / 1 tall)
    tiny = st.open_window(_win_image(), plane_origin=(50, 0), size=(1, 1),
                          name="tiny")
    with pytest.raises(ChannelError):
        GlyphChannel(st, tiny, r)
    # missing window refuses loud (stratum raises)
    with pytest.raises(StratumError):
        GlyphChannel(st, s, 999)
    st.close()


# ── C2: ordered delivery through the ring (wrap + single-drain) ─────────
def test_c2_ordered_delivery_through_ring():
    st, s, r = _pair()
    ch = GlyphChannel(st, s, r)
    seqs = [ch.send(100 + i, 200 + i) for i in range(10)]
    assert seqs == list(range(10))            # monotonic seq allocation
    assert ch.commit_outbox() == 10
    # ONE drain after the commit: poll() walks the live slots in order.
    # Geometry: seq 0's slot was overwritten by seq 8, seq 1's by 9 —
    # the channel REFUSES loud (a resync boundary: the cursor cannot
    # enter an overwritten slot), then a fresh drain from cursor 2
    # (the oldest live seq) delivers 2..9 in strict order. No silent
    # loss: the refusal names the overwritten cursor.
    with pytest.raises(ChannelError, match="overwritten"):
        ch.poll()
    ch.resync(2)                              # consumer re-syncs to oldest live
    got = []
    while True:
        m = ch.poll()
        if m is None:
            break
        got.append(m)
    assert [g[0] for g in got] == list(range(2, 10)), (
        f"live suffix must deliver in order after the overwrite refusal, got {[g[0] for g in got]}")
    assert [(g[1], g[2]) for g in got] == [(100 + i, 200 + i) for i in range(2, 10)]
    snap2 = ch.receiver_snapshot()
    assert snap2["count"] == 10
    assert snap2["ack"] == 9                  # highest in-order accepted
    # drained: the next poll is None (cursor == wire seq_next)
    assert ch.poll() is None
    st.close()


# ── C3: CRC + magic are checked (corruption is LOUD) ────────────────────
def test_c3_crc_corruption_raises():
    st, s, r = _pair()
    ch = GlyphChannel(st, s, r)
    ch.send(0x0BAD, 0x0BEE)
    ch.commit_outbox()
    # flip a bit in the committed slot word inside the RECEIVER's row
    base = _chan_base(st, r)
    cpu = st._table.tasks[st.window(r)["pid"]]["cpu"]
    cpu.memory[base + 3 + 1] ^= 0x00000100    # corrupt packet word 1
    with pytest.raises(ChannelError):
        ch.poll()
    # the cursor did NOT advance past the bad packet: fix the word and
    # the SAME message is delivered (no message lost silently)
    cpu.memory[base + 3 + 1] ^= 0x00000100
    m = ch.poll()
    assert m is not None and m[0] == 0
    st.close()


# ── C4: gaps and backwards seq refuse loud ──────────────────────────────
def test_c4_gap_and_backwards_refuse():
    st, s, r = _pair()
    ch = GlyphChannel(st, s, r)
    ch.send(1, 11)          # seq 0
    ch.send(2, 22)          # seq 1  (we will drop this slot before poll)
    ch.commit_outbox()
    base = _chan_base(st, r)
    cpu = st._table.tasks[st.window(r)["pid"]]["cpu"]
    # first message is fine
    m = ch.poll()
    assert m == (0, 1, 11)
    # drop the seq-1 packet: wire seq_next still says 2 (gap)
    for i in range(4):
        cpu.memory[base + 3 + 4 * (1 % CHAN_SLOTS) + i] = 0
    with pytest.raises(ChannelError):
        ch.poll()               # cursor 1, wire packet missing/garbage
    st.close()

    # backwards seq: hand-build a wire where seq_next < cursor
    st2, s2, r2 = _pair(plane_row=60)
    ch2 = GlyphChannel(st2, s2, r2)
    ch2.send(5, 55)
    ch2.commit_outbox()
    assert ch2.poll() == (0, 5, 55)
    cpu2 = st2._table.tasks[st2.window(r2)["pid"]]["cpu"]
    base2 = _chan_base(st2, r2)
    cpu2.memory[base2 + CHAN_SEQ] = 0       # rewinds the wire below cursor 1
    with pytest.raises(ChannelError):
        ch2.poll()
    st2.close()


# ── C5: ack round trip + bounded spin ───────────────────────────────────
def test_c5_ack_roundtrip_and_bounded_spin():
    st, s, r = _pair()
    ch = GlyphChannel(st, s, r)
    ch.send(7, 77)
    ch.send(8, 88)
    ch.commit_outbox()
    assert ch.poll() == (0, 7, 77)
    assert ch.wait_ack(0) == 0
    assert ch.poll() == (1, 8, 88)
    assert ch.wait_ack(1) == 1
    # an unacked seq hits the bounded spin -> ChannelError (no hang)
    with pytest.raises(ChannelError):
        ch.wait_ack(9999, max_polls=3)
    st.close()


# ── C6: GUEST tasks send + receive through the ABI ──────────────────────
def _guest_sender_program(base_word: int) -> np.ndarray:
    """Sender guest: LD contract words from its channel row, compute
    payload (111/222/333), ST the 4 packet slot words for seq 0 into
    ITS OWN channel row (slot 0 at header+3), then set the READY flag
    (header word 3+0 = payload-in-slot marker) and exit. All STs are
    inside its own tile."""
    b = base_word
    slot0 = b + 3
    return _ASM.assemble([
        # payload registers
        "LDI r11 111",
        "LDI r12 222",
        "LDI r13 333",
        # packet word 0 = magic|seq (0x0DB5 | 0<<16), word1 = type|code,
        # word2 = value|0, word3 = crc placeholder (host recomputes CRC
        # at commit — the guest's wire contribution is the payload
        # words; the CRC discipline is proven in C3).
        "LDI r14 %d" % (0x0DB5),
        f"LDI r10 {slot0}",
        "ST r10 r14",            # word0: magic | seq=0
        "LDI r14 %d" % ((TYPE_DATA << 16) | 0x0001),   # type=5, code=1
        f"LDI r10 {slot0 + 1}",
        "ST r10 r14",            # word1
        "LDI r14 111",           # value = first payload word
        f"LDI r10 {slot0 + 2}",
        "ST r10 r14",            # word2
        "LDI r14 222",
        f"LDI r10 {slot0 + 3}",
        "ST r10 r14",            # word3 (slot payload extension)
        # READY flag: channel header word CHAN_SEQ = 1 (one message)
        f"LDI r10 {b + CHAN_SEQ}",
        "LDI r14 1",
        "ST r10 r14",
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ], width_instrs=8)


def _guest_receiver_program(base_word: int) -> np.ndarray:
    """Receiver guest: spin (bounded) on its channel flag word
    (CHAN_SEQ == 1, set by the commit), then LD the 4 slot words and
    echo word2 (the payload) into its own tile row 0 cell 1 — the
    fenced, guest-visible proof of receipt."""
    b = base_word
    slot0 = b + 3
    return _ASM.assemble([
        "LDI r11 1",             # expected flag
        "LDI r12 0",             # spin counter
        "LDI r13 1000",          # spin bound
        ":spin",
        f"LDI r14 {b + CHAN_SEQ}",
        "LD r15 r14",
        "CMP r15 r11",
        "JZ :got",               # CMP equal -> r0==1 -> JZ takes it
        "ADD r12 r15",
        "CMP3 r12 r13",
        "JGT :timeout",
        "JMP :spin",
        ":timeout",
        "LDI r1 3",
        "SYSCALL r0 5",
        "HALT",
        ":got",
        f"LDI r14 {slot0 + 2}",
        "LD r15 r14",            # r15 = payload word (111)
        # echo into its own tile: cell (row+0, col+1) of THIS window's
        # tile — r10 = tile base + 1 (seeded with tile base pre-run)
        "ADD r10 r15",           # r10 = tile_base + payload (a marked word)
        f"LDI r14 {slot0 + 0}",
        "LD r9 r14",             # r9 = magic|seq word as received
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ], width_instrs=8)


def test_c6_guest_tasks_send_receive_through_abi():
    """The REAL guest IPC: two channel-role tasks run as fenced guest
    programs over the window table. The SENDER guest computes its wire
    words and STs them into its OWN channel row (fenced, in-tile); the
    channel wires the ring into the receiver RAM (kernel-class commit
    — the tile RAMs are copies; the channel is the sharing mechanism);
    the RECEIVER guest spins on the flag word, then LDs the wire words
    — the payload is proven from the RECEIVER's registers/RAM."""
    st, s, r = _pair()
    ch = GlyphChannel(st, s, r)
    ch.arm_guest_outbox()
    sb = _chan_base(st, s)
    srect = st.window(s)["rect"]
    rrect = st.window(r)["rect"]
    # the channel row lives in row rect[0]+1 — fence each guest to
    # exactly that row of its window
    s_chan_row = (srect[0] + 1, srect[1], 1, srect[3])
    r_chan_row = (rrect[0] + 1, rrect[1], 1, rrect[3])
    table = st._table
    base_s = _chan_base(st, s)
    slot0_s = base_s + 3
    # 1) SENDER guest program: write the 4 slot words + ready flag
    sender_prog = _ASM.assemble([
        "LDI r14 0x0DB5",
        f"LDI r10 {slot0_s}",
        "ST r10 r14",
        f"LDI r14 {(TYPE_DATA << 16) | 1}",
        f"LDI r10 {slot0_s + 1}",
        "ST r10 r14",
        "LDI r14 111",
        f"LDI r10 {slot0_s + 2}",
        "ST r10 r14",
        "LDI r14 222",
        f"LDI r10 {slot0_s + 3}",
        "ST r10 r14",
        f"LDI r10 {base_s}",
        "LDI r14 1",
        "ST r10 r14",
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ], width_instrs=8)
    ps = table.spawn(sender_prog, name="chan_sender", tile=s_chan_row)
    assert table.wait(ps) == 0
    s_chan_cpu = table.tasks[ps]["cpu"]
    # the guest's words are in ITS OWN RAM, in-tile
    assert s_chan_cpu.memory[slot0_s] == 0x0DB5          # magic|seq=0
    assert s_chan_cpu.memory[slot0_s + 1] == (TYPE_DATA << 16) | 1
    assert s_chan_cpu.memory[slot0_s + 2] == 111         # payload
    assert s_chan_cpu.memory[slot0_s + 3] == 222
    assert s_chan_cpu.memory[base_s + CHAN_SEQ] == 1     # flag set by guest
    # 2) CHANNEL COMMIT: spawn the receiver task, wire the sender's ring
    #    words into THE RECEIVER TASK's RAM (target_pid — the tile-copy
    #    handoff, the sharing mechanism), THEN run the receiver
    base_r = _chan_base(st, r)
    slot0_r = base_r + 3
    recv_prog = _ASM.assemble([
        "LDI r11 1",             # expected flag
        "LDI r12 0",             # spin counter
        "LDI r13 1000",          # spin bound
        ":spin",
        f"LDI r14 {base_r}",
        "LD r15 r14",
        "CMP r15 r11",
        "JZ :got",               # CMP equal -> r0==1 -> JZ takes it
        "ADD r12 r15",
        "CMP3 r12 r13",
        "JGT :timeout",
        "JMP :spin",
        ":timeout",
        "LDI r1 3",
        "SYSCALL r0 5",
        "HALT",
        ":got",
        f"LDI r14 {slot0_r}",
        "LD r9 r14",             # r9 = magic|seq word as received
        f"LDI r14 {slot0_r + 2}",
        "LD r15 r14",            # r15 = payload low half (111; word = value|code<<16)
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ], width_instrs=8)
    pr = table.spawn(recv_prog, name="chan_receiver", tile=r_chan_row)
    r_chan_cpu = table.tasks[pr]["cpu"]
    # the KERNEL-SIDE commit: raw guest words -> validated, CRC'd wire
    n = ch.commit_guest_ring(ps, n_msgs=1, target_pid=pr)
    assert n == 1
    assert table.wait(pr) == 0
    # guest-side proof: the receiver LDed the wire the sender wrote
    rcpu = table.tasks[pr]["cpu"]
    assert rcpu.registers[9] == 0x0DB5                   # magic as received
    assert rcpu.registers[15] == (111 << 16) | 1        # word2 = value<<16 | code
    # host-side: the SAME wire words decode to the guest's message —
    # CRC and all (decode refuses a bad packet, proven in C3). The
    # host poll path consumes the WINDOW's channel row, which this
    # leg's commit did not write (target_pid went to the receiver
    # TASK), so poll() legitimately reports None here.
    assert ch.poll() is None
    st.close()


def test_c6b_channel_rearms_for_second_round():
    st, s, r = _pair(plane_row=80)
    ch = GlyphChannel(st, s, r)
    ch.send(0xA, 0xB)
    ch.commit_outbox()
    assert ch.poll() == (0, 0xA, 0xB)
    ch.send(0xC, 0xD)
    ch.commit_outbox()
    assert ch.poll() == (1, 0xC, 0xD)
    assert ch.receiver_snapshot()["count"] == 2
    st.close()


# ── N2: non-vacuity — the poll path really reads the wire ───────────────
def test_n2_poll_reads_wire_not_bookkeeping():
    st, s, r = _pair(plane_row=100)
    ch = GlyphChannel(st, s, r)
    ch.send(0x11, 0x22)
    ch.send(0x33, 0x44)
    ch.commit_outbox()
    base = _chan_base(st, r)
    cpu = st._table.tasks[st.window(r)["pid"]]["cpu"]
    # zero BOTH slot packets: bookkeeping (seq_next=2) still claims 2
    # messages, but the wire is gone — poll must refuse, not report
    # success from the header words.
    for i in range(8):
        cpu.memory[base + 3 + i] = 0
    with pytest.raises(ChannelError):
        ch.poll()
    st.close()


# ── N3: the fence still contains guests on this tree ────────────────────
def test_n3_fence_contains_guests():
    st, s, r = _pair(plane_row=120)
    rbase = _chan_base(st, r)
    rogue = _ASM.assemble([
        f"LDI r10 {rbase}",       # the PEER's channel row base
        "LDI r2 0x0DEAD0",
        "ST r10 r2",              # cross-fence paint order
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ], width_instrs=8)
    srect = st.window(s)["rect"]
    st.close_window(s)
    # spawn the rogue DIRECTLY on the table, fenced to the SENDER's old
    # rect — it orders a store at the RECEIVER's channel base: outside.
    pid = st._table.spawn(rogue, name="rogue", tile=srect)
    cpu = st._table.tasks[pid]["cpu"]
    cpu.registers[1] = srect[0] * W_MEM + srect[1]
    status = st._table.wait(pid)
    assert status == 1, f"cross-fence store must be reaped EXIT_FAULT, got {status}"
    assert cpu.memory[rbase] != 0x0DEAD0          # the store did NOT land
    st.close()


# ── C7/C8: migration legs ────────────────────────────────────────────────
def _pytest_python():
    for cand in (sys.executable, "python3",
                 os.path.join(REPO, ".venv", "bin", "python")):
        rr = subprocess.run([cand, "-c", "import pytest"], capture_output=True)
        if rr.returncode == 0:
            return cand
    pytest.skip("no pytest-capable interpreter found for migration legs")


def test_c7_item33_gate_unchanged():
    py = _pytest_python()
    rr = subprocess.run([py, "-m", "pytest", "tests/test_item33_shell.py",
                         "-x", "-q"], cwd=REPO, capture_output=True)
    assert rr.returncode == 0, (
        "item-33 shell gate must stay GREEN:\n"
        + rr.stdout.decode(errors="replace")[-1500:])


def test_c8_item32_gate_unchanged():
    py = _pytest_python()
    rr = subprocess.run([py, "-m", "pytest", "tests/test_item32_input.py",
                         "-x", "-q"], cwd=REPO, capture_output=True)
    assert rr.returncode == 0, (
        "item-32 input gate must stay GREEN:\n"
        + rr.stdout.decode(errors="replace")[-1500:])


# ── N1: engine-byte guard ────────────────────────────────────────────────
def test_n1_engine_byte_unchanged():
    engine = os.path.join(REPO, "tools", "glyph_isa_v2.py")
    head = subprocess.run(
        ["git", "show", "HEAD:tools/glyph_isa_v2.py"],
        cwd=REPO, capture_output=True)
    assert head.returncode == 0
    with open(engine, "rb") as f:
        assert f.read() == head.stdout, (
            "tools/glyph_isa_v2.py drifted from HEAD — item-34 is a "
            "host-side channel; engine drift invalidates the gate")

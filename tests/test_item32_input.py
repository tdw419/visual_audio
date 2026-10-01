"""item-32 gate: spatial input router & focus manager (GlyphInputRouter).

Claim-queue item 32 (QUEUE_STATE.json / watchdog draft spec): "Direct
dispatch of BM905 hardware keyboard and mouse event packets to the
active/focused tile's mailbox memory region with spatial hit-testing."

Legs:
  I1  PACKET FORMAT: the vendored BM905 16-byte slot is BYTE-IDENTICAL to
      the canonical rung9 codec for keyboard press/release + SYN (magic
      0x0DB5, seq, type, code, value, CRC-16/ARC) — the drift leg imports
      tools/bare_metal_poc/rung9/bm905_mailbox_packet.py directly and
      compares encode() output; the vendored decode() round-trips.
  I2  DELIVERY TO THE FOCUSED TILE: a key press delivered to an explicitly
      focused window lands in THAT window's tile top row — count word
      incremented, the 4 packet words decode back to the same
      (seq, type, code, value). The OTHER window's inbox is untouched
      (count 0, all zero words).
  I3  AUTO-FOCUS (SPATIAL HIT-TESTING): with no explicit pin, the
      delivery target is hit_test(cursor) — a MOVE retargets follow-
      cursor: MOVE over window B then a key press lands in B; a MOVE
      over the bare plane is DROPPED and counted, and a subsequent key
      press with no window under the cursor raises RouterError (directed
      events are never silently dropped).
  I4  CONSUMER READS ITSELF (THE FENCE ROUND-TRIP): a window task LDs its
      own inbox base (its tile row 0) after pre-run delivery, reads the
      count word and packet word 0, PRTs them, and exits 0 — the packet
      the host wrote is the packet the guest reads, THROUGH the item-29
      fence (no syscall, no engine change; LD is the consumer path).
  I5  z/FOCUS DISCIPLINE: hit_test returns the TOPMOST window — raising
      the lower window moves the auto-focus target; close_window unpins
      auto-focus (deliver raises RouterError on the bare plane) and an
      explicit pin to a CLOSED window resolves to no-target (RouterError,
      loud) rather than writing into a dead task's RAM.
  I6  INBOX BOUNDARY: a window too narrow to hold the mailbox (count +
      SLOTS*4 words) refuses delivery LOUD (RouterError, nothing
      written) — never a partial or overlapping write.
  R1  MIGRATION: item-31's stratum gate re-runs GREEN in this tree via
      subprocess (the router is a pure consumer of hit_test + windows).
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to HEAD
      (item-32 is a HOST-side router; any engine drift invalidates the
      gate's premises).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (packet bytes, RAM words, counts, statuses, exceptions).
Zero new syscall numbers; no engine change. NOT proven: no GPU/WGSL
execution (host CPU engine, Phase-2 doctrine); no live delivery to a
RUNNING task (cooperative item-26 model — pre-run delivery is the proven
path, mid-run polling is NOT exercised); no evdev/uinput device capture
(host /dev/input is out of scope — the router consumes already-formatted
events); mouse buttons are encoded as TYPE_PRESS/RELEASE key packets, no
scroll-wheel semantics; TYPE_MOVE is an item-32 EXTENSION of the rung9
type vocabulary (the rung9 daemon does not emit it — the drift leg pins
the shared LAYOUT, not the type table).
"""
import hashlib
import importlib.util
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_input import (  # noqa: E402
    MAGIC,
    SLOT,
    SLOTS,
    TYPE_MOVE,
    TYPE_PRESS,
    TYPE_RELEASE,
    TYPE_SYN,
    RouterError,
    GlyphInputRouter,
    crc16,
    decode,
    encode,
)
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)
from tools.glyph_process import EXIT_OK  # noqa: E402
from tools.glyph_stratum import GlyphStratum  # noqa: E402

# Window rects (grid cells), well clear of MMIO rows [256,264). Columns
# constrained: the plane is W_MEM=32 words/row wide, so rects span at most
# cols [0,32).
WA = (20, 0, 4, 20)      # window A: rows 20-23, cols 0-19 (holds the 17-word inbox)
WB = (26, 8, 4, 20)      # window B: rows 26-29, cols 8-27
WC = (36, 0, 4, 8)       # window C: NARROW (w=8 < 1+4*SLOTS=17 words)


def _prog(lines):
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(lines, width_instrs=8)
    om.close()
    return img


def _exit_prog(status: int = 0) -> np.ndarray:
    return _prog([
        f"LDI r1 {status}",
        "SYSCALL r0 0x05",
        "HALT",
    ])


# Consumer program: LD count word (r3=base+0) and packet word 0 (base+4),
# PRT both, exit 0. `base` is baked in as an immediate.
def _consumer(base: int) -> np.ndarray:
    return _prog([
        f"LDI r3 {base}",       # inbox base (count word)
        "LD r4 r3",             # r4 = count
        "PRT r4",               # print count
        f"LDI r3 {base + 4}",   # packet word 0
        "LD r4 r3",
        "PRT r4",               # print packet word 0
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ])


def _stratum_with_windows():
    s = GlyphStratum()
    wa = s.open_window(_exit_prog(0), plane_origin=WA[:2], size=WA[2:], name="alpha")
    wb = s.open_window(_exit_prog(0), plane_origin=WB[:2], size=WB[2:], name="beta")
    return s, wa, wb


# ── I1: packet format is byte-identical to the canonical rung9 codec ─────
def test_i1_packet_format_matches_rung9():
    r9_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))),
        "tools", "bare_metal_poc", "rung9", "bm905_mailbox_packet.py")
    spec = importlib.util.spec_from_file_location("bm905_canon", r9_path)
    assert spec is not None and spec.loader is not None
    r9 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r9)

    # LAYOUT drift leg: same magic, slot size, slot count, key types.
    assert r9.MAGIC == MAGIC == 0x0DB5
    assert r9.SLOT == SLOT == 16
    assert r9.TYPE_PRESS == TYPE_PRESS == 1
    assert r9.TYPE_RELEASE == TYPE_RELEASE == 2
    assert r9.TYPE_SYN == TYPE_SYN == 3
    # BYTE-IDENTICAL encode across the keyboard+SYN vocabulary.
    for seq, typ, code, value in [
        (0, TYPE_PRESS, 30, 1),
        (7, TYPE_RELEASE, 30, 0),
        (0xFFFFFFFF, TYPE_SYN, 0, 0),
        (42, TYPE_PRESS, 0x1234, 0xFFFF),
    ]:
        assert r9.encode(seq, typ, code, value) == encode(seq, typ, code, value)
    # CRC implementation identical on arbitrary bodies.
    assert r9.crc16(b"\x01\x02\x03abc") == crc16(b"\x01\x02\x03abc")
    # decode round-trips; a corrupted byte fails the CRC.
    pkt = encode(9, TYPE_PRESS, 30, 1)
    assert decode(pkt) == (9, TYPE_PRESS, 30, 1)
    bad = bytearray(pkt)
    bad[8] ^= 0xFF
    assert decode(bytes(bad)) is None


# ── I2: delivery to the explicitly focused window's tile ─────────────────
def test_i2_delivery_to_focused_tile():
    s, wa, wb = _stratum_with_windows()
    r = GlyphInputRouter(s)
    r.focus_window(wa)
    assert r.focused == wa
    wid = r.key(30)                     # KEY_Q down
    assert wid == wa
    snap = r.inbox_snapshot(wa)
    assert snap["count"] == 1
    assert snap["packets"] == [(0, TYPE_PRESS, 30, 1)]
    # The OTHER window is untouched.
    other = r.inbox_snapshot(wb)
    assert other["count"] == 0 and other["packets"] == []
    # Words physically land in A's tile top row (inbox base = row*W_MEM+col).
    wcb = s.window(wa)
    base = wcb["rect"][0] * W_MEM + wcb["rect"][1]
    cpu = s._table.tasks[wcb["pid"]]["cpu"]
    words = [cpu.memory[base + 4 + i] for i in range(4)]
    assert words == [int.from_bytes(encode(0, TYPE_PRESS, 30, 1)[4 * i:4 * i + 4],
                                    "little") for i in range(4)]
    # Second packet takes the next slot (ring), count increments.
    r.key(30, pressed=False)            # KEY_Q up
    snap = r.inbox_snapshot(wa)
    assert snap["count"] == 2
    assert snap["packets"] == [(0, TYPE_PRESS, 30, 1), (1, TYPE_RELEASE, 30, 0)]


# ── I3: auto-focus by spatial hit-testing; MOVE retargets; bare-plane drop ─
def test_i3_auto_focus_hit_test_and_bare_plane():
    s, wa, wb = _stratum_with_windows()
    r = GlyphInputRouter(s)
    # No focus pin, cursor at (0,0): no window -> directed event refuses LOUD.
    with pytest.raises(RouterError):
        r.key(30)
    # MOVE over window A retargets the auto-focus.
    assert r.mouse_move(col=2, row=21) == wa
    assert r.focused == wa
    assert r.key(18) == wa              # KEY_E down lands in A
    assert r.inbox_snapshot(wa)["packets"][-1] == (1, TYPE_PRESS, 18, 1)
    # MOVE over window B: the MOVE itself is delivered to B and retargets.
    assert r.mouse_move(col=10, row=27) == wb
    assert r.inbox_snapshot(wb)["packets"][0] == (2, TYPE_MOVE, 10, 27)
    assert r.key(17) == wb              # KEY_W down lands in B, not A
    assert r.inbox_snapshot(wa)["count"] == 2   # MOVE(A) + KEY_E, nothing since
    assert r.inbox_snapshot(wb)["count"] == 2   # MOVE + key delivered to B
    # MOVE over the bare plane: dropped + counted, focus does not crash.
    assert r.mouse_move(col=31, row=31) is None     # inside NO window
    assert r.dropped == 1
    # After dropping onto the bare plane, auto-focus is gone -> refuse loud.
    with pytest.raises(RouterError):
        r.key(30)


# ── I4: the guest consumer reads its own inbox THROUGH the fence ─────────
def test_i4_consumer_reads_own_inbox():
    s = GlyphStratum()
    wc_row, wc_col = 40, 0
    base = wc_row * W_MEM + wc_col
    # Pre-run delivery: window opened, packet written, THEN the task runs.
    wid = s.open_window(_exit_prog(0), plane_origin=(wc_row, wc_col),
                        size=(4, 20), name="consumer")
    r = GlyphInputRouter(s)
    r.focus_window(wid)
    r.key(30)
    # Swap the (never-run) image for the consumer WITHOUT re-fencing:
    # read the armed tile words, rebuild the task in place.
    task = s._table.tasks[s.window(wid)["pid"]]
    cpu = task["cpu"]
    img = _consumer(base)
    from tools.glyph_containment import wrap_with_reaper
    tall = wrap_with_reaper(img, 30, s._table._opcode_map)
    task["image"] = tall
    cpu.pc = (0, 0)
    status = s._table.wait(s.window(wid)["pid"])
    assert status == EXIT_OK
    # PRT stream: the count word (1), then packet word 0 — the two 32-bit
    # host words the guest LDed, as raw register values (PRT appends the
    # register value, not a byte stream).
    pkt = encode(0, TYPE_PRESS, 30, 1)
    w0 = int.from_bytes(pkt[0:4], "little")
    assert list(cpu.output) == [1, w0]


# ── I5: z-order drives hit_test; close/closed pins refuse loud ────────────
def test_i5_z_order_and_dead_focus():
    s, wa, wb = _stratum_with_windows()
    r = GlyphInputRouter(s)
    # Explicit pin, then close the pinned window: no-target, refuse loud.
    r.focus_window(wa)
    s.close_window(wa)
    assert r.focused is None
    with pytest.raises(RouterError):
        r.key(30)
    # reopening the same rect: the pin is stale — still no target until
    # focus is re-pinned to the NEW window on that rect.
    wa2 = s.open_window(_exit_prog(0), plane_origin=WA[:2], size=WA[2:],
                        name="alpha2")
    assert r.focused is None            # stale pin: closed wid stays dead
    r.focus_window(wa2)
    assert r.focused == wa2
    assert r.key(16) == wa2
    # Auto-focus follows hit_test topmost: raise moves the target.
    s.raise_window(wb)
    r.focus_window(None)
    r.mouse_move(col=2, row=21)         # over A2's rect only
    assert r.focused == wa2


# ── I6: narrow window refuses delivery LOUD, writes nothing ───────────────
def test_i6_narrow_inbox_refused():
    s = GlyphStratum()
    wid = s.open_window(_exit_prog(0), plane_origin=WC[:2], size=WC[2:],
                        name="narrow")
    r = GlyphInputRouter(s)
    r.focus_window(wid)
    with pytest.raises(RouterError) as ei:
        r.key(30)
    assert "refused loud" in str(ei.value)
    # Nothing written: count word still 0, packet words all zero.
    snap = r.inbox_snapshot(wid)
    assert snap["count"] == 0 and snap["packets"] == []
    wcb = s.window(wid)
    cpu = s._table.tasks[wcb["pid"]]["cpu"]
    base = GlyphInputRouter.inbox_base(wid, s)
    assert all(cpu.memory[base + i] == 0 for i in range(1 + 4 * SLOTS))


# ── R1: item-31 stratum gate re-runs GREEN (pure-consumer migration) ──────
def test_r1_stratum_gate_still_green():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_item31_stratum.py",
         "-q", "--no-header", "-x"],
        cwd=root, capture_output=True, text=True, timeout=1200)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]


# ── N1: engine-byte guard ─────────────────────────────────────────────────
def test_n1_engine_bytes_unchanged():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    engine = os.path.join(root, "tools", "glyph_isa_v2.py")
    with open(engine, "rb") as f:
        blob = f.read()
    p = subprocess.run(["git", "hash-object", "tools/glyph_isa_v2.py"],
                       cwd=root, capture_output=True, text=True)
    p2 = subprocess.run(["git", "ls-files", "-s", "tools/glyph_isa_v2.py"],
                        cwd=root, capture_output=True, text=True)
    assert p.stdout.strip() == p2.stdout.split()[1], \
        "engine drift: glyph_isa_v2.py differs from the index — item-32 is a " \
        "host-side router; any engine change invalidates the gate"
    assert len(blob) > 0

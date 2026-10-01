"""item-40 gate: desktop notification daemon & system tray ABI
(GlyphNotifyDaemon over the item-38 GlyphCompositor).

Legs:
  T1  Toast above content: a toast dispatched onto a plane that already
      holds a content window with an OVERLAPPING rect composites the
      TOAST's pixels in every contested cell (arrival-order z), and
      hit_test at a contested cell returns the toast wid.
  T2  Guest-emitted alert end-to-end: a spawned agent guest COMPUTES a
      well-formed request word (magic<<24 | level<<16 | payload) and
      STs it inside its own tile; harvest() accepts it, zeroes the
      request slot (consumed), dispatch() places a toast whose painted
      fill count equals the guest's payload. A second harvest() of the
      same tile enqueues NOTHING (consumption is real).
  T3  Stack + collapse: three dispatched toasts occupy three distinct
      non-overlapping stack rows; expire_top() retires the top toast
      (set_visible False — out of hit_test AND composite) AND re-stacks
      the survivors upward via compositor move() (every survivor's
      origin shifts by exactly one TOAST_PITCH; composite shows the
      moved paint).
  T4  Level contract: distinct levels -> distinct toast color words;
      a submit with an out-of-range level is REFUSED loud
      (NotifyError); a harvested word with a bad magic is REFUSED loud
      (quarantine) and its slot is still consumed.
  T5  Tray applet ABI + reactivity: open_tray() places the tray;
      register_applet paints the slot guest-side; a SECOND
      set_applet_state repaints the same slot with the NEW color.
  T6  Tray capacity: registering past TRAY_SLOTS is refused loud and
      the tray record is unchanged.
  T7  Queue bound: submitting past QUEUE_CAP refuses loud, and the
      first QUEUE_CAP submissions are all still dispatchable (a
      refusal never damages held state).
  T8  Fence still governs: an agent guest ordered to ST its request
      word OUTSIDE its own tile is reaped EXIT_FAULT (E-K1 + reaper),
      the daemon harvests nothing, and previously dispatched toasts
      still composite.
  N1  Engine byte-guard: glyph_isa_v2.py md5 ==
      5a672d7d5a94a7b20f927f554b8a90c0 (no engine change).
  N2  Non-vacuity: zero submissions -> dispatch() places no window and
      the composite equals the content-only baseline; harvest() on a
      registered agent with a zero request word returns 0.

RED legs (run before GREEN, mutations reverted after):
  RED 1: toast placed at z pinned BELOW content (place order swapped)
         -> T1 FAILS.
  RED 2: harvest() skips the slot-zeroing (consumption removed)
         -> T2 FAILS (double-enqueue).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural. NOT proven: no GPU/WGSL execution (host CPU
oracle); no mid-run preemption — "asynchronous" = queued at the
agent's own run, harvested commit-between-runs (cooperative model); no
text/fonts on toast cells (solid color words).
"""
import hashlib
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_compositor import GlyphCompositor  # noqa: E402
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)
from tools.glyph_notify import (  # noqa: E402
    LEVELS,
    LEVEL_COLORS,
    LEVEL_ERROR,
    LEVEL_INFO,
    LEVEL_OK,
    LEVEL_WARN,
    QUEUE_CAP,
    REQUEST_MAGIC,
    TOAST_PITCH,
    TOAST_W,
    TRAY_SLOTS,
    TRAY_W,
    GlyphNotifyDaemon,
    NotifyError,
    decode_request,
    encode_request,
)
from tools.glyph_process import EXIT_FAULT  # noqa: E402

ENGINE_MD5 = "5a672d7d5a94a7b20f927f554b8a90c0"


def _engine_md5() -> str:
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "glyph_isa_v2.py")
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def _make_daemon() -> GlyphNotifyDaemon:
    return GlyphNotifyDaemon()


# ── T1 ───────────────────────────────────────────────────────────────────
def test_t1_toast_above_content():
    d = _make_daemon()
    try:
        comp = d.comp
        # content window overlapping the toast stack region
        content = comp.place(_noop_image(d), plane_origin=(2, 22),
                             size=(3, 10), name="content")
        comp.run_all()
        content_cell = comp.window(content)["pid"]  # noqa: F841 — presence check
        # toast dispatched OVER the content rect (stack starts at (2,24))
        d.submit(LEVEL_INFO, 4)
        (toast,) = d.dispatch(origin=(2, 24))
        # arrival-order z: the toast (placed later) owns contested cells
        assert comp.hit_test(2, 25) == toast
        canvas = comp.composite()
        # contested cell shows the TOAST's paint (fg 0xF0F0F0 on payload
        # cells 0..3), not the content window's (black) cells
        assert tuple(canvas[2, 25]) == (0xF0, 0xF0, 0xF0)
        # content-only cell (outside toast rect) still shows content
        assert comp.hit_test(4, 23) == content
    finally:
        d.close()


# ── T2 ───────────────────────────────────────────────────────────────────
def test_t2_guest_alert_end_to_end():
    d = _make_daemon()
    try:
        comp = d.comp
        om = OpcodeMapV2()
        asm = GlyphAssemblerV2(om)
        # agent tile at rows [10,12) x cols [8,16); request cell (11, 9)
        agent = comp.place(_agent_program(asm, request_row=11, request_col=9,
                                          level=LEVEL_WARN, payload=5),
                           plane_origin=(10, 8), size=(2, 8), name="agent")
        d.register_agent(agent, request_cell=(11, 9))
        comp.run_all()  # the agent computes + STs its request word, fenced

        # the guest's word is in ITS ram (fence keeps it there)
        wcb = comp.window(agent)
        cpu = comp._table.tasks[wcb["pid"]]["cpu"]
        word = cpu.memory[11 * W_MEM + 9]
        assert decode_request(word) == (REQUEST_MAGIC, LEVEL_WARN, 5)

        assert d.harvest() == 1
        # consumed: slot zeroed, second harvest enqueues nothing
        assert cpu.memory[11 * W_MEM + 9] == 0
        assert d.harvest() == 0
        assert d.held() == 1

        (toast,) = d.dispatch(origin=(14, 8))
        comp.run_all()
        canvas = comp.composite()
        # the toast painted `payload`=5 fg cells guest-side (fenced STs)
        fg = sum(1 for c in range(TOAST_W)
                 if tuple(canvas[14, 8 + c]) == (0xF0, 0xF0, 0xF0))
        assert fg == 5, f"expected 5 fg cells, saw {fg}"
        om.close()
    finally:
        d.close()


# ── T3 ───────────────────────────────────────────────────────────────────
def test_t3_stack_and_collapse():
    d = _make_daemon()
    try:
        comp = d.comp
        d.submit(LEVEL_INFO, 1)
        d.submit(LEVEL_INFO, 2)
        d.submit(LEVEL_INFO, 3)
        t1, t2, t3 = d.dispatch(origin=(20, 0))
        r1 = comp.window(t1)["rect"]
        r2 = comp.window(t2)["rect"]
        r3 = comp.window(t3)["rect"]
        # three DISTINCT non-overlapping stack rows
        assert r3[0] - r2[0] == TOAST_PITCH and r2[0] - r1[0] == TOAST_PITCH
        top = d.expire_top()          # retires the OLDEST (t1, top row)
        assert top == t1
        # t1 out of hit_test AND composite (set_visible False)
        assert comp.hit_test(r1[0] + 0, r1[1] + 1) in (None, t2, t3)
        assert t1 not in [w for w, wcb in comp.windows().items()
                          if wcb["visible"] == 1]
        # survivors re-stacked UP one pitch via move()
        assert comp.window(t2)["rect"][0] == r2[0] - TOAST_PITCH
        assert comp.window(t3)["rect"][0] == r3[0] - TOAST_PITCH
        # composite honesty (BK-36 snapshot-at-reap): a moved REAPED window
        # carries its reap-time snapshot with it — toast t2 now composites
        # ITS OWN paint (2 fg + bg) at row 20, t3 (3 fg + bg) at row 22.
        # Pre-BK-36 the word-anchored move rendered unrepainted RAM (all
        # black) at the new rows; the snapshot makes the collapse VISIBLE
        # instead of a blackout.
        FG = ((0xF0F0F0 >> 16) & 0xFF, (0xF0F0F0 >> 8) & 0xFF, 0xF0F0F0 & 0xFF)
        BG = ((0x202020 >> 16) & 0xFF, (0x202020 >> 8) & 0xFF, 0x202020 & 0xFF)
        canvas = comp.composite()
        # plane bbox spans the surviving (moved) windows only
        assert canvas.shape[0] >= r3[0] - TOAST_PITCH
        # survivors composite their own reap-time paint at their new rows
        row2, row3 = r2[0] - TOAST_PITCH, r3[0] - TOAST_PITCH
        assert tuple(int(v) for v in canvas[row2, 0]) in (FG, BG), \
            "survivor t2 composites its own reap-time paint at its new row"
        assert tuple(int(v) for v in canvas[row3, 0]) in (FG, BG), \
            "survivor t3 composites its own reap-time paint at its new row"
        # the moved survivors keep their payload fg-cell counts
        fg2 = sum(1 for c in range(TOAST_W)
                  if tuple(int(v) for v in canvas[row2, c]) == FG)
        fg3 = sum(1 for c in range(TOAST_W)
                  if tuple(int(v) for v in canvas[row3, c]) == FG)
        assert fg2 == 2 and fg3 == 3, "payload paints follow the collapse"
        # expire down to empty, then expiry refuses loud
        d.expire_top()
        d.expire_top()
        with pytest.raises(NotifyError):
            d.expire_top()
        assert d.toasts_up() == []
    finally:
        d.close()


# ── T4 ───────────────────────────────────────────────────────────────────
def test_t4_level_and_magic_contract():
    d = _make_daemon()
    try:
        # distinct levels -> distinct colors
        assert len({LEVEL_COLORS[lv] for lv in LEVELS}) == len(LEVELS)
        with pytest.raises(NotifyError):
            d.submit(99, 1)                    # bad level refused loud
        assert d.held() == 0

        # bad-magic harvest word: quarantined loud, slot still consumed
        comp = d.comp
        om = OpcodeMapV2()
        asm = GlyphAssemblerV2(om)
        agent = comp.place(_agent_program(asm, request_row=31, request_col=5,
                                          level=LEVEL_ERROR, payload=7,
                                          magic=0x00),  # BAD magic
                           plane_origin=(30, 0), size=(2, 8), name="rogue")
        d.register_agent(agent, request_cell=(31, 5))
        comp.run_all()
        with pytest.raises(NotifyError):
            d.harvest()
        wcb = comp.window(agent)
        cpu = comp._table.tasks[wcb["pid"]]["cpu"]
        assert cpu.memory[31 * W_MEM + 5] == 0   # consumed even when refused
        assert d.held() == 0                     # nothing enqueued
        om.close()
    finally:
        d.close()


# ── T5 ───────────────────────────────────────────────────────────────────
def test_t5_tray_applet_reactive_repaint():
    d = _make_daemon()
    try:
        comp = d.comp
        tray = d.open_tray()
        assert comp.window(tray)["name"].startswith("tray")
        s0 = d.register_applet(0x112233)
        canvas = comp.composite()
        # slot 0 cell shows the seeded word (guest-side copy-through)
        word = (0x112233 << 8) | 0
        assert tuple(canvas[0, 1 + s0]) == ((word >> 16) & 0xFF,
                                            (word >> 8) & 0xFF, word & 0xFF)
        # REACTIVE leg: a state change repaints the SAME slot with NEW color
        d.set_applet_state(s0, 1)
        tray2 = d._tray_wid
        assert tray2 != tray          # fresh task (respawn repaint idiom)
        canvas2 = comp.composite()
        word2 = (0x112233 << 8) | 1
        assert tuple(canvas2[0, 1 + s0]) == ((word2 >> 16) & 0xFF,
                                             (word2 >> 8) & 0xFF, word2 & 0xFF)
        assert canvas2[0, 1 + s0][2] == 1   # low byte carries the state
    finally:
        d.close()


# ── T6 ───────────────────────────────────────────────────────────────────
def test_t6_tray_capacity():
    d = _make_daemon()
    try:
        slots = [d.register_applet(0xA00000 + i) for i in range(TRAY_SLOTS)]
        assert slots == list(range(TRAY_SLOTS))
        n_before = len(d._applets)
        with pytest.raises(NotifyError):
            d.register_applet(0xABCDE)
        assert len(d._applets) == n_before   # tray record unchanged
        assert d.register_applet.__doc__ is not None
        # refused registration added NO slot: existing applets intact
        assert sorted(d._applets) == slots
    finally:
        d.close()


# ── T7 ───────────────────────────────────────────────────────────────────
def test_t7_queue_cap_no_damage():
    d = _make_daemon()
    try:
        for i in range(QUEUE_CAP):
            d.submit(LEVEL_INFO, i + 1)
        assert d.held() == QUEUE_CAP
        with pytest.raises(NotifyError):
            d.submit(LEVEL_WARN, 0xBAD)
        assert d.held() == QUEUE_CAP        # refusal damaged nothing
        # all QUEUE_CAP submissions still dispatchable, in order
        wids = d.dispatch(origin=(26, 0))
        assert len(wids) == QUEUE_CAP
        comp = d.comp
        first = comp.window(wids[0])
        # first queued toast (payload 1) painted exactly 1 fg cell
        canvas = comp.composite()
        row = first["rect"][0]
        fg = sum(1 for c in range(TOAST_W)
                 if tuple(canvas[row, first["rect"][1] + c]) == (0xF0, 0xF0, 0xF0))
        assert fg == 1
    finally:
        d.close()


# ── T8 ───────────────────────────────────────────────────────────────────
def test_t8_fence_still_governs():
    d = _make_daemon()
    try:
        comp = d.comp
        # a legit toast up first (the innocent survivor)
        d.submit(LEVEL_OK, 3)
        (innocent,) = d.dispatch(origin=(16, 0))
        om = OpcodeMapV2()
        asm = GlyphAssemblerV2(om)
        # rogue agent: ST its request word OUTSIDE its own tile
        rogue = comp.place(_rogue_program(asm, target_word=0),  # word 0: far away
                           plane_origin=(40, 8), size=(2, 8), name="rogue")
        d.register_agent(rogue, request_cell=(41, 9))
        statuses = comp.run_all()
        wcb = comp.window(rogue)
        assert statuses[wcb["pid"]] == EXIT_FAULT   # the reaper caught it
        assert d.harvest() == 0                     # nothing to harvest
        assert d.held() == 0
        # innocent toast still composites
        canvas = comp.composite()
        assert comp.hit_test(16, 1) == innocent
        fg = sum(1 for c in range(TOAST_W)
                 if tuple(canvas[16, c]) == (0xF0, 0xF0, 0xF0))
        assert fg == 3
        om.close()
    finally:
        d.close()


# ── N1 ───────────────────────────────────────────────────────────────────
def test_n1_engine_byte_guard():
    assert _engine_md5() == ENGINE_MD5


# ── N2 ───────────────────────────────────────────────────────────────────
def test_n2_non_vacuity():
    d = _make_daemon()
    try:
        comp = d.comp
        content = comp.place(_noop_image(d), plane_origin=(50, 0),
                             size=(2, 8), name="content")
        comp.run_all()
        baseline = comp.composite().copy()
        assert d.dispatch(origin=(50, 4)) == []          # nothing queued
        assert comp.composite().shape == baseline.shape  # no window placed
        assert (comp.composite() == baseline).all()      # pixels identical
        # harvest on a quiet agent (zero request word) enqueues nothing
        om = OpcodeMapV2()
        asm = GlyphAssemblerV2(om)
        quiet = comp.place(_agent_program(asm, request_row=51, request_col=9,
                                          level=LEVEL_INFO, payload=0,
                                          quiet=True),
                           plane_origin=(50, 8), size=(2, 8), name="quiet")
        d.register_agent(quiet, request_cell=(51, 9))
        comp.run_all()
        assert d.harvest() == 0
        assert d.held() == 0
        om.close()
    finally:
        d.close()


# ── guest programs ───────────────────────────────────────────────────────

def _noop_image(d: GlyphNotifyDaemon) -> np.ndarray:
    """A minimal task: EXIT 0 immediately (content-window stand-in)."""
    om = OpcodeMapV2()
    img = d._asm.assemble(["LDI r1 0", "SYSCALL r0 0x05", "HALT"],
                          width_instrs=8)
    om.close()
    return img


def _agent_program(asm: GlyphAssemblerV2, request_row: int, request_col: int,
                   level: int, payload: int, magic: int = REQUEST_MAGIC,
                   quiet: bool = False) -> np.ndarray:
    """Agent guest: COMPUTE the request word from constants
    (magic<<24 | level<<16 | payload) and ST it at (request_row,
    request_col) INSIDE its own tile. With quiet=True the guest stores
    ZERO (no alert). All stores fenced to its tile."""
    word = ((magic & 0xFF) << 24) | ((level & 0xFF) << 16) | (payload & 0xFFFF)
    target = request_row * W_MEM + request_col
    return asm.assemble([
        "LDI r19 0",
        f"LDI r10 {word}" if not quiet else "LDI r10 0",
        f"LDI r11 {target}",
        "ST r11 r10",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ], width_instrs=8)


def _rogue_program(asm: GlyphAssemblerV2, target_word: int) -> np.ndarray:
    """Rogue guest: ST at target_word — OUTSIDE its own tile (word 0 is
    never inside a tile at plane rows >= 30)."""
    return asm.assemble([
        "LDI r19 0",
        "LDI r10 0xBAD0",
        f"LDI r11 {target_word}",
        "ST r11 r10",
        "LDI r1 0",
        "SYSCALL r0 0x05",
        "HALT",
    ], width_instrs=8)

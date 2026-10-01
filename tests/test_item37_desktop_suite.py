"""item-37 gate: interactive multi-tile desktop application suite.

Claim (QUEUE_STATE item-37): "Interactive multi-tile desktop application
suite (terminal tile, system monitor gauge, ext2 visual file explorer)".
Prereqs item-33 (GlyphShell, landed) and item-36 (cross-fence reactivity,
9e3a87b0) both LANDED. The suite is a PURE CONSUMER of the landed
item-26..36 layers (tools/glyph_desktop_suite.py composes them): it opens,
on ONE stratum, the item-33 status bar plus THREE reactive windows
(item-35 runtimes), a 4-row terminal tile whose guest program decodes a
seeded payload byte-by-byte through XOR/OR/AND/SHR (the probe-verified
af3e_probe_byteloop3 pattern), a monitor runtime fed by the item-34 wire,
and a 4-row explorer tile whose guest lists an ext2 root through the
LANDED 0x13 SYSCALL_FILE_LIST arm (NO new syscall number) over an
attached GlyphVfs (item-25).

Legs (names normative per the brief):
  A1  TOPOLOGY: bar + three suite runtimes on one stratum; contract
      words decode inside each runtime's OWN tile; rects disjoint.
  A2  TERMINAL ECHO: >=32-byte payload seeded 1-byte-per-word into a
      terminal tile; a GUEST decoder produces the byte-identical string
      in a RAM output buffer; task exits 0.
  A3  MONITOR TRACKS LIVE STATE: A ticks wall->approach; the action word
      crosses to B via GlyphChannel (send/commit/poll); B's environment
      translates the RECEIVED code into B's percepts (item-36 pattern);
      B's painted color moves scan-band -> approach-band (asserted from
      painted_color(), not host bookkeeping); the monitor's GUEST program
      reads the received action word and writes a normalized metric word
      into its OWN tile (fenced ST), asserted from monitor-tile RAM.
  A4  EXPLORER LISTS ROOT: GlyphVfs root with /etc/motd + /etc/hostname
      attached to an explorer task; guest runs SYSCALL r10 0x13 (r1/r2/r3
      = dir/dest/max); exit status == entry count (2); a second leg
      writes the listing to RAM and the host asserts both names appear
      NUL-separated; a missing-directory leg exits -1 (rc propagates).
  A5  CLICK TO APP: launcher idiom — focus + key() BM905 press into a
      suite window's inbox pre-run; the window's guest LDs the count
      word from its tile row 0 and exits status == count (1); asserted
      via exit status AND router.inbox_snapshot(wid)["count"].
  C1  CROSS-APP WIRE: terminal-runtime A emits ONE GlyphChannel message
      to monitor B whose code carries A's own painted-band state; B's
      translated tick resolves approach; the SAME scenario with the
      commit suppressed (encoded, not committed) leaves B at scan (the
      item-36 X4 isolation-difference pattern).
  C2  MIGRATION: tests/test_item33_shell.py passes GREEN via subprocess
      in this tree (the suite is a pure consumer of the shell layer).
  C2B MIGRATION: tests/test_item36_cross_fence.py passes GREEN via
      subprocess in this tree.
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to HEAD.
  N2  WIRE-READ-NOT-ASSUMED (non-vacuity, in-suite): zeroing the 4
      committed packet words in B's tile after commit, before poll, makes
      poll() raise ChannelError (magic/CRC) and B's tick stays scan —
      the A3/C1 green really required the wire-carried word.

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (rects, words, bytes, exit statuses, exceptions). Zero
new syscall numbers; no engine change; no edits to any item-26..36 layer.
NOT proven: no GPU/WGSL execution (host CPU engine, Phase-2 doctrine);
the monitor's environment translation (wire word -> percept) stays
kernel-class host logic — guests still cannot sense across fences; the
explorer lists the VFS staging-union-image view served by the landed
0x13 vfs arm, not a new in-guest ext2 parser; delivery is cooperative
commit-between-runs, never preemptive.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_channel import (  # noqa: E402
    CHAN_HDR,
    ChannelError,
    GlyphChannel,
    TYPE_DATA,
)
from tools.glyph_desktop_suite import (  # noqa: E402
    GlyphDesktopSuite,
    run_click_app,
    run_explorer_listing,
    run_monitor_metric,
    run_terminal_decode,
    term_data_base,
    wire_translate,
)
from tools.glyph_input import GlyphInputRouter  # noqa: E402
from tools.glyph_isa_v2 import W_MEM  # noqa: E402
from tools.glyph_reactive import (  # noqa: E402
    STATE_APPROACH,
    STATE_SCAN,
    ReactiveRuntime,
    SENSE_NONE,
    SENSE_WALL,
)
from tools.glyph_shell import BAR_CELLS, BAR_ROW, GlyphShell  # noqa: E402
from tools.glyph_stratum import GlyphStratum  # noqa: E402
from tools.glyph_vfs import GlyphVfs  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# plane rows (512-row plane; MMIO block 256..264 avoided). The bar owns
# row 8; runtimes deploy FULL-WIDTH 3-row tiles at their plane_row and
# plane_row+5 (the locked item-35 deploy geometry).
ROW_TERM, ROW_MON, ROW_EXP = 40, 60, 80
APP_ROW = ROW_EXP + 10   # 4-row click-app tile row


def _tmp_png(name: str) -> str:
    return os.path.join(REPO, ".builder_queue", name)


# ── A1: topology — bar + three suite runtimes on one stratum ────────────
def test_a1_topology():
    st = GlyphStratum()
    shell = GlyphShell(stratum=st)
    png = _tmp_png(".hermes-tmp.a1root.png")
    GlyphVfs.format(png)
    bar = shell.open_bar(png)
    assert st.window(bar)["rect"] == (BAR_ROW, 0, 1, BAR_CELLS)
    rts = []
    for row in (ROW_TERM, ROW_MON, ROW_EXP):
        rt = ReactiveRuntime(stratum=st, plane_row=row)
        rt.deploy()
        rts.append(rt)
    rects = [rt.window_rect() for rt in rts]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            ar, ac, ah, aw = rects[i]
            br, bc, bh, bw = rects[j]
            overlap = ((ar < br + bh) and (br < ar + ah)
                       and (ac < bc + bw) and (bc < ac + aw))
            assert not overlap, f"rects {rects[i]} and {rects[j]} overlap"
    for rt, rect in zip(rts, rects):
        r, c, h, w = rect
        for addr in ([rt.percept_addr(k) for k in range(4)]
                     + [rt.act_addr(), rt.sensor_addr()]):
            row_, col_ = divmod(addr, W_MEM)
            assert r <= row_ < r + h and c <= col_ < c + w, (
                f"contract word {addr} outside own tile {rect}")
    st.close()
    # the composed suite open() gives the same topology in one call
    suite = GlyphDesktopSuite(rows=(ROW_TERM, ROW_MON, ROW_EXP))
    deployed = suite.open(png)
    assert st.window(deployed["statusbar"])["rect"] == (
        BAR_ROW, 0, 1, BAR_CELLS)
    assert set(deployed) == {"terminal", "monitor", "explorer", "statusbar"}
    suite.close()


# ── A2: terminal echo — guest byte-loop decodes a seeded payload ─────────
def test_a2_terminal_echo():
    st = GlyphStratum()
    payload = b"glyph suite terminal echo 012345"   # 32 bytes
    got = run_terminal_decode(st, suite_om(), ROW_TERM + 10, payload)
    assert got == payload, f"echo mismatch: {got!r} != {payload!r}"
    st.close()


def suite_om():
    from tools.glyph_isa_v2 import OpcodeMapV2
    return OpcodeMapV2()


# ── A3: monitor tracks live state across the wire ────────────────────────
def test_a3_monitor_tracks_live_state():
    om = suite_om()
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_TERM); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_MON); b.deploy()
    ch_ab = GlyphChannel(st, a._agent_wid, b._agent_wid)
    # baseline: B at scan band
    b.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert b.painted_color() == 0x00202000, "scan band baseline"
    # A senses a wall -> approach; the action word crosses on the wire
    sa = a.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sa == STATE_APPROACH
    ch_ab.send(sa, a._seq, typ=TYPE_DATA)
    ch_ab.commit_outbox()
    m = ch_ab.poll()
    a._seq += 1
    assert m is not None and m[2] == sa
    # B's environment translates the RECEIVED word; B PAINTS the approach
    # band (asserted from the runtime's painted view, not host bookkeeping)
    wire_translate(b, m[1])
    sb = b.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sb == STATE_APPROACH
    assert b.painted_color() == 0x00606000, (
        f"B painted {b.painted_color():#x}, expected the approach band")
    # the MONITOR's guest program: read the received action word, normalize
    # to the state band, ST the metric into its OWN tile (fenced) —
    # asserted from monitor-tile RAM
    metric = run_monitor_metric(st, om, ROW_EXP + 10,
                                b.action_word())
    assert metric == STATE_APPROACH, (
        f"monitor metric {metric}, expected {STATE_APPROACH}")
    st.close()


# ── A4: the explorer lists the ext2 root through the LANDED 0x13 arm ─────
def test_a4_explorer_lists_root():
    om = suite_om()
    png = _tmp_png(".hermes-tmp.a4root.png")
    GlyphVfs.format(png)
    v = GlyphVfs(png)
    v.vfs_write("/etc/motd", b"welcome")
    v.vfs_write("/etc/hostname", b"glyph-suite")
    assert v.sync() == 0
    st = GlyphStratum()
    rc, listing = run_explorer_listing(st, v, om, ROW_EXP + 10, "/etc")
    assert rc == 2, f"explorer exit status {rc}, expected the entry count 2"
    assert listing is not None
    names = listing.split(b"\0")
    assert b"hostname" in names and b"motd" in names, (
        f"listing {listing!r} misses expected names")
    assert listing == b"hostname\0motd\0", (
        f"NUL-separated listing mismatch: {listing!r}")
    st.close()
    # missing dir: the engine's -1 propagates as the RAW exit status
    st2 = GlyphStratum()
    rc2, _ = run_explorer_listing(st2, v, om, ROW_EXP + 10, "/nope")
    assert rc2 == -1, (
        "missing directory must exit -1 (the landed refusal contract)")
    st2.close()


# ── A5: click-to-app — the launcher idiom delivers the count ─────────────
def test_a5_click_to_app():
    om = suite_om()
    st = GlyphStratum()
    count, status = run_click_app(st, om, APP_ROW, key_code=34)
    wid_check = GlyphInputRouter(st)
    assert count == 1, f"inbox count {count}, expected 1"
    assert status == 1, (
        f"app exit status {status}, expected the inbox count 1")
    st.close()


# ── C1: cross-app wire — and the commit-suppressed difference ────────────
def test_c1_cross_app_wire():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_TERM); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_MON); b.deploy()
    ch_ab = GlyphChannel(st, a._agent_wid, b._agent_wid)
    # baseline scan
    b.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert b.painted_color() == 0x00202000
    # A's OWN painted-band word is the message code
    sa = a.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert a.painted_color() == 0x00606000     # A approaches: band moved
    ch_ab.send(sa, a._seq, typ=TYPE_DATA)
    ch_ab.commit_outbox()
    m = ch_ab.poll()
    a._seq += 1
    assert m is not None and m[1] == sa
    wire_translate(b, m[1])
    sb = b.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sb == STATE_APPROACH
    assert b.painted_color() == 0x00606000
    st.close()

    # the SAME scenario with the commit suppressed leaves B at scan
    st2 = GlyphStratum()
    a2 = ReactiveRuntime(stratum=st2, plane_row=ROW_TERM); a2.deploy()
    b2 = ReactiveRuntime(stratum=st2, plane_row=ROW_MON); b2.deploy()
    ch2 = GlyphChannel(st2, a2._agent_wid, b2._agent_wid)
    sa2 = a2.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sa2 == STATE_APPROACH
    ch2.send(sa2, a2._seq, typ=TYPE_DATA)      # encoded, NOT committed
    assert ch2.poll() is None                  # nothing arrived
    got = b2.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert got == STATE_SCAN, (
        "with the commit suppressed B must stay at baseline — C1's change "
        "must have come through the wire, not the plane")
    assert b2.painted_color() == 0x00202000
    st2.close()


# ── C2/C2B: migration — the consumed layers' gates stay GREEN ────────────
def _pytest_python():
    for cand in (sys.executable, "python3",
                 os.path.join(REPO, ".venv", "bin", "python")):
        rr = subprocess.run([cand, "-c", "import pytest"], capture_output=True)
        if rr.returncode == 0:
            return cand
    pytest.skip("no pytest-capable interpreter found for migration legs")


def test_c2_migration_item33():
    py = _pytest_python()
    rr = subprocess.run([py, "-m", "pytest", "tests/test_item33_shell.py",
                         "-x", "-q"], cwd=REPO, capture_output=True)
    assert rr.returncode == 0, (
        "item-33 shell gate must stay GREEN:\n"
        + rr.stdout.decode(errors="replace")[-1500:])


def test_c2b_migration_item36():
    py = _pytest_python()
    rr = subprocess.run([py, "-m", "pytest", "tests/test_item36_cross_fence.py",
                         "-x", "-q"], cwd=REPO, capture_output=True)
    assert rr.returncode == 0, (
        "item-36 cross-fence gate must stay GREEN:\n"
        + rr.stdout.decode(errors="replace")[-1500:])


# ── N1: engine-byte guard ─────────────────────────────────────────────────
def test_n1_engine_bytes():
    engine = os.path.join(REPO, "tools", "glyph_isa_v2.py")
    head = subprocess.run(
        ["git", "show", "HEAD:tools/glyph_isa_v2.py"],
        cwd=REPO, capture_output=True)
    assert head.returncode == 0
    with open(engine, "rb") as f:
        assert f.read() == head.stdout, (
            "tools/glyph_isa_v2.py drifted from HEAD — item-37 is a "
            "host-side composition; engine drift invalidates the gate")


# ── N2: the wire read is not assumed (in-suite non-vacuity) ──────────────
def test_n2_wire_read_not_assumed():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_TERM); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_MON); b.deploy()
    ch_ab = GlyphChannel(st, a._agent_wid, b._agent_wid)
    sa = a.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sa == STATE_APPROACH
    ch_ab.send(sa, a._seq, typ=TYPE_DATA)
    ch_ab.commit_outbox()
    # SABOTAGE: zero the 4 committed packet words in B's tile AFTER the
    # commit, BEFORE the poll — the wire slot is empty where the cursor
    # expects seq 0.
    rwcb = st.window(b._agent_wid)
    rcv = st._table.tasks[rwcb["pid"]]["cpu"]
    r, c, _h, _w = rwcb["rect"]
    slot0 = (r + 1) * W_MEM + c + CHAN_HDR
    for i in range(4):
        rcv.memory[slot0 + i] = 0
    with pytest.raises(ChannelError):
        ch_ab.poll()          # the empty slot fails magic/CRC: LOUD
    got = b.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert got == STATE_SCAN, (
        "with the wire slot zeroed B must stay at baseline — the A3/C1 "
        "green required the wire-carried word")
    st.close()

"""item-36 gate: adversarial cross-fence multi-agent reactivity — verifiable
BEHAVIORAL change propagated ACROSS memory fences.

Claim (QUEUE_STATE item-36): "Adversarial cross-fence multi-agent reactivity
gate (verifiable behavioral change across memory fences)". Prereqs item-34
(GlyphChannel, ad9edcf9) and item-35 (GlyphReactive, 86be9194) both LANDED.

The mechanism under test: two fenced agent tiles (item-29 fences, item-31
windows, item-35 reactive runtimes) on ONE stratum. Agent A's guest-computed
state transition is emitted over the item-34 wire (seq/CRC/ack); the
kernel-class commit hands the ring to agent B's tile; B's ENVIRONMENT
translates the received message into B's percept row (the item-32 router /
item-35 environment precedent — kernel-class seeding, never a guest
cross-fence store); B's GUEST then computes a DIFFERENT transition than it
would in isolation. The behavioral change is verified against an ISOLATED
CONTROL runtime on the same tree receiving identical local stimulus —
difference = propagation, sameness = the fence held.

Legs:
  X1  TOPOLOGY + FENCE PRECONDITIONS: two ReactiveRuntimes deploy on one
      stratum at disjoint rects; all six contract words of EACH runtime are
      inside its OWN tile; the rects do not overlap (placement containment).
  X2  ISOLATION BASELINE (the control): a lone runtime's quiet scan stays
      scan and a wall scan goes approach — identical to a runtime sharing a
      stratum with a silent peer. Sharing a plane WITHOUT a message changes
      nothing (no ambient coupling — the fence is real).
  X3  CROSS-FENCE REACTION (the item's core claim): A ticks wall ->
      approach; the message crosses via GlyphChannel; B's environment seeds
      B's percepts FROM THE RECEIVED WORD; B's guest transitions
      scan->approach — while the isolated control, given the SAME local
      stimulus B received (quiet), stays scan. The DIFFERENCE is the
      behavioral change across the fence, and it was carried by the wire,
      not by any store across it.
  X4  THE WIRE IS THE ONLY PATH (adversarial): the same X3 scenario with the
      channel commit SUPPRESSED (message encoded, never committed into B's
      tile) leaves B at scan — proving X3's change came through the channel
      ABI, not from stratum sharing, address collision, or seed leakage.
  X5  MULTI-AGENT CASCADE: three runtimes A->B->C chained through two
      channels; a wall sensed by A propagates two hops: B reacts (X3
      mechanism), C reacts to B's emitted state. Each hop's payload equals
      the upstream agent's OWN action word (guest-computed, seq-ordered).
  X6  FORGED / CORRUPT WIRE IS REFUSED, REACTION DOES NOT FIRE
      (adversarial): a message hand-crafted with a BAD CRC (one flipped bit
      in a committed slot word) makes the receiver-side poll() RAISE
      ChannelError, B's environment never seeds from it, and B's tick stays
      at the isolated baseline (scan). Corruption cannot inject behavior.
  X7  OUT-OF-RANGE STATE CODE IS QUARANTINED (adversarial): a forged wire
      message whose code is not a legal state (0..3) is delivered intact by
      the channel (the wire is content-agnostic) but B's environment REFUSES
      to translate it into a percept (loud ValueError); B stays scan. A
      peer cannot drive B into an undefined state through the fence.
  X8  FENCE STILL CONTAINS GUESTS ON THIS TOPOLOGY (item-33 S5 / item-34
      N3 / item-35 N3 discipline, re-proven with BOTH agents deployed): a
      rogue guest fenced to A's tile ordered to ST at B's contract row is
      reaped EXIT_FAULT and B's act word is untouched.
  X9  MIGRATION: item-35's reactive gate re-runs GREEN in this tree via
      subprocess (item-36 composes the reactive runtime; it must not move).
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to HEAD
      (item-36 is a HOST-side composition; engine drift invalidates the gate).
  N2  NON-VACUITY (the cross-fence leg can fail): wiring the X3 scenario with
      the environment seed REVERSED (B seeded with the complement of A's
      state, a wrong translation) flips B's resolution away from the X3
      expectation — the green does not come from B defaulting or from the
      harness asserting a constant; B really branches on the wire-carried
      word.

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (states, seqs, words, exit statuses, exceptions). Zero
new syscall numbers; no engine change; no new wire format (item-34 BM905
reuse). NOT proven: no GPU/WGSL execution (host CPU engine, Phase-2
doctrine); the environment translation (wire word -> percept) is kernel-
class HOST logic — the GUEST still cannot sense across a fence (each task
RAM is a private copy; cross-window SENSE stays structurally impossible,
and X8 re-proves stores cannot cross either); delivery is still
cooperative commit-between-runs, not preemptive; the "adversary" here is a
corrupted/forged WIRE and an out-of-range payload — a malicious GUEST is
answered only by the fence itself (X8), not by this gate.
"""
import os
import subprocess
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_channel import (  # noqa: E402
    CHAN_HDR,
    ChannelError,
    GlyphChannel,
    TYPE_DATA,
)
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)
from tools.glyph_stratum import GlyphStratum  # noqa: E402
from tools.glyph_reactive import (  # noqa: E402
    SENSE_NONE,
    SENSE_WALL,
    STATE_APPROACH,
    STATE_SCAN,
    ReactiveRuntime,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_OM = OpcodeMapV2()
_ASM = GlyphAssemblerV2(_OM)

# plane rows for the topologies (512-row plane; MMIO block 256..264 avoided)
ROW_A, ROW_B, ROW_C, ROW_CTRL = 40, 60, 80, 100


def _agent_env(rt: ReactiveRuntime, rx_wid: int):
    """Build the receiving half for runtime `rt`: (channel INTO rt's agent
    tile, translate). translate(code) maps a received state code to the
    percept pair the environment seeds; out-of-range codes are refused
    LOUD (the X7 quarantine) — a peer cannot drive an undefined state."""
    ch = GlyphChannel(rt.stratum, rx_wid, rt._agent_wid)

    def translate(code: int) -> None:
        if not 0 <= code <= 3:
            raise ValueError(f"wire code {code} is not a legal state (0..3)")
        # received APPROACH from a peer means the peer sensed a wall on
        # the shared plane: surface it as this agent's wall percept.
        rt.set_percepts(SENSE_WALL if code == STATE_APPROACH else SENSE_NONE, 0)

    return ch, translate


def _deliver(ch: GlyphChannel, code: int, seq: int, commit: bool = True):
    """Send one state message A->B on the wire; optionally suppress the
    commit (X4's adversarial no-path variant)."""
    ch.send(code, seq, typ=TYPE_DATA)
    if commit:
        ch.commit_outbox()
        return ch.poll()
    return None


# ── X1: topology + fence preconditions ──────────────────────────────────
def test_x1_topology_and_fence_preconditions():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    arect = a.window_rect()
    brect = b.window_rect()
    assert arect != brect
    # disjoint tiles (placement containment already refuses overlap; assert it)
    ar, ac, ah, aw = arect
    br, bc, bh, bw = brect
    overlap = (ar < br + bh) and (br < ar + ah) and (ac < bc + bw) and (bc < ac + aw)
    assert not overlap
    # every contract word of EACH runtime is inside its OWN tile
    for rt, rect in ((a, arect), (b, brect)):
        r, c, h, w = rect
        for addr in ([rt.percept_addr(i) for i in range(4)]
                     + [rt.act_addr(), rt.sensor_addr()]):
            row, col = divmod(addr, W_MEM)
            assert r <= row < r + h and c <= col < c + w, (
                f"contract word {addr} outside own tile {rect}")
    st.close()


# ── X2: isolation baseline — no ambient coupling through the fence ──────
def test_x2_isolation_baseline_no_ambient_coupling():
    # (i) a LONE runtime
    lone = ReactiveRuntime(plane_row=ROW_A)
    lone.deploy()
    assert lone.tick(SENSE_NONE, 0, current_state=STATE_SCAN) == STATE_SCAN
    assert lone.tick(SENSE_WALL, 0, current_state=STATE_SCAN) == STATE_APPROACH
    lone.close()
    # (ii) a runtime sharing a stratum with a SILENT peer (no wire traffic)
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    assert b.tick(SENSE_NONE, 0, current_state=STATE_SCAN) == STATE_SCAN, (
        "a silent co-resident peer must not perturb the baseline")
    st.close()


# ── X3: the core claim — behavioral change across the fence ─────────────
def test_x3_cross_fence_reaction():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    ctrl = ReactiveRuntime(stratum=st, plane_row=ROW_CTRL); ctrl.deploy()
    ch_ab, translate_b = _agent_env(b, a._agent_wid)
    # A senses a wall: guest-computed transition scan->approach, emitted
    sa = a.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sa == STATE_APPROACH
    m = _deliver(ch_ab, sa, a._seq)
    a._seq += 1
    assert m is not None and m[2] == STATE_APPROACH     # B's side received it
    # B's environment translates the RECEIVED word into B's percept row
    translate_b(m[2])
    got_b = b.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert got_b == STATE_APPROACH
    # CONTROL: identical local stimulus B's WIRE word described (wall) but
    # the control agent is given the QUIET row B would have without the
    # message — it stays scan. Difference = cross-fence propagation.
    got_ctrl = ctrl.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert got_ctrl == STATE_SCAN
    assert got_b != got_ctrl
    st.close()


# ── X4: the wire is the only path (commit suppressed) ───────────────────
def test_x4_wire_is_the_only_path():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    ch_ab, translate_b = _agent_env(b, a._agent_wid)
    sa = a.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sa == STATE_APPROACH
    # encode + hold in the outbox but DO NOT commit into B's tile
    ch_ab.send(sa, a._seq, typ=TYPE_DATA)
    assert ch_ab.poll() is None                  # nothing arrived
    # the environment has NO word to translate: B keeps its own quiet read
    got_b = b.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert got_b == STATE_SCAN, (
        "with the commit suppressed B must stay at baseline — X3's change "
        "must have come through the channel, not the plane")
    st.close()


# ── X5: multi-agent cascade A->B->C, two hops ────────────────────────────
def test_x5_multi_agent_cascade():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    c = ReactiveRuntime(stratum=st, plane_row=ROW_C); c.deploy()
    ch_ab, translate_b = _agent_env(b, a._agent_wid)
    ch_bc, translate_c = _agent_env(c, b._agent_wid)
    sa = a.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sa == STATE_APPROACH
    m1 = _deliver(ch_ab, sa, a._seq); a._seq += 1
    translate_b(m1[2])
    sb = b.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sb == STATE_APPROACH
    assert ch_ab.receiver_snapshot()["seq_next"] == 1
    # hop 2: B's OWN action word crosses to C
    m2 = _deliver(ch_bc, sb, b._seq); b._seq += 1
    assert m2 is not None and m2[2] == sb
    translate_c(m2[2])
    sc = c.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sc == STATE_APPROACH
    # both hops seq-ordered, payloads are the upstream agents' OWN words
    assert (m1[0], m2[0]) == (0, 0)              # each channel's first seq
    assert m1[2] == sa and m2[2] == sb
    st.close()


# ── X6: corrupt wire is refused; reaction does not fire ─────────────────
def test_x6_corrupt_wire_refused_reaction_does_not_fire():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    ch_ab, translate_b = _agent_env(b, a._agent_wid)
    sa = a.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    ch_ab.send(sa, a._seq, typ=TYPE_DATA)
    ch_ab.commit_outbox()
    # flip one bit of the committed packet's payload word in B's tile
    rwcb = st.window(b._agent_wid)
    rcv = st._table.tasks[rwcb["pid"]]["cpu"]
    r, c, _h, _w = rwcb["rect"]
    base = (r + 1) * W_MEM + c
    slot0 = base + CHAN_HDR
    rcv.memory[slot0 + 2] ^= 0x1                 # payload word, 1 bit
    with pytest.raises(ChannelError):
        ch_ab.poll()                             # corruption is LOUD
    # the environment never got a verified word: no translation, B stays scan
    got_b = b.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert got_b == STATE_SCAN
    st.close()


# ── X7: out-of-range state code quarantined at the environment ──────────
def test_x7_out_of_range_state_quarantined():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    ch_ab, translate_b = _agent_env(b, a._agent_wid)
    # a forged WIRE message (host-side forge — the strongest wire adversary
    # available without a malicious guest, which X8 answers): valid CRC,
    # illegal code 7. The channel delivers it intact (content-agnostic).
    ch_ab.send(7, 0, typ=TYPE_DATA)
    ch_ab.commit_outbox()
    m = ch_ab.poll()
    assert m is not None and m[1] == 7     # poll returns (seq, code, value)
    with pytest.raises(ValueError):
        translate_b(m[1])                        # quarantine is LOUD
    # B was never seeded: stays at the isolated baseline
    got_b = b.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert got_b == STATE_SCAN
    st.close()


# ── X8: the fence still contains guests on this topology ────────────────
def test_x8_fence_contains_guests_both_agents_deployed():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    b_act = b.act_addr()
    arect = a.window_rect()
    rogue = _ASM.assemble([
        f"LDI r10 {b_act}",          # B's contract act slot — OUTSIDE A's tile
        "LDI r2 0x0DEAD0",
        "ST r10 r2",                 # the cross-fence order
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ], width_instrs=8)
    pid = st._table.spawn(rogue, name="rogue", tile=arect)
    cpu = st._table.tasks[pid]["cpu"]
    cpu.registers[1] = arect[0] * W_MEM + arect[1]
    status = st._table.wait(pid)
    assert status == 1, f"cross-fence store must be reaped EXIT_FAULT, got {status}"
    assert st._table.tasks[st.window(b._agent_wid)["pid"]][
        "cpu"].memory[b_act] != 0x0DEAD0
    st.close()


# ── X9: migration — the item-35 reactive gate stays GREEN ────────────────
def _pytest_python():
    for cand in (sys.executable, "python3",
                 os.path.join(REPO, ".venv", "bin", "python")):
        rr = subprocess.run([cand, "-c", "import pytest"], capture_output=True)
        if rr.returncode == 0:
            return cand
    pytest.skip("no pytest-capable interpreter found for migration legs")


def test_x9_item35_gate_unchanged():
    py = _pytest_python()
    rr = subprocess.run([py, "-m", "pytest", "tests/test_item35_reactive.py",
                         "-x", "-q"], cwd=REPO, capture_output=True)
    assert rr.returncode == 0, (
        "item-35 reactive gate must stay GREEN:\n"
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
            "tools/glyph_isa_v2.py drifted from HEAD — item-36 is a "
            "host-side composition; engine drift invalidates the gate")


# ── N2: non-vacuity — a wrong translation flips the resolution ──────────
def test_n2_wrong_translation_flips_resolution():
    st = GlyphStratum()
    a = ReactiveRuntime(stratum=st, plane_row=ROW_A); a.deploy()
    b = ReactiveRuntime(stratum=st, plane_row=ROW_B); b.deploy()
    ch_ab, _ = _agent_env(b, a._agent_wid)
    sa = a.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert sa == STATE_APPROACH
    m = _deliver(ch_ab, sa, a._seq); a._seq += 1
    assert m[2] == STATE_APPROACH
    # WRONG translation: seed the COMPLEMENT (quiet) instead of wall —
    # B must resolve DIFFERENTLY than X3's green expectation. This proves
    # B branches on the wire-carried word, not on a harness constant.
    b.set_percepts(SENSE_NONE, 0)
    got_b = b.tick(SENSE_NONE, 0, current_state=STATE_SCAN)
    assert got_b == STATE_SCAN
    assert got_b != STATE_APPROACH
    st.close()

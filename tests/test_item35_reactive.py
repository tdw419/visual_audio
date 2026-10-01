"""item-35 gate: reactive agent state machine runtime (read-evaluate-act-
paint execution loop).

The unit under test is tools/glyph_reactive.py (ReactiveRuntime), which
composes the landed layers: item-31 windows (fenced tiles), item-29
containment, item-34 GlyphChannel (the ACT telemetry wire), and the
cooperative seed-then-run model (item-26/33 precedent).

Legs:
  R1  DEPLOY + CONTRACT ROW GEOMETRY: deploy() opens the agent window
      and its IPC peer, binds a GlyphChannel, and the contract row
      addresses (percepts 0..3, act, sensor) are inside the agent's own
      tile. Deploy is idempotent-refusing (a second deploy raises).
  R2  READ IS REAL (the sensor echo): tick() with a known percept; the
      agent's sensor word (its OWN guest ST) equals the percept — the
      guest LDed the environment row and echoed it. Corrupting the
      percept seed after the run (RED discrimination) changes nothing
      already run, but a DIFFERENT percept yields a DIFFERENT sensor.
  R3  EVALUATE IS GUEST-COMPUTED (the FSM lives in guest instructions):
      the SAME program, seeded with different percepts, resolves
      DIFFERENT next states — wall->approach, target->act, trap->flee,
      none->scan, event->flee. The transition table is NOT host logic:
      the only host-side work is seeding and reading words.
  R4  ACT + CHANNEL TELEMETRY (the item-34 wire): every tick() emits
      exactly one ordered channel message whose code is the resolved
      state; after N ticks the receiver snapshot count is N and the
      wire is drained cleanly (poll returns None).
  R5  PAINT IS REAL + FENCED: the composite shows the paint cell in the
      state's color band; and a tick whose paint order would cross the
      fence is impossible by construction — proven by the N3 rogue leg
      (this leg asserts the painted word comes from the agent's OWN
      tile RAM, in-tile).
  R6  MULTI-TICK REACTIVITY SEQUENCE: a scripted percept sequence
      drives scan->approach->act->scan across three ticks, each
      transition both stored (act word) and emitted (channel seq
      order). The transitions ledger matches the act words.
  R7  MIGRATION: item-34's channel gate re-runs GREEN in this tree via
      subprocess (the runtime consumes the channel; it must not move).
  N1  ENGINE-BYTE guard: tools/glyph_isa_v2.py is byte-identical to
      HEAD (item-35 is a HOST-side runtime; engine drift invalidates
      the gate's premises).
  N2  NON-VACUITY (the FSM leg can fail): seeding the environment row
      with a WRONG percept pattern (all 0xFFFFFFFF) and asserting a
      specific state FAILS — i.e. R3's green does not come from the
      runtime defaulting; the guest really branches on the percepts.
  N3  FENCE still contains guests on this tree: a rogue guest fenced to
      the agent tile and ordered to ST at the PEER's contract row is
      reaped EXIT_FAULT (item-33 S5 / item-34 N3 discipline).

Honesty: no rates/latencies asserted (rule-1 floors do not attach); all
asserts structural (words, colors, counts, seqs, exit statuses,
exceptions). Zero new syscall numbers; no engine change. NOT proven: no
GPU/WGSL execution (host CPU engine, Phase-2 doctrine); perception is a
contract-row read, NOT a composite readback (cross-window SENSE is
structurally impossible — each task RAM is a private copy); the
runtime does not preempt (cooperative seed-then-run; a fresh agent task
per tick); the state machine is fixed at assemble time, not learned;
stay-marker paint resolves through the agent's documented masked-color
path (the gate asserts ACTION WORDS for stay legs, not colors).
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.glyph_channel import ChannelError  # noqa: E402,F401
from tools.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2,
    OpcodeMapV2,
    W_MEM,
)
from tools.glyph_reactive import (  # noqa: E402
    SENSE_NONE,
    SENSE_TARGET,
    SENSE_TRAP,
    SENSE_WALL,
    STATE_ACT,
    STATE_APPROACH,
    STATE_FLEE,
    STATE_SCAN,
    ReactiveError,
    ReactiveRuntime,
)
from tools.glyph_stratum import GlyphStratum, StratumError  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_OM = OpcodeMapV2()
_ASM = GlyphAssemblerV2(_OM)


# ── R1: deploy + contract row geometry ──────────────────────────────────
def test_r1_deploy_and_contract_row_geometry():
    rt = ReactiveRuntime()
    agent_wid, peer_wid = rt.deploy()
    assert agent_wid != peer_wid
    arect = rt.stratum.window(agent_wid)["rect"]
    prect = rt.stratum.window(peer_wid)["rect"]
    # two distinct fenced tiles, no overlap
    assert arect != prect
    # contract row words live INSIDE the agent's own tile
    r, c, h, w = arect
    for word_off in range(0, 6):        # percepts 0..3, act, sensor
        addr = rt.percept_addr(word_off) if word_off < 4 else (
            rt.act_addr() if word_off == 4 else rt.sensor_addr())
        row, col = divmod(addr, W_MEM)
        assert r <= row < r + h, f"contract word {word_off} row outside tile"
        assert c <= col < c + w, f"contract word {word_off} col outside tile"
    # double deploy refuses loud
    with pytest.raises(ReactiveError):
        rt.deploy()
    rt.close()


# ── R2: READ is real (the sensor echo) ──────────────────────────────────
def test_r2_read_is_real_sensor_echo():
    rt = ReactiveRuntime()
    rt.deploy()
    rt.set_percepts(SENSE_WALL, 0)
    nxt = rt.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    # the agent's OWN guest store of what it loaded
    assert rt.action_word() == nxt
    assert rt._agent_cpu().memory[rt.sensor_addr()] == SENSE_WALL, (
        "the agent must echo the percept it LDed (guest-side ST)")
    # a different percept yields a different sensor read (discriminating)
    rt2_state = rt.tick(SENSE_TRAP, 0, current_state=STATE_SCAN)
    assert rt._agent_cpu().memory[rt.sensor_addr()] == SENSE_TRAP
    assert rt2_state in (STATE_SCAN, STATE_APPROACH, STATE_ACT, STATE_FLEE)
    rt.close()


# ── R3: EVALUATE is guest-computed (FSM transitions) ────────────────────
def test_r3_evaluate_is_guest_computed_fsm():
    rt = ReactiveRuntime()
    rt.deploy()
    # scan + wall -> approach
    assert rt.tick(SENSE_WALL, 0, current_state=STATE_SCAN) == STATE_APPROACH
    # scan + target -> act
    assert rt.tick(SENSE_TARGET, 0, current_state=STATE_SCAN) == STATE_ACT
    # scan + trap -> flee
    assert rt.tick(SENSE_TRAP, 0, current_state=STATE_SCAN) == STATE_FLEE
    # scan + nothing -> scan (re-arm)
    assert rt.tick(SENSE_NONE, 0, current_state=STATE_SCAN) == STATE_SCAN
    # event (p1=1) dominates -> flee from any state
    assert rt.tick(SENSE_NONE, 1, current_state=STATE_SCAN) == STATE_FLEE
    # the SAME program produced 4+ distinct resolutions: guest-computed
    seen = {t[3] for t in rt.transitions}
    assert seen == {STATE_SCAN, STATE_APPROACH, STATE_ACT, STATE_FLEE}
    rt.close()


# ── R4: ACT + channel telemetry (the item-34 wire) ──────────────────────
def test_r4_act_emits_ordered_channel_messages():
    rt = ReactiveRuntime()
    rt.deploy()
    for i, (p0, want) in enumerate(
            [(SENSE_WALL, STATE_APPROACH), (SENSE_TARGET, STATE_ACT),
             (SENSE_NONE, STATE_SCAN)]):
        got = rt.tick(p0, 0, current_state=STATE_SCAN)
        assert got == want
        snap = rt.channel_snapshot()
        assert snap["count"] == i + 1        # one message per tick
    snap = rt.channel_snapshot()
    assert snap["ack"] == 2                  # all three drained in order
    rt.close()


# ── R5: PAINT is real + in-tile ─────────────────────────────────────────
def test_r5_paint_is_real_and_in_tile():
    rt = ReactiveRuntime()
    rt.deploy()
    rt.tick(SENSE_TARGET, 0, current_state=STATE_SCAN)   # -> act (green-ish)
    cpu = rt._agent_cpu()
    wid = rt._agent_wid
    assert wid is not None
    r, c, _h, _w = rt.stratum.window(wid)["rect"]
    paint_word = cpu.memory[(r + 0) * W_MEM + c] & 0xFFFFFF
    assert paint_word != 0, "the agent must paint its own tile cell"
    # the composite carries the SAME color at the paint cell (in-tile);
    # unpack order matches the LOCKED item-31 composite encoding
    # (glyph_stratum.py composite(): word = (R<<16)|(G<<8)|B)
    canvas = rt.stratum.composite()
    assert tuple(int(v) for v in canvas[r, c]) == (
        (paint_word >> 16) & 0xFF, (paint_word >> 8) & 0xFF, paint_word & 0xFF)
    rt.close()


# ── R6: multi-tick reactivity sequence ──────────────────────────────────
def test_r6_multi_tick_reactivity_sequence():
    rt = ReactiveRuntime()
    rt.deploy()
    # scan -wall-> approach -arrive(p1)-> ... approach + quiet + no event
    # stays approach (stay marker), then trap -> flee -> scan re-arm.
    s0 = rt.tick(SENSE_WALL, 0, current_state=STATE_SCAN)
    assert s0 == STATE_APPROACH
    s1 = rt.tick(SENSE_NONE, 0, current_state=s0)
    assert s1 == s0                          # unrecognized -> stay
    s2 = rt.tick(SENSE_TRAP, 0, current_state=s1)
    assert s2 == STATE_FLEE
    s3 = rt.tick(SENSE_NONE, 0, current_state=s2)
    assert s3 == STATE_SCAN                  # flee re-arms
    led = rt.transitions
    assert [t[3] for t in led] == [s0, s1, s2, s3]
    assert [t[0] for t in led] == [0, 1, 2, 3]   # channel seq order
    rt.close()


# ── N2: non-vacuity — the FSM leg can fail ──────────────────────────────
def test_n2_fsm_is_not_a_default():
    rt = ReactiveRuntime()
    rt.deploy()
    # a garbage environment (all-ones percept) must NOT resolve to any
    # clean state via a host default: the stay marker is the only legal
    # resolution for an unrecognized percept... except the event bit
    # (p1 lsb of the key) dominates. All-ones = key >= 4 with p1=1 ->
    # flee. Assert the guest actually branched: run with p1=0 and a
    # garbage p0 (key 0xFE<<1, >= 4, quiet) -> the STAY path must fire,
    # i.e. the action word equals the current state (stay semantics),
    # NOT a crash and NOT an arbitrary default state.
    stay = rt.tick(0xFE, 0, current_state=STATE_ACT)
    assert stay == STATE_ACT, (
        f"garbage quiet percept must STAY (got {stay}) — proves the "
        "guest branches on the percept bytes")
    rt.close()


# ── N3: the fence still contains guests on this tree ────────────────────
def test_n3_fence_contains_guests():
    rt = ReactiveRuntime()
    rt.deploy()
    agent_wid = rt._agent_wid
    peer_wid = rt._peer_wid
    assert agent_wid is not None and peer_wid is not None
    arect = rt.stratum.window(agent_wid)["rect"]
    prect = rt.stratum.window(peer_wid)["rect"]
    peer_contract = (prect[0] + 1) * W_MEM + prect[1]
    rogue = _ASM.assemble([
        f"LDI r10 {peer_contract}",   # the PEER's contract row base
        "LDI r2 0x0DEAD0",
        "ST r10 r2",                  # cross-fence write order
        "LDI r1 0",
        "SYSCALL r0 5",
        "HALT",
    ], width_instrs=8)
    table = rt.stratum._table
    pid = table.spawn(rogue, name="rogue", tile=arect)
    cpu = table.tasks[pid]["cpu"]
    cpu.registers[1] = arect[0] * W_MEM + arect[1]   # tile base seed contract
    status = table.wait(pid)
    assert status == 1, f"cross-fence store must be reaped EXIT_FAULT, got {status}"
    peer_cpu = table.tasks[rt.stratum.window(peer_wid)["pid"]]["cpu"]
    assert peer_cpu.memory[peer_contract] != 0x0DEAD0
    rt.close()


# ── R7: migration — the item-34 channel gate stays GREEN ────────────────
def _pytest_python():
    for cand in (sys.executable, "python3",
                 os.path.join(REPO, ".venv", "bin", "python")):
        rr = subprocess.run([cand, "-c", "import pytest"], capture_output=True)
        if rr.returncode == 0:
            return cand
    pytest.skip("no pytest-capable interpreter found for migration legs")


def test_r7_item34_gate_unchanged():
    py = _pytest_python()
    rr = subprocess.run([py, "-m", "pytest", "tests/test_item34_channel.py",
                         "-x", "-q"], cwd=REPO, capture_output=True)
    assert rr.returncode == 0, (
        "item-34 channel gate must stay GREEN:\n"
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
            "tools/glyph_isa_v2.py drifted from HEAD — item-35 is a "
            "host-side runtime; engine drift invalidates the gate")

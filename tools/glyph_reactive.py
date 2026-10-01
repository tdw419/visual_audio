"""glyph_reactive.py — CLAIM QUEUE item 35: reactive agent state machine
runtime (read-evaluate-act-paint execution loop).

Spec (claim supply, QUEUE_STATE item-35): a "Reactive agent state machine
runtime (read-evaluate-act-paint execution loop)" — a runtime where a
GUEST agent task (1) READS its percepts, (2) EVALUATES a state machine
(guest-computed transition function, not a host table lookup), (3) ACTS
by writing an action word to its runtime contract row, and (4) PAINTS
its own tile from the new state.

Layer contract (items 26-34 landed the foundation this composes):

  - item-31 (tools/glyph_stratum.py): GlyphStratum — windows as fenced
    tiles on the W_MEM=32 word-grid plane. The agent's tile IS its
    world: everything the agent can sense or paint is inside the fence.
  - item-32 (tools/glyph_input.py): BM905 packets into a window's tile
    top row — the ENVIRONMENT side of the sense half (an input event
    lands in the agent's perception row before its task runs).
  - item-34 (tools/glyph_channel.py): GlyphChannel — ordered, CRC'd,
    acked messages between two fenced tiles. The ACT half uses it for
    real: each transition EMITS one channel message whose code is the
    state the agent just entered (the reactivity telemetry path).

The ReactiveRuntime is the HOST-side kernel-class driver for a
reactive AGENT task plus its ENVIRONMENT contract row:

  Read    : the agent LDs its SENSE row (percepts 0..3, sensor word 4)
            from its own tile — real guest LDs, no host interpretation.
  Evaluate: a GUEST-COMPUTED transition function over the loaded
            percept (LDI/SHL/AND decode, jump table, state-encode add) —
            the state machine lives in guest instructions, not in a
            host dict. Gate legs prove the transition is guest-computed
            by changing ONE percept byte and observing a DIFFERENT
            next state from the SAME program.
  Act     : the agent STs its new state word to the contract row's
            action slot (a real guest store, fenced in-tile), which
            the runtime reads back after the run and routes as a
            GlyphChannel message (seq, CRC, ack — the item-34 wire).
  Paint   : the agent paints one cell of its own tile per state (red/
            green/blue/amber) through fenced STs — the composite shows
            the state machine, and cross-fence paint is impossible by
            the item-29 fence (proven again on this tree).

Contract row (the agent's SECOND tile row; row 0 is paint cells and —
for input windows — the item-32 mailbox row):

    word 0  percept 0        (environment: SENSE_NONE / SENSE_WALL /
                              SENSE_TARGET / SENSE_TRAP)
    word 1  percept 1        (environment: 0 = quiet, 1 = event)
    word 2  percept 2        (environment: free)
    word 3  percept 3        (environment: free)
    word 4  act      (agent-written; the runtime's action slot)
    word 5  sensor   (agent-written; raw percept the agent loaded)

States (the LOCKED state vocabulary):

    STATE_SCAN = 0, STATE_APPROACH = 1, STATE_ACT = 2, STATE_FLEE = 3

    scan      -sense wall->  approach
    scan      +sense event-> flee
    approach  -arrive (p1)-> act
    approach  -sense trap->  flee
    flee      -> scan       (default transition: re-arm)
    act       -> scan       (default transition: re-arm)
    (unrecognized percept -> stay in the current state: reactivity,
    not a crash)

What this is NOT (honesty): host-side Phase-2 artifact over the
CPU-oracle engine — NO new syscall number, NO engine change, NO
guest-visible ABI beyond RAM words a task already LD/STs (WGSL twin
contract untouched). Perception is a contract-row read, NOT a
composite readback: an agent cannot see another window's pixels (each
task's RAM is a private copy — cross-window SENSE is structurally
impossible and never claimed). The runtime does not preempt: like
items 26-34 the step model is seed-then-run (cooperative) — a tick
seeds the environment row, runs the agent task to HALT, reads the
action, and advances the channel; a fresh agent task per tick (the
item-33 refresh_bar precedent). The state machine is fixed at
assemble time (a real FSM, not a learned policy); no rates or
latencies are asserted (rule-1 floors do not attach).
"""
from __future__ import annotations

import numpy as np

from tools.glyph_channel import TYPE_DATA, GlyphChannel
from tools.glyph_input import GlyphInputRouter  # noqa: F401  (same plane family)
from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2, W_MEM
from tools.glyph_stratum import GlyphStratum

# ── ReactiveRuntime ABI constants (the item-35 LOCKED contract) ──────────
SENSE_NONE = 0            # nothing of interest in the sensed cell
SENSE_WALL = 1            # obstacle ahead
SENSE_TARGET = 2          # the thing the agent seeks
SENSE_TRAP = 3            # hazard: the correct reaction is flee

STATE_SCAN = 0
STATE_APPROACH = 1
STATE_ACT = 2
STATE_FLEE = 3
STATE_NAMES = {STATE_SCAN: "scan", STATE_APPROACH: "approach",
               STATE_ACT: "act", STATE_FLEE: "flee"}

ROW_PERCEPT0 = 35         # contract row word 0..3: environment percepts
ROW_ACT = 39              # word 4: agent-written action (the new state)
ROW_SENSOR = 40           # word 5: agent-written raw percept it loaded
AGENT_ROW = 1             # the agent tile's CONTRACT row (row 1 of its tile)
AGENT_PAINT_ROW = 0       # row 0: the agent's paint cells

# The contract row SHARES row 1 with the item-34 channel wire (CHAN header
# 3 words + 8 slots x 4 words = 35 words, offsets 0..34). The contract
# words therefore start at offset 35 — no overlap with the channel wire,
# which is the whole reason ROW_PERCEPT0 is not 0.

# paint colors per state — the HOST view of the guest's masked palette:
# guest paints base 0x00202000 + stride 0x00404000 * (resolved & 3),
# i.e. scan 0x00202000, approach 0x00606000, act 0x00A0A000,
# flee 0x00E0E000. The stay marker resolves to index 3 (flee band) by
# the documented masked path; stay COLOR is not a contract (the gate
# asserts action words for stay legs, not colors).
STATE_COLORS = {
    STATE_SCAN: 0x00202000,
    STATE_APPROACH: 0x00606000,
    STATE_ACT: 0x00A0A000,
    STATE_FLEE: 0x00E0E000,
}


class ReactiveError(Exception):
    """Raised on runtime misuse — loud, never silent."""


def _word(row: int, col: int) -> int:
    return row * W_MEM + col


class ReactiveRuntime:
    """Kernel-class driver for a reactive agent task on a GlyphStratum.

    The agent window is 2 rows tall: row 0 = paint cells, row 1 = the
    contract row (percepts 0..3, act, sensor). The environment writes
    percepts (host, kernel-class — the router precedent); the agent
    task reads them with real guest LDs, computes the transition in
    guest instructions, writes its action with a real guest ST, and
    paints its state cell fenced in-tile. After each tick the runtime
    reads the action word back and routes it over a GlyphChannel (the
    item-34 wire: seq, CRC, ack).
    """

    def __init__(self, stratum: GlyphStratum | None = None,
                 plane_row: int = 40):
        self.stratum = stratum if stratum is not None else GlyphStratum()
        self._om = OpcodeMapV2()
        self._asm = GlyphAssemblerV2(self._om)
        self._plane_row = plane_row
        self._agent_wid: int | None = None
        self._peer_wid: int | None = None
        self._channel: GlyphChannel | None = None
        self._seq = 0
        # per-tick telemetry: (tick, percept, from_state, to_state)
        self.transitions: list[tuple[int, int, int, int]] = []

    # ── topology ─────────────────────────────────────────────────────────
    def deploy(self) -> tuple[int, int]:
        """Open the agent window and its IPC peer window; bind the
        channel. Returns (agent_wid, peer_wid)."""
        if self._agent_wid is not None:
            raise ReactiveError("deploy: runtime already deployed")
        row = self._plane_row
        # FULL-WIDTH (W_MEM=32) x 3-ROW tiles: the item-34 channel bind
        # requires a full-width window; the channel wire (CHAN_WORDS=35
        # from the row-1 base) needs row 2 to land its words [32, 35),
        # and the item-35 contract words live at wire offsets 35..40
        # (still row 2). One tile = row 0 paint/input, rows 1-2 the
        # channel wire + contract row, all fenced.
        self._agent_wid = self.stratum.open_window(
            self._idle_image(), plane_origin=(row, 0), size=(3, W_MEM),
            name="agent")
        self._peer_wid = self.stratum.open_window(
            self._idle_image(), plane_origin=(row + 5, 0), size=(3, W_MEM),
            name="ipc_peer")
        self._channel = GlyphChannel(self.stratum, self._agent_wid,
                                     self._peer_wid)
        return self._agent_wid, self._peer_wid

    def _idle_image(self) -> np.ndarray:
        """Placeholder image so open_window can spawn; every tick swaps
        the task for the REAL agent program (refresh precedent)."""
        return self._asm.assemble([
            "LDI r1 0",
            "SYSCALL r0 5",
            "HALT",
        ], width_instrs=8)

    def window_rect(self) -> tuple[int, int, int, int]:
        self._require_deployed()
        return self.stratum.window(self._agent_wid)["rect"]

    def _require_deployed(self) -> None:
        if self._agent_wid is None:
            raise ReactiveError("runtime not deployed (call deploy())")

    # ── addresses in the AGENT TASK's RAM (its tile's contract row) ─────
    # GEOMETRY (measured against the item-34 wire, CHAN_WORDS=35):
    # the channel row is ROW 1 of the tile, and its 35 words start at
    # (row+1, col) — words [32, 35) of the wire wrap into ROW 2, which
    # is OUTSIDE a 2-row tile. In THIS runtime the channel is bound to
    # the two full-width windows but its wire lives in the windows' OWN
    # RAM copies (commit_outbox writes the RECEIVER TASK's RAM), so the
    # visible constraint is only that contract words must not collide
    # with the wire words [0, 35) measured from (row+1, col). The
    # contract therefore lives in ROW 1 at wire offsets 35..40 — i.e.
    # linear words (row+1)*W_MEM + col + 35 .. +40, which ARE inside the
    # tile when the tile is 3 rows tall. deploy() opens 3-row tiles for
    # exactly this reason; AGENT_ROW and the ROW_* offsets below are
    # the LOCKED item-35 contract.
    def _contract_base(self) -> int:
        r, c, _h, _w = self.window_rect()
        return (r + AGENT_ROW) * W_MEM + c

    def act_addr(self) -> int:
        return self._contract_base() + ROW_ACT

    def sensor_addr(self) -> int:
        return self._contract_base() + ROW_SENSOR

    def percept_addr(self, idx: int) -> int:
        if not 0 <= idx <= 3:
            raise ReactiveError(f"percept index must be 0..3, got {idx}")
        return self._contract_base() + ROW_PERCEPT0 + idx

    # ── the environment: seed the sense row (kernel-class, pre-run) ─────
    def set_percepts(self, p0: int, p1: int = 0, p2: int = 0,
                     p3: int = 0) -> None:
        """Write the environment's percepts into the AGENT's contract
        row before its task runs (the item-32 router precedent: the
        dispatcher is kernel-class; the agent is the consumer)."""
        self._require_deployed()
        for idx, val in ((0, p0), (1, p1), (2, p2), (3, p3)):
            if not 0 <= val <= 0xFFFFFFFF:
                raise ReactiveError(f"percept {idx} out of range: {val}")
        rect = self.window_rect()
        # seed goes to the CURRENT agent task's RAM (post-open)
        cpu = self._agent_cpu()
        for idx, val in ((0, p0), (1, p1), (2, p2), (3, p3)):
            cpu.memory[self.percept_addr(idx)] = val & 0xFFFFFFFF

    def _agent_cpu(self):
        return self.stratum._table.tasks[
            self.stratum.window(self._agent_wid)["pid"]]["cpu"]

    def _spawn_agent(self, state: int) -> int:
        """Spawn a fresh agent task over the FSM program (the item-33
        refresh precedent: a closed/finished task never re-runs)."""
        self._require_deployed()
        rect = self.stratum.window(self._agent_wid)["rect"]
        r, c, h, w = rect
        # close the window record (frees the rect), respawn at the SAME
        # rect, restore the record fields the stratum wiped
        state0 = self.stratum.window(self._agent_wid)["state"]
        if state0 == 1:
            self.stratum.close_window(self._agent_wid)
        program = self.agent_program(initial_state=state)
        # The stratum allocates MONOTONIC wids (a respawn is a NEW window
        # record: close the old, open at the same rect -> new wid). Track
        # the identity by REBINDING to the new wid, never by asserting the
        # old one came back (the old assert is impossible by construction).
        program_rect = rect
        wid = self.stratum.open_window(
            program, plane_origin=(program_rect[0], program_rect[1]),
            size=(program_rect[2], program_rect[3]), name="agent")
        self._agent_wid = wid
        cpu = self._agent_cpu()
        # the agent needs its starting state: seed it at the contract
        # row's act slot pre-run (the agent reads it as its entry state)
        cpu.memory[self.act_addr()] = state & 0xFFFFFFFF
        # item-33 seed contract: r1 = tile base (the paint cell store's
        # destination is data — no guest-visible ABI, a seeded word).
        cpu.registers[1] = r * W_MEM + c
        return wid

    # ── the agent program (the FSM, in guest instructions) ──────────────
    def agent_program(self, initial_state: int = STATE_SCAN) -> np.ndarray:
        """The reactive agent: read-evaluate-act-paint, all in guest
        instructions over the item-35 contract row.

        Register plan:
          r1 tile base (seeded pre-run by the stratum's spawn contract)
          r10 addr scratch, r11..r15 values/scratch
          r16 percept, r17 current state, r18 next state
        """
        base = self._contract_base()
        p0, p1, p2, p3 = (base + ROW_PERCEPT0 + i for i in range(4))
        act_a, sensor_a = base + ROW_ACT, base + ROW_SENSOR
        # paint cell = tile base (row 0, col 0)
        return self._asm.assemble([
            # ── READ: load the percepts (real guest LDs) ──
            f"LDI r10 {p0}",
            "LD r16 r10",            # r16 = percept 0
            f"LDI r10 {p1}",
            "LD r11 r10",            # r11 = percept 1 (event flag)
            # ── sensor echo: store what we sensed (act discipline) ──
            f"LDI r10 {sensor_a}",
            "ST r10 r16",
            # ── EVALUATE: guest-computed transition over (r16, r11) ──
            # dispatch key: p0 itself (0=NONE,1=WALL,2=TARGET,3=TRAP,
            # else unrecognized) with the EVENT bit tested separately in
            # the default arm. The agent ITSELF computes the dispatch
            # from the loaded percept (jump table in guest instructions).
            # r17 = current state (seeded at the act slot pre-run)
            f"LDI r10 {act_a}",
            "LD r17 r10",
            # event dominance: p1=1 -> flee BEFORE the p0 dispatch
            "LDI r12 1",
            "CMP r11 r12",
            "JZ :flee_now",
            # jump table on p0 (data-derived dispatch — reactivity):
            "LDI r13 4",             # p0 >= 4 -> default transition
            "CMP3 r16 r13",
            "JGT :default",
            "LDI r13 0",
            "CMP r16 r13",
            "JZ :k0",
            "LDI r13 1",
            "CMP r16 r13",
            "JZ :k1",
            "LDI r13 2",
            "CMP r16 r13",
            "JZ :k2",
            "LDI r13 3",
            "CMP r16 r13",
            "JZ :k3",
            "JMP :default",
            # key 0: p0=NONE, quiet -> STATE-DEPENDENT re-arm: from scan
            # (or act/flee) the quiet cell re-arms to scan; from approach
            # an quiet cell is NOT a transition stimulus — stay.
            ":k0",
            "LDI r13 1",             # STATE_APPROACH
            "CMP r17 r13",           # current state == approach?
            "JZ :k0_stay",
            "LDI r18 0",             # scan (re-arm from scan/act/flee)
            "JMP :commit",
            ":k0_stay",
            "LDI r18 -1",            # stay marker (resolved at :commit)
            "JMP :commit",
            # key 1: p0=WALL quiet   -> approach
            ":k1",
            "LDI r18 1",
            "JMP :commit",
            # key 2: p0=TARGET quiet -> act
            ":k2",
            "LDI r18 2",
            "JMP :commit",
            # key 3: p0=TRAP quiet   -> flee
            ":k3",
            "LDI r18 3",
            "JMP :commit",
            # key >= 4 (unrecognized p0): only p1 matters (event -> flee),
            # else stay in the current state
            ":default",
            "LDI r13 1",
            "CMP r11 r13",
            "JZ :flee_now",
            # unrecognized percept: STAY in the current state
            "LDI r18 -1",            # -1 = stay marker (0xFFFFFFFF)
            "JMP :commit",
            ":flee_now",
            "LDI r18 3",
            # ── ACT: store the resolved next state (real guest ST) ──
            # Stay-marker resolution: if r18 == 0xFFFFFFFF the transition
            # is a STAY — the resolved state is the CURRENT state, which
            # still sits in the act slot (seeded pre-run, not yet
            # overwritten). Reload it and store that. (No MOV in the ISA;
            # the act-slot reload is the register move.)
            ":commit",
            "LDI r13 -1",
            "CMP r18 r13",           # r18 == stay marker?
            "JNZ :store",            # not the marker -> store as computed
            f"LDI r10 {act_a}",
            "LD r18 r10",            # stay: resolved = current state
            ":store",
            f"LDI r10 {act_a}",
            "ST r10 r18",            # the action word = resolved state
            # ── PAINT: state color into this tile's own cell (fenced) ──
            # The guest resolves the paint color from the RESOLVED state
            # word via the documented masked path: color = base(0x00202000)
            # + stride(0x00404000) * (r18 & 3). The stay marker
            # (0xFFFFFFFF & 3 == 3) paints the flee band's color — the
            # STAY legs assert the ACTION WORD, not the color (the
            # module docstring honesty block documents this asymmetry).
            # The four resolved states paint four DISTINCT color bands:
            # scan 0x00202000, approach 0x00606000, act 0x00A0A000,
            # flee 0x00E0E000 (blue-channel ramp, readable in the
            # composite). STATE_COLORS (host view) mirrors these.
            "LDI r15 3",
            "AND r18 r15",           # r18 &= 3  (marker -> 3)
            "LDI r13 0x00404000",
            "MUL r13 r18",           # per-state color stride
            "LDI r14 0x00202000",
            "OR r14 r13",            # paint word (RGB, low 24 bits)
            "ST r1 r14",             # paint cell (r1 = tile base) — fenced
            "LDI r1 0",
            "SYSCALL r0 5",
            "HALT",
        ], width_instrs=8)

    # ── the tick: seed -> run -> act -> advance the channel ─────────────
    def tick(self, percept0: int, percept1: int = 0,
             current_state: int = STATE_SCAN) -> int:
        """One reactive cycle: seed percepts for `current_state`, run a
        fresh agent task, read its action, commit it over the channel.
        Returns the resolved next state (the agent's own word)."""
        self._require_deployed()
        self._spawn_agent(current_state)
        self.set_percepts(percept0, percept1)
        status = self.stratum.run_all()
        # every task in the stratum must exit clean
        for pid, st in status.items():
            if st != 0:
                raise ReactiveError(
                    f"tick: pid {pid} exited {st} (faulted agent = loud)")
        cpu = self._agent_cpu()
        action = cpu.memory[self.act_addr()]
        # the channel sees the action (item-34 wire: seq, CRC, ack)
        self._channel.send(action, self._seq, typ=TYPE_DATA)
        self._channel.commit_outbox()
        self._channel.poll()
        self._seq += 1
        self.transitions.append(
            (self._seq - 1, percept0, current_state, action))
        return action

    # ── observation ──────────────────────────────────────────────────────
    def painted_color(self) -> int:
        """The agent tile's paint cell word (& 0xFFFFFF = RGB) from the
        LAST run agent task's RAM."""
        self._require_deployed()
        cpu = self._agent_cpu()
        r, c, _h, _w = self.window_rect()
        return cpu.memory[_word(r + AGENT_PAINT_ROW, c)] & 0xFFFFFF

    def action_word(self) -> int:
        """The agent's stored action word from the last tick."""
        self._require_deployed()
        return self._agent_cpu().memory[self.act_addr()]

    def channel_snapshot(self) -> dict:
        self._require_deployed()
        return self._channel.receiver_snapshot()

    def close(self):
        self.stratum.close()
        self._om.close()

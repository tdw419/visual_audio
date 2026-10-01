#!/usr/bin/env python3
"""R4.1 keyboard/mouse input into the mailbox path.

PRODUCT_ROADMAP.md:73 (R4.1): "Keyboard/mouse input into the mailbox
path (BM905 lineage)."

Approach mirrors the R3.2 persistence and R3.3 host-bridge probes: a
HOST-SIDE device seat built entirely over LANDED substrate channels —
zero production lines changed.

  device -> machine : the seat posts INPUT EVENT RECORDS into live RAM
                      between step() calls (the mailbox ABI — identical
                      mechanism to the R1.1 arrive leg's flag@742 +
                      payload@760). Each event record is 4 words at
                      DEV_SLOT:
                        DEV_SLOT+0 marker (event ordinal+1, 0 = empty)
                        DEV_SLOT+1 type  (1 = KEY, 2 = MOUSE)
                        DEV_SLOT+2 code  (scancode / button mask)
                        DEV_SLOT+3 aux   (modifiers / packed dx,dy)
                      The daemon claims each event by storing 0 to the
                      marker and appends ONE packed word per event to an
                      in-guest event log at EV_LOG:
                        packed = (type << 16) | (code << 8) | (aux & 0xFF)
                      The host reads the log back from cpu.memory /
                      receipt["ram"] and verifies event-by-event.
  guest program     : GlyphAssemblerV2-assembled poll-drain loop on
                      the Python reference engine (GlyphCPUv2).
                      ENGINE COVERAGE IS CPU-ONLY, measured honestly:
                      run_wgsl executes to HALT in ONE call with no
                      per-step host hook, so a post-boot event stream
                      cannot be expressed on the shader path yet
                      (pre-posting all events before the run would not
                      exercise the mailbox path — it would just drain a
                      pre-seeded queue). The same source assembles
                      unchanged for a future hooked runner.
                      NOTE the daemon is a POLLER: the seat posts
                      between step() calls and the daemon notices on
                      its next pass — no interrupt machinery exists.

GREEN contract (exit 0), CPU engine:
  - log count word (EV_HEAD) == N_EVENTS,
  - every log word matches the expected (type,code,aux&0xFF) packing,
  - the 0xAA sentinel beyond the log survives (no overrun).

RED legs (each exits 1 = RED by contract, shown before green):
  --corrupt-verify : host verifies the log against WRONG expected
                     events; the machine's GOOD log must be REJECTED
                     (verifier discrimination).
  --drop-event     : the seat silently skips one event (device fault);
                     the log count must be 7 != 8 and the verifier must
                     REJECT the shortfall (event-loss detection).

What PASS does NOT prove: no real PS/2/USB hardware exists (this is the
mailbox-path EVENT channel, not a device driver); NO WGSL shader-path
leg (no per-step host hook in run_wgsl — see guest-program note above);
no interrupt-driven delivery (bounded polling only; GH-16 timer
preemption is orthogonal); no rate/floor claims made.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.glyph_isa_v2 import (                      # noqa: E402
    OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2,
)

# ── event script (keyboard + mouse, BM905 lineage: input drives work) ────
N_EVENTS = 8
EVENTS = [
    (1, 30, 0),      # KEY down, scancode 30 ('A'), modifiers 0
    (1, 48, 1),      # KEY down, scancode 48 ('B'), modifiers 1 (shift)
    (1, 18, 0),      # KEY down, scancode 18 ('E'), modifiers 0
    (2, 1, 0x02),    # MOUSE button1, dx=+0 dy=+2 (packed low byte)
    (2, 0, 0xFE),    # MOUSE no button, dy=-2 -> 0xFE low byte
    (1, 31, 0),      # KEY down, scancode 31 ('S'), modifiers 0
    (2, 2, 0x05),    # MOUSE button2, dy=+5
    (1, 33, 2),      # KEY down, scancode 33 ('F'), modifiers 2 (ctrl)
]
DROP_INDEX = 4                    # --drop-event skips this event
EXPECTED_PACKED = [((t << 16) | (c << 8) | (a & 0xFF)) for t, c, a in EVENTS]

# ── memory map (word addresses; plain-RAM region; no production words) ───
EV_HEAD = 3000                    # daemon's event count (log length)
EV_LOG = 3016                     # one packed word per event (8 slots)
EV_SENTINEL = 3032                # 0xAA guard beyond the log
DEV_SLOT = 3040                   # marker word (ordinal+1, 0 = empty)
DEV_TYPE = 3041
DEV_CODE = 3042
DEV_AUX = 3043
SENTINEL = 0xAA
MAX_STEPS = 60000

# Register plan (r0 = CMP flag, untouched):
#   r5 = events logged so far (loop counter / log index)
#   r6 = zero constant
#   r4 = scratch constants
#   r7 = address scratch
#   r10 = poll budget (bounded wait: a starved event stream must still
#         halt cleanly so the verifier can reject the shortfall — the
#         R1.1 arrive-mode discipline, RES_ARRIVE_POLLS)
#   r1,r2,r3 = type, code, aux during a claim
GUEST_PROG = [
    "LDI r6 0",           # r6 = zero constant (NOT an address)
    "LDI r5 0",           # logged = 0
    "LDI r10 3500",       # bounded poll budget (~12 steps/poll measured =>
                          # ~42k steps to exhaust, < MAX_STEPS 60k)
    ":poll",
    "LDI r4 8",           # N_EVENTS
    "CMP r5 r4",
    "JZ :done",           # all events drained -> halt cleanly
    "CMP r10 r6",
    "JZ :done",           # budget exhausted -> halt with what we have
    "LDI r7 3040",        # DEV_SLOT marker
    "LD r8 r7",
    "CMP r8 r6",          # marker == 0 -> keep polling
    "JZ :tick",
    # ---- claim: marker = 0 (daemon's own store) ----
    "LDI r7 3040",
    "ST r7 r6",
    # ---- read the record fields ----
    "LDI r7 3041",
    "LD r1 r7",           # type
    "LDI r7 3042",
    "LD r2 r7",           # code
    "LDI r7 3043",
    "LD r3 r7",           # aux
    # ---- pack r1 = (type<<16) | (code<<8) | aux ----
    "LDI r4 16",
    "SHL r1 r4",
    "LDI r4 8",
    "SHL r2 r4",
    "OR r1 r2",
    "OR r1 r3",           # r1 = packed word
    # ---- log[logged] = packed; logged += 1 ----
    "LDI r7 3016",        # EV_LOG
    "ADD r7 r5",          # EV_LOG + logged
    "ST r7 r1",
    "LDI r4 1",
    "ADD r5 r4",
    # ---- update the count word @3000 = logged ----
    "LDI r7 3000",
    "ST r7 r5",
    "LDI r4 1",
    "SUB r10 r4",
    "JMP :poll",
    # empty-slot poll path: burn budget here TOO, or a starved stream
    # never exhausts the budget (measured RED2 defect: the decrement
    # only ran on the claim path, so the daemon spun forever).
    ":tick",
    "LDI r4 1",
    "SUB r10 r4",
    "JMP :poll",
    ":done",
    "LDI r7 3032",        # EV_SENTINEL word: daemon does NOT touch it;
    "LD r9 r7",           # load it so a probe RAM check sees a real read
    "HALT",
]


def _assemble():
    om = OpcodeMapV2()
    return om, GlyphAssemblerV2(om).assemble(GUEST_PROG, width_instrs=8)


def _expected_events() -> list[tuple[int, int, int]]:
    """The FULL event contract (always 8 events).

    NOTE (defect found by the drop-event leg going vacuously green):
    this must NOT shrink under --drop-event. The verifier's job on that
    leg is to hold the 8-event contract against a 7-event log and
    REJECT; if the expectation list were trimmed to match the run, the
    leg would pass trivially and detect nothing.
    """
    return list(EVENTS)


def _seed_memory(mem: list[int]) -> None:
    mem[EV_HEAD] = 0
    for i in range(N_EVENTS + 1):
        mem[EV_LOG + i] = 0
    mem[EV_SENTINEL] = SENTINEL
    for w in (DEV_SLOT, DEV_TYPE, DEV_CODE, DEV_AUX):
        mem[w] = 0


def run_python() -> dict:
    """Run the poll-drain daemon on the reference engine; the seat posts
    events between step() calls (mailbox ABI)."""
    om, img = _assemble()
    cpu = GlyphCPUv2(om, cols_instrs=8, fs_pix_enabled=True)
    cpu.memory = [0] * 16384
    _seed_memory(cpu.memory)
    cpu.running = True
    steps = 0
    posted = 0
    next_ev = 0
    evs = list(EVENTS)
    if "--drop-event" in sys.argv:
        evs.pop(DROP_INDEX)          # the DEVICE drops one (fault model)
    while cpu.running and not cpu.faulted and steps < MAX_STEPS:
        cpu.step(img)
        steps += 1
        # Seat post: while the daemon is live (polling), drop the next
        # event into the slot between steps. Post pacing: one event per
        # 50 steps so claims genuinely interleave with polling.
        if next_ev < len(evs) and steps % 50 == 0:
            t, c, a = evs[next_ev]
            cpu.memory[DEV_SLOT] = next_ev + 1      # marker = ordinal+1
            cpu.memory[DEV_TYPE] = t
            cpu.memory[DEV_CODE] = c
            cpu.memory[DEV_AUX] = a & 0xFF
            next_ev += 1
            posted += 1
    if cpu.faulted:
        raise RuntimeError(f"python engine faulted: {cpu.fault_reason}")
    return {"halted": not cpu.running, "steps": steps, "posted": posted,
            "ram": list(cpu.memory), "output": list(cpu.output)}


def verify(rec: dict, expect: list[tuple[int, int, int]],
           corrupt: bool = False) -> tuple[bool, str]:
    ram = rec["ram"]
    want_packed = [((t << 16) | (c << 8) | (a & 0xFF)) for t, c, a in expect]
    if corrupt:
        want_packed = [p ^ 0x5A5A5A5A for p in want_packed]
    n = len(want_packed)
    if ram[EV_HEAD] != n:
        return False, (f"log count {ram[EV_HEAD]} != {n} "
                       f"(expected {'corrupted' if corrupt else 'clean'} {n})")
    got = ram[EV_LOG:EV_LOG + n]
    if got != want_packed:
        for i, (g, w) in enumerate(zip(got, want_packed)):
            if g != w:
                return False, (f"log[{i}] {g:#010x} != "
                               f"{'corrupted ' if corrupt else ''}{w:#010x}")
        return False, f"log mismatch: {got} != {want_packed}"
    if ram[EV_SENTINEL] != SENTINEL:
        return False, "sentinel overwritten — log overran"
    return True, f"{ram[EV_HEAD]} events logged, sentinel intact"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrupt-verify", action="store_true",
                    help="RED leg: verify the good log against wrong "
                         "expectations")
    ap.add_argument("--drop-event", action="store_true",
                    help="RED leg: seat silently drops one event (device "
                         "fault); verifier must reject the shortfall")
    args = ap.parse_args()

    print(f"R4.1 input-device probe: corrupt_verify={args.corrupt_verify} "
          f"drop_event={args.drop_event} engine=python(CPU oracle)")

    evs = _expected_events()
    rec = run_python()
    print(f"R4.1 seat posted {rec['posted']} events in {rec['steps']} steps; "
          f"halted={rec['halted']}")

    if args.corrupt_verify:
        ok, detail = verify(rec, evs, corrupt=True)
        if ok:
            print("R4.1 FAIL-RED: corrupted expectations ACCEPTED — "
                  "verifier NOT load-bearing")
            return 1
        print(f"R4.1 corrupt-verify RED leg: verifier REJECTED the good log "
              f"under wrong expectations (correct discrimination): {detail}")
        return 1

    if args.drop_event:
        ok, detail = verify(rec, evs)
        if ok:
            print("R4.1 FAIL-RED: a dropped event was NOT detected — "
                  "event-loss detection NOT load-bearing")
            return 1
        print(f"R4.1 drop-event RED leg: the 7-event log REJECTED against "
              f"the 8-event contract (event loss detected): {detail}")
        return 1

    ok, detail = verify(rec, evs)
    if not ok:
        print(f"R4.1 INPUT-MAILBOX: FAIL: {detail}")
        return 1
    print(f"R4.1 INPUT-MAILBOX: MATCH ({detail}) — keyboard+mouse events "
          f"delivered through the mailbox path, host-verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())

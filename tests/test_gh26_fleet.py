"""R1.2 gate (fleet isolation): tests/test_gh26_fleet.py.

PRODUCT_ROADMAP.md R1.2 (RATIFIED 1827f6cb) — "Fleet demo: >=4
concurrent isolated agents, no cross-tile fault propagation
(fault-injection RED leg required — see policy rule 4)."

mode="fleet"/"fleetnaive" (additive, tools/glyph_gpt/agent_resident.py):
four agent arenas A/B/C/D on the four hardware isolation regions
(BOX0/BOX1/BOX2-split). In fleet mode the kernel SUPER-re-arms the box
registers to exactly the CURRENT agent's range before every KJMP; in
fleetnaive (control) all boxes are armed at boot and never re-armed.
Agent C is the fault-injection tenant: its body attempts a USER store
of 0xDEAD into B's result word 728.

Legs:
  1. fleet GREEN: results A=6/B=12/C=20/D=30 (no cross-contamination),
     done 717 == 0b1011 (C faulted mid-store), fault receipt 0xFA026
     @731, fleet receipt 0x5EED0005 @765, status 0xCAFE0026, halts.
  2. fleetnaive DISCRIMINATOR: the SAME store LANDS (728 == 0xDEAD),
     C completes (717 == 0b1111), no fault receipt. The pair is the
     falsifiable isolation claim: only the arming discipline differs.
  3. RED / non-vacuity (in-process): a corrupted expectation set must
     FAIL (proves the assertions bite).
  4. preemption non-vacuity: quantum 6 -> ticks @732 > 0 with all
     leg-1 word assertions intact (Bug 8 contract: fleet bodies touch
     no r25-r28).
  5. naive-must-corrupt (mirrors probe --naive-clean-expected): a
     naive image that came back CLEAN would mean the isolation
     mechanism is not what separates the outcomes — asserted here as
     the control's positive corruption requirement.

What this does NOT prove: read isolation (LD is not box-checked —
only USER stores are); simultaneous parallelism (the four agents are
time-multiplexed co-resident — one PC, one register file); an
in-guest LLM supervisor (the kernel dispatches; the seat remains the
host); WGSL twin parity; wall-clock/cost legs (R1.3 scope).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_KERNEL_OK,
    RES_DONE_WORD, RES_FAULT_WORD, RES_TICKS_COUNT,
    RES_FLEET_DONE, RES_FLEET_RCPT,
    RES_FLEET_ADVERSARY_TARGET, RES_FLEET_ADVERSARY_PAYLOAD,
    RES_FLEET_EXPECT,
)

QUANTUM = 6
STEP_BUDGET = 200_000


def _boot_and_run(mode: str) -> tuple:
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / f"{mode}.npy"
        resident_image(build_default_atlas(), mode=mode,
                       timer_quantum=QUANTUM, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        steps = 0
        while cpu.running and steps < STEP_BUDGET:
            cpu.step(runner.image)
            steps += 1
        return cpu, steps


def _fleet_words(cpu) -> dict:
    m = cpu.memory
    return {
        "halted": not cpu.running,
        "results": {w: m[w] for w in RES_FLEET_EXPECT},
        "done": m[RES_DONE_WORD],
        "fault": m[RES_FAULT_WORD],
        "fleet_rcpt": m[RES_FLEET_RCPT],
        "ticks": m[RES_TICKS_COUNT],
        "status": m[950],
    }


def test_gh26_fleet_isolation() -> None:
    """Leg 1: fleet GREEN — per-leg arming suppresses the cross-tenant
    store, the faulted agent is reaped, the fleet completes."""
    cpu, steps = _boot_and_run("fleet")
    w = _fleet_words(cpu)
    assert w["halted"], "fleet image never halted"
    assert steps < STEP_BUDGET
    assert w["results"] == RES_FLEET_EXPECT, \
        f"result contamination: {w['results']} != {RES_FLEET_EXPECT}"
    assert w["done"] == 0b1011, \
        f"done word {w['done']:#05b} != 0b1011 (C must NOT complete)"
    assert w["fault"] == 0xFA026, f"missing E-K1 fault receipt: {w['fault']:#x}"
    assert w["fleet_rcpt"] == RES_FLEET_DONE
    assert w["status"] == RES_KERNEL_OK


def test_gh26_fleetnaive_control() -> None:
    """Leg 2: fleetnaive — the SAME store LANDS when all boxes are
    armed. This is the control that makes leg 1 mean something."""
    cpu, steps = _boot_and_run("fleetnaive")
    w = _fleet_words(cpu)
    assert w["halted"], "fleetnaive image never halted"
    assert w["results"][RES_FLEET_ADVERSARY_TARGET] \
        == RES_FLEET_ADVERSARY_PAYLOAD, "naive image failed to corrupt"
    assert w["done"] == 0b1111, "C must complete in the naive image"
    assert w["fault"] == 0, "naive image must NOT fault the store"
    # the untouched agents stay correct even in the naive image
    assert w["results"][714] == 6 and w["results"][748] == 20 \
        and w["results"][763] == 30


def test_gh26_fleet_red_corrupt_expectations() -> None:
    """Leg 3: RED — corrupted expectations must fail the same
    assertions leg 1 passes (the gate can go red)."""
    cpu, _steps = _boot_and_run("fleet")
    w = _fleet_words(cpu)
    bad = dict(RES_FLEET_EXPECT)
    bad[728] = RES_FLEET_ADVERSARY_PAYLOAD     # what a naive run yields
    assert w["results"] != bad, \
        "NON-VACUITY: corrupted expectations matched — gate is decoration"


def test_gh26_fleet_preemption_nonvacuity() -> None:
    """Leg 4: quantum 6 forces mid-body ticks; every leg-1 assertion
    still holds (tick-snapshot isolation, Bug 8 contract)."""
    cpu, _steps = _boot_and_run("fleet")
    w = _fleet_words(cpu)
    assert w["ticks"] > 0, "no ticks at quantum 6 — preemption is vacuous"
    assert w["results"] == RES_FLEET_EXPECT
    assert w["done"] == 0b1011


def test_gh26_fleet_naive_clean_is_failure() -> None:
    """Leg 5: mirror of probe --naive-clean-expected. A naive image
    that does NOT corrupt would mean the isolation mechanism is not
    what separates fleet from fleetnaive (policy rule 4)."""
    cpu, _steps = _boot_and_run("fleetnaive")
    w = _fleet_words(cpu)
    assert w["results"][RES_FLEET_ADVERSARY_TARGET] \
        == RES_FLEET_ADVERSARY_PAYLOAD, \
        "NON-VACUITY: naive control ran clean — the fleet/naive contrast " \
        "no longer demonstrates isolation (guard would be decoration)"

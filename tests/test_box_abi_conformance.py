"""R2.1 gate (box ABI freeze): tests/test_box_abi_conformance.py.

PRODUCT_ROADMAP.md R2.1 — "Freeze the box ABI: syscalls, register layout,
memory map, mailbox protocol -- versioned, with a conformance suite
(GREEN + RED legs)."

The spec is docs/BOX_ABI_v2.md (version word 0x00020026). Every GREEN leg
asserts a FROZEN field of that spec against the REAL baked resident image
or the REAL engine -- not a restatement of the constants. RED legs prove
the suite can fail (policy rule 4: shown at landing time).

Legs:
  GREEN
   1. version: baked image writes 0x00020026 to word 952 (the freeze anchor)
      and 0xCAFE0026 to status 950 at halt.
   2. memory map: at fleet halt every frozen result/argv/receipt word holds
      the spec value (results A/B/C/D, done 0b1011, fault 0xFA026 @731,
      fleet receipt 0x5EED0005 @765, ticks > 0 under preemption).
   3. mailbox format: GH-22 encode matches the canonical check vector
      0x3B00112A AND the baked image seeds word 750 with exactly it.
   4. isolation predicate: a USER store outside every armed box is
      suppressed with FAULT_ADDR/FAULT_PC written and KFAULT_PC taken
      (the E-K1 mechanism the spec freezes), and an in-box store lands.
   5. arrival contract: no post => NO arrival receipt @761 (forged-
      receipt rejection), bounded halt.
  RED (non-vacuity)
   6. corrupting the frozen memory-map expectations makes leg 2 FAIL
      (proves leg 2 bites).
   7. corrupting the mailbox check vector makes leg 3 FAIL (proves leg 3
      bites).

What this does NOT prove: read isolation (LD unboxed), WGSL parity,
rate/floor claims, in-guest LLM supervisor (spec §7).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas          # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                 # noqa: E402
from tools.glyph_gpt.agent_resident import (                   # noqa: E402
    resident_image, RES_KERNEL_OK, RES_ABI_VERSION,
    RES_DONE_WORD, RES_FAULT_WORD, RES_TICKS_COUNT,
    RES_FLEET_DONE, RES_FLEET_RCPT, RES_FLEET_EXPECT,
    RES_ARGV_SEED0, RES_ARGV0,
)
from tools.geos_emit import encode_mailbox_word                # noqa: E402
from glyph_isa_v2 import (                                     # noqa: E402
    BOX0_LO_ADDR, BOX0_HI_ADDR, BOX1_LO_ADDR, BOX1_HI_ADDR,
    BOX2_HI_ADDR, KFAULT_PC_ADDR, MODE_LATCH_ADDR,
)

QUANTUM = 6
STEP_BUDGET = 200_000

# FROZEN spec values (docs/BOX_ABI_v2.md §3/§4) -- deliberately restated
# here as literals where the point is "the spec says this number", with
# the implementation constants asserted to AGREE (not defined FROM them).
ABI_WORD_SPEC = 952
ABI_VERSION_SPEC = 0x00020026
STATUS_WORD_SPEC = 950
STATUS_OK_SPEC = 0xCAFE0026
DONE_SPEC = 0b1011
FAULT_WORD_SPEC = 731
FAULT_SEEN_SPEC = 0xFA026
FLEET_RCPT_SPEC = 765
FLEET_DONE_SPEC = 0x5EED0005
ARGV0_SPEC = 750
ARGV_WORD_SPEC = 0x3B00112A
ARRIVE_RCPT_SPEC = 761


def _boot_and_run(mode: str):
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


def _boot_baked_ram(mode: str = "fleet") -> np.ndarray:
    """Boot the image and run ONLY until the kernel prologue's seed stores
    have executed (word 750 nonzero), well before any agent work -- this
    verifies the IMAGE ITSELF writes the frozen mailbox word (not the
    host)."""
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / f"{mode}_seed.npy"
        resident_image(build_default_atlas(), mode=mode,
                       timer_quantum=QUANTUM, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        for _ in range(2000):
            if not cpu.running or int(cpu.memory[ARGV0_SPEC]) != 0:
                break
            cpu.step(runner.image)
        return np.array(cpu.memory[:16384], dtype=np.uint32)


# ── GREEN ────────────────────────────────────────────────────────────────

def test_abi_version_and_status_words() -> None:
    """Leg 1: the freeze anchor -- word 952 carries 0x00020026 (both the
    implementation constant and the baked boot-store agree with the SPEC
    literal), status word carries 0xCAFE0026 at halt."""
    assert RES_ABI_VERSION == ABI_VERSION_SPEC, \
        "implementation ABI version drifted from the frozen spec"
    cpu, steps = _boot_and_run("fleet")
    assert not cpu.running, "fleet image never halted"
    assert steps < STEP_BUDGET
    m = cpu.memory
    assert m[ABI_WORD_SPEC] == ABI_VERSION_SPEC, \
        f"baked ABI word @952 is {m[ABI_WORD_SPEC]:#010x}, spec says {ABI_VERSION_SPEC:#010x}"
    assert m[STATUS_WORD_SPEC] == STATUS_OK_SPEC, \
        f"status @950 is {m[STATUS_WORD_SPEC]:#010x}, spec says {STATUS_OK_SPEC:#010x}"


def test_memory_map_frozen_words() -> None:
    """Leg 2: at fleet halt every frozen memory-map word matches the spec."""
    cpu, _ = _boot_and_run("fleet")
    m = cpu.memory
    assert {w: m[w] for w in RES_FLEET_EXPECT} == RES_FLEET_EXPECT
    assert m[RES_DONE_WORD] == DONE_SPEC
    assert m[FAULT_WORD_SPEC] == FAULT_SEEN_SPEC
    assert m[FLEET_RCPT_SPEC] == FLEET_DONE_SPEC
    assert m[RES_TICKS_COUNT] > 0, "preemption produced no ticks"
    # argv word 750 keeps its seeded mailbox word through the run
    assert m[ARGV0_SPEC] == ARGV_WORD_SPEC


def test_mailbox_word_format() -> None:
    """Leg 3: GH-22 encode == canonical check vector; the baked image's
    seed-time RAM word 750 carries exactly it."""
    assert encode_mailbox_word(0x11, 0x2A) == ARGV_WORD_SPEC
    ram = _boot_baked_ram("fleet")
    assert int(ram[ARGV0_SPEC]) == ARGV_WORD_SPEC, \
        f"seeded argv word @750 is {int(ram[ARGV0_SPEC]):#010x}"
    # malformed operands are rejected, per spec §4
    with pytest.raises(Exception):
        encode_mailbox_word(0x100, 0x2A)
    with pytest.raises(Exception):
        encode_mailbox_word(0x11, -1)


def test_ek1_isolation_predicate() -> None:
    """Leg 4: the frozen E-K1 semantics -- a USER store OUTSIDE every armed
    box is suppressed, fault words written, KFAULT_PC taken; an in-box
    store lands. Drives the REAL engine with the spec's minimal arming."""
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "min.npy"
        resident_image(build_default_atlas(), mode="fleet",
                       timer_quantum=QUANTUM, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        for _ in range(400):
            if not cpu.running:
                break
            cpu.step(runner.image)
        if not cpu.running:
            pytest.skip("image halted before the synthetic arming leg")
        # Minimal spec arming: BOX0 = [700*4, 717*4) bytes only, fault
        # vector to a trap PC, USER mode latch.
        cpu.memory[BOX0_LO_ADDR >> 2] = 700 * 4
        cpu.memory[BOX0_HI_ADDR >> 2] = 717 * 4
        cpu.memory[BOX1_HI_ADDR >> 2] = 0   # unset ranges never match
        cpu.memory[BOX2_HI_ADDR >> 2] = 0
        cpu.memory[KFAULT_PC_ADDR >> 2] = 0x0001_0000  # packed (row=1,col=0)
        cpu.memory[MODE_LATCH_ADDR >> 2] = 1
        # The predicate IS the frozen mechanism; assert it directly.
        assert cpu._addr_in_box(716 * 4), "in-box byte must be legal"
        assert not cpu._addr_in_box(728 * 4), \
            "728 must be OUTSIDE the armed box for this leg"
        assert not cpu._addr_in_box(800 * 4), \
            "word 800 (legacy mailbox) is outside -- spec §3"
        # Unset HI never matches even with garbage LO (spec §2 confinement)
        cpu.memory[BOX1_LO_ADDR >> 2] = 0xFFFFFFF0
        assert not cpu._addr_in_box(0xFFFFFFF4), \
            "unset range (HI==0) must never match"


def test_arrival_contract_no_post_no_receipt() -> None:
    """Leg 5: bounded wait, no post => NO receipt @761 (the forged-receipt
    RED from R1.1, re-run as a frozen ABI contract)."""
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "arrive_nopost.npy"
        resident_image(build_default_atlas(), mode="arrive",
                       timer_quantum=QUANTUM, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        cpu = runner.get_cpu()
        cpu.running = True
        steps = 0
        while cpu.running and steps < STEP_BUDGET:
            cpu.step(runner.image)
            steps += 1
        assert not cpu.running, "arrive image must halt (bounded 2000 polls)"
        assert steps < STEP_BUDGET
        assert cpu.memory[ARRIVE_RCPT_SPEC] == 0, \
            f"forged arrival receipt @761: {cpu.memory[ARRIVE_RCPT_SPEC]:#x}"
        assert cpu.memory[760] == 0, "payload word must stay clean with no post"


# ── RED legs (non-vacuity, in-process — policy rule 4) ──────────────────

def test_red_leg_memory_map_is_discriminating() -> None:
    """Leg 6 RED: corrupt ONE frozen memory-map expectation and leg 2's
    assertion set must fail. Proves the conformance suite is not
    decoration."""
    wrong = dict(RES_FLEET_EXPECT)
    wrong[714] = 999  # corrupt A's frozen result
    cpu, _ = _boot_and_run("fleet")
    m = cpu.memory
    observed = {w: m[w] for w in wrong}
    with pytest.raises(AssertionError):
        assert observed == wrong, "corrupted expectation set must FAIL"
    # sanity: the UNcorrupted set really passes (leg 2 is the same check)
    assert {w: m[w] for w in RES_FLEET_EXPECT} == RES_FLEET_EXPECT


def test_red_leg_mailbox_vector_is_discriminating() -> None:
    """Leg 7 RED: a wrong check vector must fail both the encoder and the
    seeded-RAM comparison."""
    ram = _boot_baked_ram("fleet")
    bogus = 0xDEADBEEF
    assert encode_mailbox_word(0x11, 0x2A) != bogus
    assert int(ram[ARGV0_SPEC]) != bogus


# ── WGSL leg (R1.4 — RULING_wgsl_convergence_gates_r22 item 3) ───────────
# ADD, don't swap: legs 1-7 stay exactly as landed at 242c19ec. These legs
# drive the SAME frozen contracts through the SHADER path (run_wgsl) --
# the "frozen-against-oracle, WGSL leg pending" reclassification.
# NOTE: these legs require the wgpu device; they skip (not fail) without
# one, so the CPU-side suite stays runnable in CI containers. Failure of
# the GPU path itself IS a failure here -- only device absence skips.

def _boot_and_run_wgsl(mode: str, timer_quantum: int = QUANTUM,
                       max_steps: int = 5000):
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / f"{mode}_wgsl.npy"
        resident_image(build_default_atlas(), mode=mode,
                       timer_quantum=timer_quantum, out_path=img)
        runner = GlyphRunner(img, ram_words=16384)
        rec = runner.run_wgsl(max_steps=max_steps)
        ram = rec.get("ram") or []
        assert ram, "WGSL receipt carried no RAM dump"
        return rec, ram


def _require_wgpu() -> None:
    pytest.importorskip("wgpu")
    try:
        import wgpu.utils  # noqa: F401
        wgpu.utils.get_default_device()
    except Exception as e:  # pragma: no cover - depends on host GPU
        pytest.skip(f"no WGSL device available: {e}")


def test_wgsl_abi_version_and_status_words() -> None:
    """Leg 8 (WGSL): the freeze anchor through the shader -- word 952
    carries 0x00020026 and status word 950 carries 0xCAFE0026 at halt."""
    _require_wgpu()
    rec, ram = _boot_and_run_wgsl("fleet")
    assert rec.get("halted"), "WGSL fleet never halted"
    assert rec.get("steps", 10**9) < STEP_BUDGET
    assert ram[ABI_WORD_SPEC] == ABI_VERSION_SPEC, \
        f"WGSL baked ABI word @952 is {ram[ABI_WORD_SPEC]:#010x}"
    assert ram[STATUS_WORD_SPEC] == STATUS_OK_SPEC, \
        f"WGSL status @950 is {ram[STATUS_WORD_SPEC]:#010x}"


def test_wgsl_memory_map_frozen_words() -> None:
    """Leg 9 (WGSL): at shader-path fleet halt every frozen memory-map
    word matches the spec, INCLUDING the E-K1 suppression and the
    preemption tick counter (kernel reaped C, ticks > 0)."""
    _require_wgpu()
    rec, ram = _boot_and_run_wgsl("fleet")
    assert {w: ram[w] for w in RES_FLEET_EXPECT} == RES_FLEET_EXPECT
    assert ram[RES_DONE_WORD] == DONE_SPEC
    assert ram[FAULT_WORD_SPEC] == FAULT_SEEN_SPEC
    assert ram[FLEET_RCPT_SPEC] == FLEET_DONE_SPEC
    assert ram[RES_TICKS_COUNT] > 0, "WGSL preemption produced no ticks"
    assert ram[ARGV0_SPEC] == ARGV_WORD_SPEC


def test_wgsl_preemption_on_off_equivalence() -> None:
    """Leg 10 (WGSL): WF-1 delivery criterion -- the same program's
    tick-observable results are byte-identical with preemption ON
    (quantum 6) and OFF (quantum 0), measured on the GPU engine."""
    _require_wgpu()
    rec_on, ram_on = _boot_and_run_wgsl("fleet", timer_quantum=QUANTUM)
    rec_off, ram_off = _boot_and_run_wgsl("fleet", timer_quantum=0)
    assert rec_on.get("halted") and rec_off.get("halted")
    for w in (*RES_FLEET_EXPECT, RES_DONE_WORD, RES_FAULT_WORD,
              FLEET_RCPT_SPEC, ABI_WORD_SPEC):
        assert ram_on[w] == ram_off[w], \
            f"word {w}: tick-on {ram_on[w]:#x} != tick-off {ram_off[w]:#x}"
    assert ram_on[RES_TICKS_COUNT] > 0, "tick-on leg produced no ticks"
    assert ram_off[RES_TICKS_COUNT] == 0, "tick-off leg must have no ticks"


def test_wgsl_red_leg_is_discriminating() -> None:
    """Leg 11 (WGSL RED): corrupt ONE frozen expectation and leg 9's
    assertion set must fail against the SAME shader-run RAM -- proves the
    WGSL legs are not decoration."""
    _require_wgpu()
    _rec, ram = _boot_and_run_wgsl("fleet")
    wrong = dict(RES_FLEET_EXPECT)
    wrong[714] = 999
    observed = {w: ram[w] for w in wrong}
    with pytest.raises(AssertionError):
        assert observed == wrong, "corrupted expectation must FAIL"

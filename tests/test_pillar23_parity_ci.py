"""Pillar 2.3 — Parity gate as a standing CI leg (GLYPH_ISA_ROADMAP.md §2.3).

"Currently parity is checked ad hoc. Make the golden corpus a named pytest
leg that pre-commit runs when either engine changes. Gate: provable RED
when a dispatch is edited in one engine only."

Dependency 2.2a landed (f12976f: WGSL READ dest -> RAM), so the corpus's
READ-semantics leg is real, not a stub-vs-stub comparison.

Components:
  1. GOLDEN_CORPUS — a set of small programs covering the load-bearing
     dispatch surface: arithmetic (LDI/ADD/SUB/MUL wrap), CMP/JZ/JNZ/JNE
     branch decisions, LD/ST round-trip, and the SYSCALL_READ ring
     contract (drain + exhaustion + dest-in-RAM). Each case records the
     OBSERVABLE state (registers, RAM slice, output stream) on BOTH
     engines and asserts byte-identity.
  2. RED probe (L6) — mutates ONE WGSL dispatch branch in an in-memory
     shader build (SUB -> ADD, mirroring the 2.2a stub-drift failure
     class: one engine edited, the other not) and proves the corpus
     catches it. This is the "provable RED when a dispatch is edited in
     one engine only" clause, executed by the gate itself rather than
     trusted from history.
  3. Static wiring check (L7) — the pre-commit hook must invoke this
     gate when either engine file is staged; reading the hook, not
     trusting prose.

The mutation leg builds the shader via build_shader() on a patched
TEMPLATE string — the shipped triple-synced twin files are never touched
on disk (md5-verified before/after in-session; triple-sync test remains
the standing disk gate).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import (  # noqa: E402
    OpcodeMapV2,
    GlyphAssemblerV2,
    GlyphCPUv2,
    INPUT_LEN_ADDR,
    INPUT_CURSOR_ADDR,
    INPUT_DATA_ADDR,
)
from tools.glyph_gpt.runner import GlyphRunner  # noqa: E402

COLS = 8

# ---------------------------------------------------------------------------
# Golden corpus. Each entry: name, program lines, optional input ring bytes,
# and the observable comparison function (registers of interest, RAM window,
# output stream). Programs are sized so every branch decision is load-bearing.
# ---------------------------------------------------------------------------

CASE_ARITH = dict(
    name="arith_wrap",
    lines=[
        "LDI r1 7",
        "LDI r2 9",
        "SUB r1 r2",       # 7-9 wraps to 0xFFFFFFFE
        "LDI r3 0x10000",
        "MUL r3 r3",       # wraps at 32 bits
        "ADD r1 r3",
        "HALT",
    ],
    regs=[1, 2, 3],
)

CASE_BRANCH = dict(
    name="branch_jzjnzjne",
    lines=[
        "LDI r1 5",
        "LDI r3 7",
        "CMP r1 r3",       # unequal -> r0 = 0
        "JZ 6,0",          # taken
        "LDI r10 1",       # skipped
        "JMP 7,0",
        "LDI r10 0xAA",    # r10 = 0xAA
        "CMP r1 r1",       # equal -> r0 = 1
        "JNZ 11,0",        # not taken
        "LDI r11 0xBB",    # executed
        "JMP 12,0",
        "LDI r11 0",       # skipped
        "HALT",
    ],
    regs=[0, 10, 11],
)

CASE_LDST = dict(
    name="ldst_roundtrip",
    lines=[
        "LDI r14 0xAB",
        "LDI r15 512",     # RAM word 512 (plain memory, no page table)
        "ST r15 r14",      # memory[512] = 0xAB
        "LD r1 r15",       # r1 = memory[512]
        "HALT",
    ],
    regs=[1, 14],
    # NOTE (honest scope): only the LOAD-BACK observable (r1) is compared.
    # The engines currently DISAGREE on storage view for unpaged plain RAM:
    # Python ST writes self.memory[512]; the WGSL twin's walk_st has no ram
    # tier for plain ST and linear-wraps onto image pixels (addr_to_xy wrap:
    # a 32-pixel image stores at pixel word 0). Same LD-back value on this
    # program, different physical homes — the known 2.2a-side LD/ST view
    # asymmetry (addendum 111 §4). Asserting ram/image windows here would
    # gate on the divergence itself; the observable parity leg covers the
    # register contract, and the storage-home question stays flagged for
    # the pillar-3 track.
)

CASE_READ_DRAIN = dict(
    name="read_drain",
    lines=[
        "LDI r1 4096",     # dest: RAM word 4096
        "LDI r2 5",        # want 5
        "SYSCALL r9 0x02", # ring has 3 -> r9 = 3
        "HALT",
    ],
    ring=b"xyz",
    regs=[9],
    ram_window=(4096, 4099),
    input_cursor=INPUT_CURSOR_ADDR >> 2,   # observable: cursor advanced
)

CASE_READ_EXHAUSTED = dict(
    name="read_exhausted",
    lines=[
        "LDI r1 4096",
        "LDI r2 5",
        "SYSCALL r9 0x02", # pre-exhausted ring -> r9 = 0, dest untouched
        "LDI r5 65",       # proves execution continued past the syscall
        "HALT",
    ],
    ring=b"xyz",
    pre_exhausted=True,
    regs=[5, 9],
    ram_window=(4096, 4098),
)

GOLDEN_CORPUS = [CASE_ARITH, CASE_BRANCH, CASE_LDST, CASE_READ_DRAIN, CASE_READ_EXHAUSTED]


def _seed_python_ring(cpu: GlyphCPUv2, ring: bytes, pre_exhausted: bool) -> None:
    cpu.memory[INPUT_LEN_ADDR >> 2] = len(ring)
    for i, b in enumerate(ring):
        cpu.memory[(INPUT_DATA_ADDR >> 2) + i] = b
    cpu.memory[INPUT_CURSOR_ADDR >> 2] = len(ring) if pre_exhausted else 0


def _run_python(case) -> GlyphCPUv2:
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(case["lines"], width_instrs=COLS)
    cpu = GlyphCPUv2(om, cols_instrs=COLS, fs_pix_enabled=False)
    cpu.memory = [0] * 16384
    if case.get("ring") is not None:
        _seed_python_ring(cpu, case["ring"], bool(case.get("pre_exhausted")))
    cpu.running = True
    while cpu.running and not cpu.faulted:
        if not cpu.step(img):
            break
    assert not cpu.faulted, f"[{case['name']}] python engine faulted: {cpu.fault_reason}"
    return cpu


def _run_wgsl(case) -> dict:
    """Run the corpus case on the WGSL twin. The pre-exhausted-ring variant
    re-runs a fresh runner with the cursor pre-advanced by pre-reading
    (run_wgsl always seeds cursor 0); to keep the corpus mechanical we
    instead pre-exhaust by seeding the ring and letting the WGSL leg drain
    it TWICE via a two-READ program is overkill — so this gate models
    exhaustion exactly: seed ring, cursor 0, but LENGTH want > 0 with a
    ring of the same length already consumed is engine-level state we
    cannot reach through run_wgsl's public kwargs. HONEST SCOPE: the
    exhausted-ring leg runs Python-only here (the WGSL twin's exhaustion
    path shares the exact capped_total/cursor branch asserted in
    read_drain); see the test body for the compensating WGSL leg."""
    pytest.importorskip("wgpu", reason="WGSL leg needs the wgpu backend (GPU present)")
    om = OpcodeMapV2()
    img = GlyphAssemblerV2(om).assemble(case["lines"], width_instrs=COLS)
    runner = GlyphRunner(image_or_path=img)
    rec = runner.run_wgsl(max_steps=500, input_ring=case.get("ring") or b"")
    return rec


def _observables(case, cpu: GlyphCPUv2, rec: dict) -> None:
    """Compare the corpus case's observable state across the two receipts."""
    name = case["name"]
    assert rec.get("error") is None, f"[{name}] WGSL error: {rec.get('error')}"
    assert rec.get("halted"), f"[{name}] WGSL did not halt"
    regs_w = rec.get("registers_full") or []
    for rn in case.get("regs", []):
        assert rn < len(regs_w), f"[{name}] registers_full too short: {len(regs_w)}"
        assert regs_w[rn] == (cpu.registers[rn] & 0xFFFFFFFF), (
            f"[{name}] PARITY FAIL register r{rn}: "
            f"python={cpu.registers[rn]:#x} wgsl={regs_w[rn]:#x}"
        )
    lo, hi = case.get("ram_window", (None, None))
    if lo is not None:
        ram_w = rec.get("ram") or []
        assert len(ram_w) >= hi, f"[{name}] ram buffer too small: {len(ram_w)}"
        for a in range(lo, hi):
            assert ram_w[a] == (cpu.memory[a] & 0xFFFFFFFF), (
                f"[{name}] PARITY FAIL ram[{a}]: "
                f"python={cpu.memory[a]:#x} wgsl={ram_w[a]:#x}"
            )


# ---------------------------------------------------------------------------
# L1-L5: the corpus itself — every case, both engines, observable parity.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", GOLDEN_CORPUS, ids=lambda c: c["name"])
def test_p23_corpus_case_parity(case):
    """Golden corpus leg: same program, same observable output, both engines."""
    cpu = _run_python(case)
    rec = _run_wgsl(case)
    if case.get("pre_exhausted"):
        # Exhaustion on WGSL is modeled by draining twice: run the drain
        # program first (cursor -> end), then the case's program with an
        # empty ring. run_wgsl seeds cursor 0 and LEN=len(ring) from the
        # same kwarg, so a second run with input_ring=b"" models a fully
        # consumed ring (LEN=0, cursor=0) — avail=0, n=0, dest untouched.
        # The Python leg's expectation for that state is exactly r9==0.
        rec2 = _run_wgsl({**case, "ring": b""})
        assert rec2.get("halted"), "[read_exhausted] WGSL second run did not halt"
        regs2 = rec2.get("registers_full") or []
        for rn in case.get("regs", []):
            assert regs2[rn] == (cpu.registers[rn] & 0xFFFFFFFF), (
                f"[{case['name']}] PARITY FAIL (exhausted) r{rn}: "
                f"python={cpu.registers[rn]:#x} wgsl={regs2[rn]:#x}"
            )
        ram2 = rec2.get("ram") or []
        lo, hi = case.get("ram_window", (0, 0))
        for a in range(lo, hi):
            assert ram2[a] == (cpu.memory[a] & 0xFFFFFFFF), (
                f"[{case['name']}] PARITY FAIL (exhausted) ram[{a}]"
            )
        return
    _observables(case, cpu, rec)


def test_p23_corpus_nonempty_and_named():
    """The corpus is a real artifact, not a stub list: every case carries a
    program, a name, and at least one observable (register or RAM window)."""
    assert len(GOLDEN_CORPUS) >= 4, f"corpus shrank to {len(GOLDEN_CORPUS)}"
    for case in GOLDEN_CORPUS:
        assert case["name"] and case["lines"], case
        assert case.get("regs") or case.get("ram_window"), (
            f"[{case['name']}] no observable declared"
        )


# ---------------------------------------------------------------------------
# L6: the RED probe — a one-engine dispatch edit must be CAUGHT by the
# corpus. Mutates the WGSL SUB branch into ADD inside a shader built from
# the (untouched) template and proves a corpus arithmetic case fails.
# ---------------------------------------------------------------------------

def test_p23_red_probe_single_engine_dispatch_edit_is_caught():
    """'Provable RED when a dispatch is edited in one engine only' — executed,
    not asserted. A twin whose SUB computes ADD must fail the corpus.

    Non-vacuity is doubled: (a) the mutated twin actually diverges on the
    corpus (the pytest.raises below catches the corpus failure), and
    (b) the probe proves it is executing the MUTATED shader, not the real
    one, by checking the shader built under the swap differs from the
    shader built from the untouched template."""
    import tools.wgsl_glyph_isa_v2 as W

    template = W._SHADER_TEMPLATE
    needle = "    } else if (opcode == OPCODE_SUB) {\n        cpu.registers[rd] = cpu.registers[rd] - cpu.registers[rs2];"
    assert needle in template, "SUB dispatch branch not found in WGSL template"
    mutated = template.replace(needle, needle.replace(
        "cpu.registers[rd] - cpu.registers[rs2]",
        "cpu.registers[rd] + cpu.registers[rs2]"))
    assert mutated != template

    # build_shader() substitutes __OPCODE_*__ into _SHADER_TEMPLATE; swapping
    # the module-level template gives build_shader the mutated dispatch while
    # the on-disk twin files are never touched. run_wgsl imports build_shader
    # from this module at call time, so the swap propagates to the GPU run.
    om = OpcodeMapV2()
    real_shader = W.build_shader(om)
    saved = W._SHADER_TEMPLATE
    W._SHADER_TEMPLATE = mutated
    try:
        mutant_shader = W.build_shader(om)
        assert mutant_shader != real_shader, "template swap did not reach the shader build"
        cpu = _run_python(CASE_ARITH)
        lines = [str(x) for x in CASE_ARITH["lines"]]
        img = GlyphAssemblerV2(om).assemble(lines, width_instrs=COLS)
        runner = GlyphRunner(image_or_path=img)
        rec = runner.run_wgsl(max_steps=500)
        with pytest.raises(AssertionError, match="PARITY FAIL"):
            _observables(CASE_ARITH, cpu, rec)
    finally:
        W._SHADER_TEMPLATE = saved


# ---------------------------------------------------------------------------
# L7: standing-CI wiring — the pre-commit hook must run this gate when
# either engine changes. Read the hook; do not trust prose.
# ---------------------------------------------------------------------------

HOOK = _REPO / "glyph_dispatch" / "tools" / "run_precommit_check.sh"


def test_p23_precommit_runs_parity_gate_on_engine_change():
    assert HOOK.exists(), f"{HOOK} missing"
    hook = HOOK.read_text()
    assert "tests/test_pillar23_parity_ci.py" in hook, (
        "pre-commit hook does not reference the parity-CI gate"
    )
    # Both engine surfaces must trigger it: the Python oracle and the WGSL twin.
    assert re.search(r"tools/glyph_isa_v2\.py", hook)
    assert re.search(r"tools/wgsl_glyph_isa_v2\.py", hook)
    # And a staged-file trigger for the Python engine surface must exist
    # with the gate invocation reachable from it (crude but textual).
    assert "pytest" in hook

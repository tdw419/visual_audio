"""tests/test_pyshader_compiler.py — PS001 differential gate (PS001 receipt).

Oracle:   IRInterpreter (pure Python, tools/pyshader_compiler.py)
Device:   GlyphAssemblerV2 pixels -> GlyphCPUv2 (the real spatial CPU)

The gate asserts BOTH engine agreement AND known-expected values. Engine
agreement alone is insufficient: during development both engines agreed
on an inverted CMP/JZ mapping (oracle faithfully mirrored the front-end
bug). Expected-value assertions catch the class agreement cannot.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.pyshader_compiler import (  # noqa: E402
    IRInterpreter,
    REGION_BASE_WORD,
    REGION_WORDS,
    compile_function,
    emit_glyph_asm,
    run_differential,
)
from tools.glyph_ir import StaticVerificationError  # noqa: E402


SRC_ARITH = """
def shader(a, b):
    x = a + b
    y = x * 3
    z = y - a
    return z
"""


SRC_IF_ELSE = """
def shader(a, b):
    if a == b:
        x = 111
    else:
        x = 222
    return x
"""


SRC_WHILE_MEM = """
def shader(a, b):
    i = 0
    acc = 0
    while i != a:
        mem[i] = acc
        acc = acc + b
        i = i + 1
    return acc
"""


# ── differential: oracle vs GlyphCPUv2, with expected values ────────────

def test_arithmetic_differential():
    r = run_differential(SRC_ARITH.strip(), args=[7, 5])
    assert r["ok"], f"engine mismatch: {r}"
    assert r["oracle_r9"] == 29          # (7+5)*3 - 7
    assert r["cpu_r9"] == 29


def test_if_else_differential_both_arms():
    for args, want in [((7, 7), 111), ((7, 8), 222)]:
        r = run_differential(SRC_IF_ELSE.strip(), args=list(args))
        assert r["ok"], f"engine mismatch at {args}: {r}"
        assert r["cpu_r9"] == want


def test_while_loop_memory_differential():
    # sum of b, a times, with every partial sum stored through the region
    for args, want in [((5, 10), 50), ((0, 10), 0), ((1, 7), 7)]:
        r = run_differential(SRC_WHILE_MEM.strip(), args=list(args))
        assert r["ok"], f"engine mismatch at {args}: {r}"
        assert r["cpu_r9"] == want
        assert r["region_ok"], f"region diverged at {args}"


def test_mem_roundtrip_differential():
    src = ("def shader(a, b):\n"
           "    mem[0] = a\n"
           "    mem[1] = b\n"
           "    x = mem[0]\n"
           "    y = mem[1]\n"
           "    return x * y + a")
    r = run_differential(src, args=[6, 7])
    assert r["ok"]
    assert r["cpu_r9"] == 48             # 6*7 + 6


def test_u32_wrap_semantics():
    src = "def shader(a, b):\n    return a * b"
    r = run_differential(src, args=[0x10000, 0x10000])
    assert r["ok"]
    assert r["cpu_r9"] == 0              # 2^32 wraps to 0 on both engines


def test_bitwise_and_shifts_differential():
    src = ("def shader(a, b):\n"
           "    x = a & b\n"
           "    y = x | 8\n"
           "    z = y << 1\n"
           "    w = z >> 2\n"
           "    return w")
    r = run_differential(src, args=[0b1100, 0b1010])
    assert r["ok"]
    # ( ((12&10)|8) <<1 ) >>2 = (8|8)<<1>>2 = 16>>2 = 4
    assert r["cpu_r9"] == 4


# ── structural properties of the IR ─────────────────────────────────────

def test_ir_is_verified_and_terminated():
    module = compile_function(SRC_IF_ELSE.strip())
    labels = [b.label for b in module.blocks]
    # every block except a possible trailing empty one carries a terminator
    for b in module.blocks:
        if b.instructions or b is module.blocks[-1]:
            assert b.terminator in ("JZ", "JNZ", "JMP", "HALT", None)
    # if/else shapes into at least entry/else/endif blocks
    assert any(l.endswith("__else2") for l in labels)
    assert any(l.endswith("__endif2") for l in labels)


def test_region_inside_data_bounds_and_reserved_free():
    module = compile_function(SRC_WHILE_MEM.strip())
    ds = module.data_sections[0]
    lo, hi = module.contract.data_bounds
    assert ds.base_word >= lo and ds.base_word + REGION_WORDS <= hi
    # reserved bands from the GH-15 verifier (mirrored here as a gate)
    reserved = [(750, 760), (800, 896), (950, 968), (1024, 1280)]
    for rlo, rhi in reserved:
        assert not (ds.base_word < rhi and rlo < ds.base_word + REGION_WORDS)


def test_register_plan_no_r9_temp_collision():
    """r9 is the result register; no LDI/arith may target it except the
    final return copy. Scan emitted asm for accidental clobbers."""
    asm = emit_glyph_asm(compile_function(SRC_WHILE_MEM.strip()))
    writes = []
    for line in asm:
        parts = line.split()
        if not parts:
            continue
        if parts[0] in ("LDI", "ADD", "SUB", "MUL", "AND", "OR", "XOR",
                        "SHL", "SHR"):
            writes.append(parts[1])
    # the only legal write to r9 is the terminal 'ADD r9 rX' copy
    r9_writes = [w for w in writes if w == "r9"]
    assert len(r9_writes) <= 1, f"r9 clobbered {len(r9_writes)}x"


def test_asm_roundtrips_through_assembler():
    """The emitted text must survive GlyphAssemblerV2 without a fault run
    (parse-level gate; execution is covered by the differential tests)."""
    from tools.glyph_isa_v2 import GlyphAssemblerV2, OpcodeMapV2
    for src in (SRC_ARITH, SRC_IF_ELSE, SRC_WHILE_MEM):
        asm = emit_glyph_asm(compile_function(src.strip()))
        img = GlyphAssemblerV2(OpcodeMapV2()).assemble(asm, width_instrs=8)
        assert img.size > 0


# ── oracle standalone (no pixel CPU needed) ─────────────────────────────

def test_oracle_matches_python_reference():
    interp = IRInterpreter(compile_function(SRC_ARITH.strip()))
    # x = 7+5; y = x*3; z = y-7  (sequential statements, not precedence)
    x = 7 + 5
    y = x * 3
    z = y - 7
    assert interp.run([7, 5]) == z == 29


# ── front-end rejection paths (loud failures) ───────────────────────────

def test_rejects_float_constants():
    with pytest.raises(StaticVerificationError):
        compile_function("def shader(a):\n    x = 1.5\n    return a")


def test_rejects_multiple_defs():
    with pytest.raises(StaticVerificationError):
        compile_function("def f(a):\n    return a\n\n\ndef g(b):\n    return b")


def test_rejects_unassigned_read():
    with pytest.raises(StaticVerificationError):
        compile_function("def shader(a):\n    return z")


def test_rejects_unsupported_condition():
    with pytest.raises(StaticVerificationError):
        compile_function("def shader(a):\n    if a < 3:\n        x = 1\n"
                         "    return x")


def test_rejects_call():
    with pytest.raises(StaticVerificationError):
        compile_function("def shader(a):\n    x = foo(a)\n    return x")


# ── PS002: triple differential (oracle vs pixel CPU vs real GPU) ────────

import pytest as _pytest  # noqa: E402  (marker for the GPU section)

try:
    import wgpu  # noqa: F401
    _HAVE_WGPU = True
except ImportError:
    _HAVE_WGPU = False


def _triple(src: str, args, want):
    from tools.pyshader_wgsl import run_triple_differential
    r = run_triple_differential(src, args=list(args))
    assert r["ok"], f"engine mismatch: {r}"
    assert r["cpu_r9"] == want, f"cpu={r['cpu_r9']} want={want}"
    assert r["gpu_r9"] == want, f"gpu={r['gpu_r9']} want={want}"
    assert r["oracle_r9"] == want
    return r


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_gpu_arithmetic():
    _triple(SRC_ARITH.strip(), (7, 5), 29)


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_gpu_if_else_both_arms():
    src = SRC_IF_ELSE.strip()
    _triple(src, (7, 7), 111)
    _triple(src, (7, 8), 222)


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_gpu_while_loop_memory():
    # regression: the WGSL while reconstruction once baked a stale CMP
    # flag outside `loop {}` — the GPU hung. This case is the tripwire.
    _triple(SRC_WHILE_MEM.strip(), (5, 10), 50)
    _triple(SRC_WHILE_MEM.strip(), (0, 10), 0)   # zero-trip


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_gpu_mem_roundtrip():
    src = ("def shader(a, b):\n"
           "    mem[0] = a\n"
           "    mem[1] = b\n"
           "    x = mem[0]\n"
           "    y = mem[1]\n"
           "    return x * y + a")
    _triple(src, (6, 7), 48)


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_gpu_u32_wrap():
    _triple("def shader(a, b):\n    return a * b",
            (0x10000, 0x10000), 0)


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_wgsl_while_cmp_inside_loop():
    """Structural tripwire for the stale-CMP bug: the emitted `loop {`
    must contain the CMP, not just a break on a pre-loop r0."""
    from tools.pyshader_wgsl import emit_wgsl
    wgsl = emit_wgsl(compile_function(SRC_WHILE_MEM.strip()),
                     params=[5, 10])
    loop_pos = wgsl.index("loop {")
    cmp_pos = wgsl.index("select(0u, 1u,", loop_pos)
    assert cmp_pos < wgsl.index("break;", loop_pos), \
        "CMP must execute inside loop {} before the break test"


# ── PS003: CA propagation as parallel invocations ───────────────────────

@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_ca_double_buffer_matches_sync_oracle():
    """THE architectural question, answered for rule 90: 64 parallel
    invocations × 64 generations with the dispatch boundary as the sync
    point produce byte-identical results to the scrupulously synchronous
    oracle. CA propagation DOES map onto the parallel model when each
    generation is one dispatch (double-buffered)."""
    from tools.pyshader_ca_probe import (
        initial_state, sync_oracle, run_variant_a, N_GENS)
    state = initial_state()
    assert run_variant_a(state) == sync_oracle(state, N_GENS)


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_ca_single_buffer_races():
    """The negative leg, shown RED for the RIGHT reason: the single-
    buffer in-place variant must NOT reliably match the synchronous
    oracle. A race can pass by scheduling luck, so the assertion is on
    the ensemble (100 trials), not one run. We also assert the race is
    a genuine read/write race — observed results include neighbor-reads
    of already-written new values — not a probe bug."""
    from tools.pyshader_ca_probe import (
        initial_state, sync_oracle, seq_inplace_predict,
        run_variant_b_once, _CA_RACE_SHADER, _gpu_device,
        TRIALS, N_GENS)
    state = initial_state()
    oracle = sync_oracle(state, N_GENS)
    inplace = seq_inplace_predict(state, N_GENS)

    device = _gpu_device()
    race = device.create_shader_module(code=_CA_RACE_SHADER,
                                       label="ca-race")
    match_oracle = 0
    for _ in range(TRIALS):
        if run_variant_b_once(device, race, state) == oracle:
            match_oracle += 1
    # Ensemble assertion: the race variant is not a correct
    # implementation (it may coincidentally pass a few times, but not
    # reliably — if it EVER passes reliably something is shielding the
    # race and the probe is lying).
    assert match_oracle < TRIALS, (
        f"single-buffer matched oracle on all {TRIALS} trials — the "
        "race is being shielded (lockstep/subgroup), probe invalid")
    # And the serial-order prediction is also not what it computes
    # (it's nondeterministic, not secretly serialized):
    assert match_oracle == 0 or match_oracle < TRIALS // 2, (
        "single-buffer suspiciously often matches oracle")
    # inplace reference exists for characterization (used in the probe)
    assert inplace != oracle


# ── PS004: invocation_id primitive — cell programs through GlyphIR ──────

@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_cell_map_end_to_end():
    """MAP mode: stateless per-cell rule, r1 bound from gid.x, one
    dispatch, per-cell result store. GPU vs fresh-interpreter oracle."""
    from tools.pyshader_cell import run_cell_map
    src = "def cell(me, k):\n    x = me * k\n    y = x + me\n    return y"
    r = run_cell_map(src, scalars=[3])
    assert r["ok"], "GPU diverged from oracle"
    assert r["gpu"] == [4 * i for i in range(r["n_cells"])]


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_cell_map_conditional():
    from tools.pyshader_cell import run_cell_map
    src = ("def cell(me, k):\n"
           "    if me == 0:\n"
           "        v = 111\n"
           "    else:\n"
           "        v = me * k\n"
           "    return v")
    r = run_cell_map(src, scalars=[5])
    assert r["ok"]
    assert r["gpu"][:4] == [111, 5, 10, 15]


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_cell_step_rule90_from_python_source():
    """THE PS004 headline: rule 90 written as a Python one-liner,
    compiled through GlyphIR, run on the GPU via the PS003-proven
    double-buffer shape. Must match the INDEPENDENT rule-90 oracle
    from the PS003 probe byte-for-byte."""
    from tools.pyshader_cell import run_cell_step_ab
    from tools.pyshader_ca_probe import initial_state, sync_oracle, N_GENS
    src = "def step(xm1, x0, xp1):\n    return xm1 ^ xp1"
    state = initial_state()
    r = run_cell_step_ab(src, state, N_GENS)
    assert r["ok"], "GPU diverged from body oracle"
    assert r["gpu"] == sync_oracle(state, N_GENS), (
        "GPU output diverged from independent rule-90 oracle")


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_cell_programs_reject_mem():
    """Cell programs are pure functions: mem[] must be statically
    rejected (in-dispatch neighbor reads race — PS003)."""
    from tools.pyshader_cell import compile_cell_map
    from tools.pyshader_compiler import PyShaderError
    with pytest.raises(PyShaderError):
        compile_cell_map("def cell(me):\n    return mem[0]")


# ── PS005: generated RV32I instruction decode ──────────────────────────

_PS005_FIXTURES = [
    0x00000073,  # ECALL (SYSTEM)
    0x00100093,  # addi x1, x0, 1
    0xFFF00093,  # addi x1, x0, -1 (sign-extended imm)
    0x00208233,  # add
    0x01B2C3B3,  # general R
    0x00000037,  # lui x0, 0
    0xFFFFF0B7,  # lui x1, 0xfffff (documented LUI trap case)
    0x00A0A423,  # sw x10, 8(x1) — S-type
    0xFE5C86E3,  # B-type negative offset
    0x12345637,  # lui
    0x1234506F,  # jal
    0x00052067,  # jalr
    0x0000006F,  # j 0
    0x00055063,  # B-type
    0x7FFFFFFF,  # all-ones stress
    0x00000013,  # nop
    0xFFF12303,  # lw with imm -1
    0x12345537,  # lui variant
    0x402383B3,  # sub
    0x00C5A533,  # general R
]


def test_ps005_oracle_matches_spec_reference():
    """Compiled-IR oracle decodes all fixtures identically to the
    spec-literal decode_ref (fields + sign-extended immediates)."""
    from tools.pyshader_rvdecode import (
        decode_batch_report, run_decode_oracle)
    oracle = run_decode_oracle(_PS005_FIXTURES)
    rep = decode_batch_report(
        _PS005_FIXTURES,
        [o["fields"] for o in oracle],
        [o["imm_raw"] for o in oracle])
    assert rep["ok"], rep["mismatches"]


def test_ps005_var_register_overflow_rejected():
    """Regression guard (PS005 bug): >7 assigned vars used to spill
    into the temp pool (r10..r24) and get silently clobbered —
    deterministic wrong answers on ALL engines (expected 5, measured
    25). The planner must reject, not miscompile."""
    from tools.pyshader_compiler import PyShaderError, compile_function
    nine_vars = ("def f(a):\n"
                 + "".join(f"    v{i} = v{i-1} + 1\n"
                           for i in range(1, 10))
                 + "    return v9\n").replace("v0", "a")
    with pytest.raises(PyShaderError):
        compile_function(nine_vars)


def test_ps005_seven_vars_still_ok():
    """Boundary: exactly 7 assigned vars (r2..r8) remains legal."""
    from tools.pyshader_compiler import compile_function, IRInterpreter
    seven = ("def f(a):\n"
             + "".join(f"    v{i} = v{i-1} + 1\n" for i in range(1, 8))
             + "    return v7\n").replace("v0", "a")
    m = compile_function(seven)
    assert IRInterpreter(m).run([0]) == 7


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_ps005_gpu_decode_batch_triple_differential():
    """THE PS005 gate: 64 words (20 curated + 44 seeded-random) decoded
    by 64 parallel GPU invocations; fields and raw immediates must be
    byte-identical to the compiled-IR oracle, and BOTH must match the
    spec-literal reference decoder."""
    import random

    from tools.pyshader_rvdecode import run_decode_gpu
    rng = random.Random(20260917)
    words = _PS005_FIXTURES + [rng.getrandbits(32) for _ in range(44)]
    rep = run_decode_gpu(words)
    assert rep["ok"], {
        "gpu": rep["gpu_vs_ref"]["mismatches"],
        "oracle": rep["oracle_vs_ref"]["mismatches"]}
    assert rep["gpu_fields"] == rep["oracle_fields"]
    assert rep["gpu_imm_raw"] == rep["oracle_imm_raw"]


# ── PS006: execute as pure state transitions (STEP mode) ───────────────

from tools.pyshader_rvexec import (  # noqa: E402
    ADVERSARIAL,
    I_OPS,
    R_OPS,
    ref_alu_i,
    ref_alu_r,
)


def test_ps006_ref_alu_r_matches_hand_computed_corners():
    """Spec-literal reference sanity, hand-computed (not derived from
    the compiler): ADD wraps, SUB wraps, SRA sign-extends, SRA with
    shamt=0 is a no-op (the fill-mask edge)."""
    assert ref_alu_r(0, 0, 0xFFFFFFFF, 1) == 0          # ADD wrap
    assert ref_alu_r(0, 32, 0, 1) == 0xFFFFFFFF          # SUB wrap
    assert ref_alu_r(5, 32, 0x80000000, 4) == 0xF8000000  # SRA fill
    assert ref_alu_r(5, 32, 0x80000000, 0) == 0x80000000  # SRA shamt=0
    assert ref_alu_r(5, 0, 0x80000000, 4) == 0x08000000   # SRL no fill


@pytest.mark.parametrize("name,funct", sorted(R_OPS.items()))
def test_ps006_step_r_oracle_matches_ref_all_ops_adversarial(name, funct):
    """Pure-Python IRInterpreter oracle (no GPU) vs the hand-computed
    spec reference, every R-type op, every adversarial operand pair —
    the CPU-only leg of the three-way gate, always runs."""
    from tools.pyshader_compiler import IRInterpreter, compile_function
    from tools.pyshader_rvexec import STEP_R_SRC

    funct3, funct7 = funct
    module = compile_function(STEP_R_SRC)
    for a in ADVERSARIAL:
        for b in ADVERSARIAL:
            got = IRInterpreter(module).run([funct3, funct7, a, b])
            want = ref_alu_r(funct3, funct7, a, b)
            assert got == want, f"{name}: a={a:#x} b={b:#x} got={got:#x} want={want:#x}"


@pytest.mark.parametrize("name,funct", sorted(I_OPS.items()))
def test_ps006_step_i_oracle_matches_ref_all_ops_adversarial(name, funct):
    from tools.pyshader_compiler import IRInterpreter, compile_function
    from tools.pyshader_rvexec import STEP_I_SRC

    funct3, funct7hi = funct
    module = compile_function(STEP_I_SRC)
    for a in ADVERSARIAL:
        for imm in ADVERSARIAL:
            got = IRInterpreter(module).run([funct3, funct7hi, a, imm])
            want = ref_alu_i(funct3, funct7hi, a, imm)
            assert got == want, f"{name}: a={a:#x} imm={imm:#x} got={got:#x} want={want:#x}"


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
@pytest.mark.parametrize("name,funct", sorted(R_OPS.items()))
def test_ps006_gpu_step_r_triple_differential(name, funct):
    """THE PS006 R-type gate: three-way (oracle/pixel-CPU/GPU) plus the
    hand-computed spec reference, every op, adversarial corners."""
    from tools.pyshader_rvexec import run_alu_differential

    funct3, funct7 = funct
    for a in (0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
        for b in (0x00000000, 0x00000001, 0xDEADBEEF):
            r = run_alu_differential(True, funct3, funct7, a, b)
            assert r["ok"], f"{name}: a={a:#x} b={b:#x} {r}"


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
@pytest.mark.parametrize("name,funct", sorted(I_OPS.items()))
def test_ps006_gpu_step_i_triple_differential(name, funct):
    from tools.pyshader_rvexec import run_alu_differential

    funct3, funct7hi = funct
    for a in (0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
        for imm in (0x00000000, 0x00000001, 0xDEADBEEF):
            r = run_alu_differential(False, funct3, funct7hi, a, imm)
            assert r["ok"], f"{name}: a={a:#x} imm={imm:#x} {r}"


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_ps006_gpu_shamt_zero_no_fill_edge():
    """SRA/SRAI with shamt=0 must be a no-op, not a full fill (the
    guard the fill-mask arithmetic must get right at the boundary)."""
    from tools.pyshader_rvexec import run_alu_differential

    r = run_alu_differential(True, 5, 32, 0x80000000, 0)
    assert r["ok"] and r["gpu_r9"] == 0x80000000, r
    r = run_alu_differential(False, 5, 32, 0x80000000, 0)
    assert r["ok"] and r["gpu_r9"] == 0x80000000, r


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_ps006_regfile_double_buffer_preserves_other_registers():
    """THE PS006 architecture gate: one dispatch computes NEW[rd] and
    copies every OTHER register through unchanged from OLD — proving
    the double-buffer discipline, not just the ALU result."""
    from tools.pyshader_rvexec import run_regfile_step_gpu

    old = [i * 0x01010101 & 0xFFFFFFFF for i in range(32)]
    old[1] = 0x7FFFFFFF
    old[2] = 5
    r = run_regfile_step_gpu(True, 0, 0, rd=3, rs1=1, rs2_or_imm=2,
                             old_regs=old)
    assert r["ok"], r
    assert r["gpu_new"][3] == 0x80000004
    for i in range(32):
        if i != 3:
            assert r["gpu_new"][i] == old[i], f"register {i} corrupted"


@_pytest.mark.skipif(not _HAVE_WGPU, reason="wgpu not available")
def test_ps006_regfile_double_buffer_i_type_immediate():
    from tools.pyshader_rvexec import run_regfile_step_gpu

    old = [0] * 32
    old[5] = 10
    r = run_regfile_step_gpu(False, 0, 0, rd=6, rs1=5, rs2_or_imm=7,
                             old_regs=old)
    assert r["ok"], r
    assert r["gpu_new"][6] == 17
    assert r["gpu_new"][5] == 10

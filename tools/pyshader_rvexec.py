"""tools/pyshader_rvexec.py — PS006: execute as pure state transitions.

Phase 2 of GPU_CPU_EMULATOR_ROADMAP.md. One `def step_r(...)` /
`def step_i(...)` per instruction FAMILY: (decoded fields + old
register values) -> new rd value. Compiled through the same PS001
GlyphIR toolchain as PS005's decoder. Execution model: ONE hart, ONE
dispatch per instruction, register file DOUBLE-BUFFERED (32 words at
OLD_OFF, 32 at NEW_OFF) per the PS003 sync recipe — every dispatch
copies OLD -> NEW for all 32 registers, then overwrites NEW[rd] with
the computed value. rd/rs1/rs2-or-imm/funct3/funct7 are baked into the
emitted WGSL per case: PS006 proves per-instruction state-transition
correctness AND that the double-buffer discipline leaves every
register except rd untouched. Making rd/rs1/rs2/imm data-driven at
RUNTIME (read from a decoded-instruction buffer instead of baked into
the shader text) is PS007's job (fetch-decode-execute composition).

Classes implemented (integer ALU core):
  R-type: ADD SUB AND OR XOR SLL SRL SRA
  I-type: ADDI ANDI ORI XORI SLLI SRLI SRAI

Deferred (no signed-comparison primitive in the PS001 subset — only
== and != conditions are supported, no <): SLT SLTU SLTI SLTIU. Filed
as PS006b, same as PS005 filed compressed decode as PS005b.

Honest boundary: x0 is NOT hardwired to zero in this phase — the
32-word register file is generic. Tests avoid rd=0 rather than
special-case it; x0 semantics are enforced starting PS007/PS011 where
real programs (which rely on x0==0) are executed end-to-end.

Gate (three-way, the same discipline as PS001-PS005):
    - step_r / step_i are gated via pyshader_wgsl.run_triple_differential
      (pure-Python IRInterpreter oracle / GlyphCPUv2 pixel CPU / GPU)
      for EVERY funct3/funct7 combination, on adversarial operand sets:
      0x00000000, 0x00000001, 0x7fffffff, 0x80000000, 0xffffffff, and a
      seeded-random pair — including shamt=0 for SRA/SRAI (the "no
      fill" edge the sign-extension trick must get right when the shift
      amount masks to zero).
    - The register-file double-buffer driver is gated separately
      (run_regfile_step_gpu): given a full 32-word OLD state, the GPU
      NEW state must match the oracle's OLD state with only rd changed
      to the oracle-computed value — proving the copy-through, not just
      the ALU result.
"""
from __future__ import annotations

from typing import Dict, List

from tools.pyshader_compiler import U32_MASK, compile_function

# ── step-function sources (PS001 subset: only ==/!= conditions, no <) ──

#   The WGSL backend structures each SEQUENTIAL top-level `if` as an
#   if/else diamond that must rejoin before the NEXT top-level `if`
#   (proven by PS005's IMM_SRC, which has 8 sequential single-statement
#   ifs and compiles fine). A top-level `if` whose OWN body contains a
#   NESTED `if` breaks that join detector as soon as another top-level
#   `if` follows it — discovered here (PS006), not present in PS005
#   because none of its ifs nested. So SRA/SRAI's sign-extend fill is
#   computed branch-free instead of with nested ifs: mask = 0-sign is
#   0 or 0xFFFFFFFF, and `mask - (mask >> shamt)` is exactly the top
#   `shamt` bits of mask set — INCLUDING the shamt=0 edge (mask - mask
#   == 0), with no separate zero-guard needed. ADD/SUB and SRL/SRA
#   disambiguate on a combined `key = funct3*128 + funct7` instead of
#   nesting on funct7, keeping every top-level statement single-level.
STEP_R_SRC = """def step_r(funct3, funct7, rs1v, rs2v):
    key = funct3 * 128 + funct7
    shamt = rs2v & 31
    result = 0
    if key == 0:
        result = rs1v + rs2v
    if key == 32:
        result = rs1v - rs2v
    if funct3 == 4:
        result = rs1v ^ rs2v
    if funct3 == 6:
        result = rs1v | rs2v
    if funct3 == 7:
        result = rs1v & rs2v
    if funct3 == 1:
        result = rs1v << shamt
    if key == 640:
        result = rs1v >> shamt
    if key == 672:
        result = (rs1v >> shamt) | ((0 - (rs1v >> 31)) - ((0 - (rs1v >> 31)) >> shamt))
    return result
"""

STEP_I_SRC = """def step_i(funct3, funct7hi, rs1v, imm):
    key = funct3 * 128 + funct7hi
    shamt = imm & 31
    result = 0
    if funct3 == 0:
        result = rs1v + imm
    if funct3 == 4:
        result = rs1v ^ imm
    if funct3 == 6:
        result = rs1v | imm
    if funct3 == 7:
        result = rs1v & imm
    if funct3 == 1:
        result = rs1v << shamt
    if key == 640:
        result = rs1v >> shamt
    if key == 672:
        result = (rs1v >> shamt) | ((0 - (rs1v >> 31)) - ((0 - (rs1v >> 31)) >> shamt))
    return result
"""

# funct3 values used by the ALU core (name -> (funct3, funct7-or-0))
R_OPS = {
    "ADD": (0, 0), "SUB": (0, 32), "XOR": (4, 0), "OR": (6, 0),
    "AND": (7, 0), "SLL": (1, 0), "SRL": (5, 0), "SRA": (5, 32),
}
I_OPS = {
    "ADDI": (0, 0), "XORI": (4, 0), "ORI": (6, 0), "ANDI": (7, 0),
    "SLLI": (1, 0), "SRLI": (5, 0), "SRAI": (5, 32),
}

ADVERSARIAL = [0x00000000, 0x00000001, 0x7FFFFFFF, 0x80000000,
              0xFFFFFFFF, 0xDEADBEEF]


def ref_alu_r(funct3: int, funct7: int, rs1v: int, rs2v: int) -> int:
    """Spec-literal reference for step_r (the oracle's oracle)."""
    rs1v &= U32_MASK
    rs2v &= U32_MASK
    if funct3 == 0:
        return ((rs1v - rs2v) if funct7 == 32 else (rs1v + rs2v)) & U32_MASK
    if funct3 == 4:
        return rs1v ^ rs2v
    if funct3 == 6:
        return rs1v | rs2v
    if funct3 == 7:
        return rs1v & rs2v
    if funct3 == 1:
        return (rs1v << (rs2v & 31)) & U32_MASK
    if funct3 == 5:
        shamt = rs2v & 31
        if funct7 == 32:
            signed = rs1v - (1 << 32) if rs1v & 0x80000000 else rs1v
            return (signed >> shamt) & U32_MASK if shamt else rs1v
        return rs1v >> shamt
    raise ValueError(funct3)


def ref_alu_i(funct3: int, funct7hi: int, rs1v: int, imm: int) -> int:
    return ref_alu_r(funct3, funct7hi, rs1v, imm & U32_MASK)


# ── three-way differential gate over the ALU families ──────────────────


def run_alu_differential(is_r: bool, funct3: int, funct7: int,
                         rs1v: int, rs2v_or_imm: int) -> Dict:
    """compile_function + pyshader_wgsl.run_triple_differential on the
    step_r/step_i source, args=[funct3, funct7, rs1v, rs2v_or_imm].
    Adds the spec-literal reference as a FOURTH check (the PS004 lesson:
    never adjudicate an oracle-vs-GPU disagreement by trusting either
    engine — a hand-computed value settles it)."""
    from tools.pyshader_wgsl import run_triple_differential

    src = STEP_R_SRC if is_r else STEP_I_SRC
    args = [funct3, funct7, rs1v, rs2v_or_imm]
    receipt = run_triple_differential(src, args)
    ref = (ref_alu_r if is_r else ref_alu_i)(funct3, funct7, rs1v,
                                             rs2v_or_imm)
    receipt["ref"] = ref & U32_MASK
    receipt["ok"] = receipt["ok"] and receipt["gpu_r9"] == (ref & U32_MASK)
    return receipt


# ── register-file double-buffer driver (PS003 recipe, 32+32 words) ─────

REG_N = 32

_REGFILE_SHADER = """// generated by tools/pyshader_rvexec.py — PS006 regfile step
@group(0) @binding(0) var<storage, read_write> buf: array<u32, 64u>;

fn body(r1: u32, r2: u32, r3: u32, r4: u32) -> u32 {
%DECLS%
%BODY%
}

@compute @workgroup_size(1, 1, 1)
fn main() {
    var i: u32 = 0u;
    loop {
        if (i >= 32u) { break; }
        buf[32u + i] = buf[i];
        i = i + 1u;
    }
    let rs1v = buf[%RS1%u];
    let rs2v = %RS2_EXPR%;
    buf[32u + %RD%u] = body(%FUNCT3%u, %FUNCT7%u, rs1v, rs2v);
}
"""


def _alu_body_wgsl(module) -> str:
    """Extract the compiled step_r/step_i body as a WGSL function body
    over r1..r4 (its own params) — same body-extraction trick as
    pyshader_cell._step_body_wgsl, generalized to 4 params."""
    from tools.pyshader_wgsl import emit_wgsl

    wgsl = emit_wgsl(module, params=None)
    lines = wgsl.splitlines()
    start = next(i for i, l in enumerate(lines)
                if "structured body" in l) + 1
    halt = next(i for i, l in enumerate(lines) if "HALT" in l)
    body: List[str] = []
    for l in lines[start:halt]:
        s = l.strip()
        if s.startswith("r25 = "):
            continue
        body.append("    " + s)
    return "\n".join(body) + "\n    return r9;"


def run_regfile_step_gpu(is_r: bool, funct3: int, funct7: int,
                         rd: int, rs1: int, rs2_or_imm,
                         old_regs: List[int]) -> Dict:
    """One dispatch: OLD 32-word regfile (old_regs) -> NEW 32-word
    regfile, computed via the double-buffer copy-then-overwrite-rd
    driver. `rs2_or_imm` is a register index (R-type) or a literal
    immediate int (I-type; set is_r=False).

    Gate: NEW must equal OLD everywhere except NEW[rd], which must
    equal ref_alu_r/ref_alu_i(funct3, funct7, OLD[rs1], rs2-value) —
    proving the copy-through (every OTHER register survives the
    dispatch unmodified), not merely the ALU result."""
    import struct

    import wgpu

    assert rd != 0 and rs1 != 0, "PS006: x0 not hardwired yet, avoid r0 in tests"
    src = STEP_R_SRC if is_r else STEP_I_SRC
    module = compile_function(src)
    decls = "    var r0: u32 = 0u;\n" + "\n".join(
        f"    var r{i}: u32 = 0u;" for i in range(5, 25))
    body = _alu_body_wgsl(module)

    if is_r:
        rs2_expr = f"buf[{rs2_or_imm}u]"
    else:
        rs2_expr = f"{rs2_or_imm & U32_MASK}u"

    wgsl = (_REGFILE_SHADER
            .replace("%DECLS%", decls)
            .replace("%BODY%", body)
            .replace("%RS1%", str(rs1))
            .replace("%RS2_EXPR%", rs2_expr)
            .replace("%RD%", str(rd))
            .replace("%FUNCT3%", str(funct3))
            .replace("%FUNCT7%", str(funct7)))

    old_regs = [v & U32_MASK for v in old_regs][:REG_N]
    old_regs += [0] * (REG_N - len(old_regs))

    device = _device()
    shader = device.create_shader_module(code=wgsl, label="regfile-step")
    n = 2 * REG_N
    gpu_buf = device.create_buffer(
        size=n * 4,
        usage=(wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
               | wgpu.BufferUsage.COPY_DST),
        label="regfile-state")
    device.queue.write_buffer(
        gpu_buf, 0, struct.pack(f"<{REG_N}I", *old_regs))
    pipe = device.create_compute_pipeline(
        layout="auto", compute={"module": shader, "entry_point": "main"},
        label="regfile-pipe")
    bg = device.create_bind_group(
        layout=pipe.get_bind_group_layout(0),
        entries=[{"binding": 0,
                  "resource": {"buffer": gpu_buf, "offset": 0,
                               "size": n * 4}}],
        label="regfile-bind")
    enc = device.create_command_encoder(label="regfile-enc")
    cp = enc.begin_compute_pass()
    cp.set_pipeline(pipe)
    cp.set_bind_group(0, bg)
    cp.dispatch_workgroups(1, 1, 1)
    cp.end()
    readback = device.create_buffer(
        size=n * 4,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ,
        label="regfile-read")
    enc.copy_buffer_to_buffer(gpu_buf, 0, readback, 0, n * 4)
    device.queue.submit([enc.finish()])
    readback.map_sync(mode=wgpu.MapMode.READ)
    data = bytes(readback.read_mapped())
    readback.unmap()
    words = list(struct.unpack(f"<{n}I", data))
    new_regs = words[REG_N:2 * REG_N]

    rs2v = old_regs[rs2_or_imm] if is_r else (rs2_or_imm & U32_MASK)
    ref_fn = ref_alu_r if is_r else ref_alu_i
    rd_expected = ref_fn(funct3, funct7, old_regs[rs1], rs2v) & U32_MASK
    want = list(old_regs)
    want[rd] = rd_expected

    return {"ok": new_regs == want, "gpu_new": new_regs, "want": want,
            "rd_expected": rd_expected, "wgsl": wgsl}


def _device():
    """Route through pyshader_wgsl's cached device — PS006 found that a
    fresh adapter+device per call exhausts the driver across many
    parametrized GPU tests in one process."""
    from tools.pyshader_wgsl import _cached_device
    return _cached_device()

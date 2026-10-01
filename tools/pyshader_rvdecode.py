"""tools/pyshader_rvdecode.py — PS005: generated RV32I instruction decode.

Phase 1 of GPU_CPU_EMULATOR_ROADMAP.md: express instruction decoding as
Python programs, compile them through the PS001-PS004 toolchain
(GlyphIR -> WGSL -> naga -> SPIR-V -> RTX 5090), and decode 64
instruction words per dispatch as parallel MAP-mode invocations.

TWO programs, both compiled and GPU-verified:
  FIELDS_SRC  dec(word)      -> packed field word (opcode/rd/funct3/
                                rs1/rs2/funct7 in RISC-V bit positions)
  IMM_SRC     decimm(word)   -> RAW immediate field (no sign extension;
                                extension is applied host-side by
                                unpack_imm using the format table —
                                the SAME table the oracle uses, so
                                extension rules exist in exactly one
                                place on the GPU path)

Gate: every fixture is checked against decode_ref (the spec-literal
Python decoder) with format-aware field comparison — for I/S/B formats
the packed word's rs2/funct7 bit positions ARE the immediate bits, so
only the fields each format defines are compared. Imm comparison is on
the sign-extended value.

Compressed (C) decode: OUT of scope for PS005 (all fixtures are 32-bit
encodings); the roadmap files it as PS005b.
"""
from __future__ import annotations

from typing import Dict, List

N_CELLS = 64

# ── Python reference decoder (the oracle AND the spec source) ───────────


def decode_ref(word: int) -> Dict:
    """Reference RV32I decode. Spec-literal; the shader programs below
    are transcriptions of it, and the gate proves agreement."""
    opcode = word & 0x7F
    rd = (word >> 7) & 0x1F
    funct3 = (word >> 12) & 0x7
    rs1 = (word >> 15) & 0x1F
    rs2 = (word >> 20) & 0x1F
    funct7 = (word >> 25) & 0x7F

    def sext(value: int, bits: int) -> int:
        sign = 1 << (bits - 1)
        return (value & (sign - 1)) - (value & sign)

    imm_i = sext(word >> 20, 12)
    imm_s = sext(((word >> 25) << 5) | ((word >> 7) & 0x1F), 12)
    imm_b = sext(((word >> 31) & 0x1) << 12
                 | ((word >> 7) & 0x1) << 11
                 | ((word >> 25) & 0x3F) << 5
                 | ((word >> 8) & 0xF) << 1, 13)
    imm_u = word & 0xFFFFF000
    imm_j = sext(((word >> 31) & 0x1) << 20
                 | ((word >> 12) & 0xFF) << 12
                 | ((word >> 20) & 0x1) << 11
                 | ((word >> 21) & 0x3FF) << 1, 21)

    if opcode == 0x33:                       # R
        return dict(fmt="R", opcode=opcode, rd=rd, funct3=funct3,
                    rs1=rs1, rs2=rs2, funct7=funct7, imm=0)
    if opcode in (0x13, 0x03, 0x67):         # I (ALU, load, JALR)
        return dict(fmt="I", opcode=opcode, rd=rd, funct3=funct3,
                    rs1=rs1, imm=imm_i)
    if opcode == 0x23:                       # S (store)
        return dict(fmt="S", opcode=opcode, funct3=funct3,
                    rs1=rs1, rs2=rs2, imm=imm_s)
    if opcode == 0x63:                       # B (branch)
        return dict(fmt="B", opcode=opcode, funct3=funct3,
                    rs1=rs1, rs2=rs2, imm=imm_b)
    if opcode in (0x37, 0x17):               # U (LUI, AUIPC)
        return dict(fmt="U", opcode=opcode, rd=rd, imm=imm_u)
    if opcode == 0x6F:                       # J (JAL)
        return dict(fmt="J", opcode=opcode, rd=rd, imm=imm_j)
    if opcode == 0x73:                       # SYSTEM (ECALL/EBREAK)
        return dict(fmt="SYSTEM", opcode=opcode, rd=rd, funct3=funct3,
                    imm=imm_i)
    return dict(fmt="??", opcode=opcode, rd=rd, funct3=funct3,
                rs1=rs1, rs2=rs2, funct7=funct7, imm=0)


# Per-format defined fields — the ONLY fields a format's packed word
# is required to reproduce (I/S/B imm bits alias rs2/funct7 positions).

def _expected_fields(d: Dict) -> Dict[str, int]:
    """Fields each format DEFINES (packed word must reproduce these).
    Positions not defined by the format hold immediate bits and are
    checked via the immediate comparison, never here."""
    fmt = d["fmt"]
    exp = {"opcode": d["opcode"]}
    if fmt in ("R", "I", "SYSTEM"):
        exp["rd"] = d.get("rd", 0)
    if fmt in ("R", "I", "S", "B", "SYSTEM"):
        exp["funct3"] = d.get("funct3", 0)
    if fmt in ("R", "I", "S", "B"):
        exp["rs1"] = d.get("rs1", 0)
    if fmt == "R":
        exp["rs2"] = d["rs2"]
        exp["funct7"] = d["funct7"]
    if fmt in ("S", "B"):
        exp["rs2"] = d["rs2"]
    return exp


# ── Shader sources (front-end subset: <=8 var regs r2..r9 with
#    statement-scoped temps; deep expressions staged into multiple
#    assigns — see pyshader_compiler.lower_body note) ──────────────────

FIELDS_SRC = """def dec(word):
    opcode = word & 127
    rd = (word >> 7) & 31
    funct3 = (word >> 12) & 7
    rs1 = (word >> 15) & 31
    rs2 = (word >> 20) & 31
    funct7 = (word >> 25) & 127
    fields = opcode + (rd << 7) + (funct3 << 12)
    fields = fields + (rs1 << 15)
    fields = fields + (rs2 << 20)
    fields = fields + (funct7 << 25)
    return fields
"""

IMM_SRC = """def decimm(word):
    opcode = word & 127
    imm_i = (word >> 20) & 4095
    imm_u = word & 4294963200
    imm_s = ((word >> 25) & 127) * 32 + ((word >> 7) & 31)
    imm_b = ((word >> 31) & 1) * 4096 + ((word >> 7) & 1) * 2048
    imm_b = imm_b + ((word >> 25) & 63) * 32 + ((word >> 8) & 15) * 2
    imm_j = ((word >> 31) & 1) * 1048576 + ((word >> 12) & 255) * 4096
    imm_j = imm_j + ((word >> 20) & 1) * 2048 + ((word >> 21) & 1023) * 2
    imm = 0
    if opcode == 19:
        imm = imm_i
    if opcode == 3:
        imm = imm_i
    if opcode == 103:
        imm = imm_i
    if opcode == 115:
        imm = imm_i
    if opcode == 35:
        imm = imm_s
    if opcode == 99:
        imm = imm_b
    if opcode == 55:
        imm = imm_u
    if opcode == 23:
        imm = imm_u
    if opcode == 111:
        imm = imm_j
    return imm
"""


def unpack_imm(raw: int, fmt: str) -> int:
    """Format-aware sign extension of the raw immediate. ONE place the
    extension rules live for the GPU path (the oracle's decode_ref has
    the identical rules inline)."""
    def sext(value: int, bits: int) -> int:
        sign = 1 << (bits - 1)
        return (value & (sign - 1)) - (value & sign)

    if fmt in ("I", "S", "SYSTEM"):
        return sext(raw & 0xFFF, 12)
    if fmt == "B":
        return sext(raw & 0x1FFF, 13)
    if fmt == "U":
        return raw & 0xFFFFF000
    if fmt == "J":
        return sext(raw & 0x1FFFFF, 21)
    return 0


# ── Oracle runner (fresh interpreter per case — PS004 lesson) ──────────


def run_decode_oracle(words: List[int]) -> List[Dict]:
    """CPU-only decode of each word through the compiled IR — the
    middle engine. Returns per-word {fields, imm_raw} dicts."""
    from tools.pyshader_compiler import IRInterpreter, compile_function

    mf = compile_function(FIELDS_SRC)
    mi = compile_function(IMM_SRC)
    out = []
    for w in words:
        w &= 0xFFFFFFFF
        out.append({
            "fields": IRInterpreter(mf).run([w]),
            "imm_raw": IRInterpreter(mi).run([w]),
        })
    return out


def decode_batch_report(words: List[int], fields: List[int],
                        imm_raw: List[int]) -> Dict:
    """Adjudicate a decode result (GPU or oracle) against decode_ref.
    Format-aware: only format-defined fields compared; imm compared
    after unpack_imm sign extension."""
    mismatches = []
    for i, w in enumerate(words):
        w &= 0xFFFFFFFF
        ref = decode_ref(w)
        pf = unpack_fields(fields[i])
        exp = _expected_fields(ref)
        bad = {k: (pf.get(k), v) for k, v in exp.items()
               if pf.get(k) != v}
        imm_signed = unpack_imm(imm_raw[i], ref["fmt"])
        if bad or imm_signed != ref["imm"]:
            mismatches.append({
                "i": i, "word": w, "ref": ref,
                "got_fields": pf, "field_bad": bad,
                "imm_raw": imm_raw[i], "imm_signed": imm_signed,
            })
    return {"ok": not mismatches, "n": len(words),
            "mismatches": mismatches[:8], "n_bad": len(mismatches)}


def unpack_fields(packed: int) -> Dict[str, int]:
    return dict(
        opcode=packed & 0x7F,
        rd=(packed >> 7) & 0x1F,
        funct3=(packed >> 12) & 0x7,
        rs1=(packed >> 15) & 0x1F,
        rs2=(packed >> 20) & 0x1F,
        funct7=(packed >> 25) & 0x7F,
    )


# ── GPU runner: seed buf[REGION_OFF + i] = word, one invocation per
#    word, read back fields + raw imm from two result windows ──────────


def _emit_reader_wgsl(module, in_off: int, out_off: int) -> str:
    """Cell-mode WGSL where invocation `me` reads its input word from
    buf[in_off + me] and stores its result at buf[out_off + me].

    Built on emit_cell_map_wgsl (r1=me at entry, per-cell result store
    at HALT), then: the input read is injected right after the r1=me
    bind, the result store target moves to out_off, and the buffer is
    sized to cover the highest window (max in/off + n_cells words)."""
    from tools.pyshader_cell import emit_cell_map_wgsl
    from tools.pyshader_wgsl import REGION_OFF as _RO

    wgsl = emit_cell_map_wgsl(module)
    # me is stashed in r31 BEFORE r1 is overwritten with the input
    # word: r31 is declared by the standard prologue but never used by
    # the compiler (vars r2..r8, temps r10..r24, region base r25), so
    # it is safe as the invocation index across the body.
    wgsl = wgsl.replace(
        "    r1 = gid.x;",
        f"    r31 = gid.x;\n    r1 = buf[{in_off}u + r31];")
    wgsl = wgsl.replace(
        f"    buf[{_RO} + r1] = r9;",
        f"    buf[{out_off}u + r31] = r9;")
    need = max(in_off, out_off) + N_CELLS
    wgsl = wgsl.replace(
        f"array<u32, {_RO + N_CELLS}>", f"array<u32, {need}>")
    return wgsl


def run_decode_gpu(words: List[int]) -> Dict:
    """Dispatch N_CELLS invocations; invocation i decodes
    buf[REGION_OFF+i]. Returns the GPU report + oracle comparison."""
    import struct

    import wgpu

    from tools.pyshader_cell import N_CELLS as NC
    from tools.pyshader_compiler import compile_function
    from tools.pyshader_wgsl import REGION_OFF

    words = [w & 0xFFFFFFFF for w in words][:NC]
    n = len(words)
    # two result windows after the inputs: fields at +64, imm at +128
    IN_OFF = REGION_OFF
    FLD_OFF = REGION_OFF + NC
    IMM_OFF = REGION_OFF + 2 * NC
    N_BUF = REGION_OFF + 3 * NC

    mf = compile_function(FIELDS_SRC)
    mi = compile_function(IMM_SRC)

    device = _device()
    gpu_buf = device.create_buffer(
        size=N_BUF * 4,
        usage=(wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC
               | wgpu.BufferUsage.COPY_DST),
        label="rvdecode-state")
    seed = [0] * N_BUF
    for i, w in enumerate(words):
        seed[IN_OFF + i] = w
    device.queue.write_buffer(
        gpu_buf, 0, struct.pack(f"<{N_BUF}I", *seed))

    outs = {}
    for tag, module, out_off in (
            ("fields", mf, FLD_OFF), ("imm", mi, IMM_OFF)):
        wgsl = _emit_reader_wgsl(module, IN_OFF, out_off)
        shader = device.create_shader_module(code=wgsl,
                                             label=f"rvdec-{tag}")
        pipe = device.create_compute_pipeline(
            layout="auto",
            compute={"module": shader, "entry_point": "main"},
            label=f"rvdec-{tag}-pipe")
        bg = device.create_bind_group(
            layout=pipe.get_bind_group_layout(0),
            entries=[{"binding": 0,
                      "resource": {"buffer": gpu_buf, "offset": 0,
                                   "size": N_BUF * 4}}],
            label=f"rvdec-{tag}-bind")
        enc = device.create_command_encoder(label=f"rvdec-{tag}")
        cp = enc.begin_compute_pass()
        cp.set_pipeline(pipe)
        cp.set_bind_group(0, bg)
        cp.dispatch_workgroups(NC, 1, 1)
        cp.end()
        device.queue.submit([enc.finish()])

    readback = device.create_buffer(
        size=N_BUF * 4,
        usage=wgpu.BufferUsage.COPY_DST | wgpu.BufferUsage.MAP_READ,
        label="rvdec-read")
    enc2 = device.create_command_encoder(label="rvdec-read")
    enc2.copy_buffer_to_buffer(gpu_buf, 0, readback, 0, N_BUF * 4)
    device.queue.submit([enc2.finish()])
    readback.map_sync(mode=wgpu.MapMode.READ)
    data = bytes(readback.read_mapped())
    readback.unmap()
    got = list(struct.unpack(f"<{N_BUF}I", data))
    outs["fields"] = got[FLD_OFF:FLD_OFF + NC]
    outs["imm"] = got[IMM_OFF:IMM_OFF + NC]

    # oracle legs
    oracle = run_decode_oracle(words)
    o_fields = [o["fields"] for o in oracle]
    o_imm = [o["imm_raw"] for o in oracle]

    g_fields = outs["fields"][:n]
    g_imm = outs["imm"][:n]

    gpu_vs_ref = decode_batch_report(words, g_fields, g_imm)
    oracle_vs_ref = decode_batch_report(words, o_fields, o_imm)

    return {
        "ok": (gpu_vs_ref["ok"] and oracle_vs_ref["ok"]
               and g_fields == o_fields and g_imm == o_imm),
        "n": n,
        "gpu_fields": g_fields, "gpu_imm_raw": g_imm,
        "oracle_fields": o_fields, "oracle_imm_raw": o_imm,
        "gpu_vs_ref": gpu_vs_ref, "oracle_vs_ref": oracle_vs_ref,
    }


def _device():
    import wgpu
    adapter = wgpu.gpu.request_adapter_sync(
        power_preference="high-performance")
    return adapter.request_device_sync(label="pyshader-rvdecode")

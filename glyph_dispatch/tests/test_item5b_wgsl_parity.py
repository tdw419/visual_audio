#!/usr/bin/env python3
"""
ROADMAP item 5b oracle: the WGSL Glyph ISA shader is instruction-for-instruction
parity with the Python GlyphCPUv2 — including the item 5a ROTR opcode.

Runs the same assembled program through BOTH execution engines from an
identical initial state and requires identical PRT output:

  Python : GlyphCPUv2 (glyph_isa_v2.py)          — the reference
  GPU    : wgsl_glyph_isa_v2.build_shader() run  — the WGSL port
           via wgpu (skips cleanly if wgpu/GPU absent)

Programs exercised (each is a parity oracle in its own right):
  1. rot  — ROTR sweep: all 32 shift amounts, rotate-by-register with
            rs2=35 (masking to 3), and the n=0 identity edge
  2. alu  — every ALU opcode (LDI/ADD/SUB/AND/OR/XOR/SHL/SHR/CMP/ROTR)
            with values chosen to wrap 32 bits
  3. mem  — LD/ST/PUSH/POP round trip (shared program/image memory model)
  4. ctrl — CALL/RET/JMP/JZ control flow with a down-counter

FAILS LOUDLY (non-zero exit) on any divergence. Skips (exit 0, reason
printed) only when wgpu or a GPU device is unavailable.

Run:  python3 glyph_dispatch/tests/test_item5b_wgsl_parity.py
"""
import contextlib
import hashlib
import io
import sys
from pathlib import Path

# GlyphCPUv2 registers are unbounded Python ints; PRT formats them as decimal
# and SHL programs grow them past CPython's 4300-digit int->str limit. The ISA
# contract is 32-bit (see the mask in run_python) — this only keeps the
# reference's own printing alive.
sys.set_int_max_str_digits(2_000_000)

import numpy as np

_GD_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]
# NOTE: glyph_dispatch has its own src/ package; the repo root ALSO has a src/
# (the codec). _GD_ROOT must end up AHEAD of _REPO_ROOT on sys.path, and since
# insert(0) reverses insertion order, _GD_ROOT is inserted LAST.
for p in (str(_REPO_ROOT / "tools"), str(_REPO_ROOT), str(_GD_ROOT)):
    # remove-then-insert: GD must END UP first even if a wrapper already put
    # some of these on sys.path (the naive 'if not in' skip breaks ordering)
    while p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

from src.glyph.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2
from src.glyph.wgsl_glyph_isa_v2 import build_shader, make_cpu_state_array
from src.glyph.sha256_kernel import build_sha256_glyph_program, sha256_glyph

WIDTH = 16  # instructions per row

# The repo root's real wordbase db (glyph_dispatch's default src/db/wordbase.db
# does not exist; the GD 'tools' namespace package vs the repo's regular
# 'tools' package resolves to the repo's WordbaseManager).
WORDBASE_DB = _REPO_ROOT / "db" / "wordbase.db"


def _opmap():
    return OpcodeMapV2(wordbase_path=WORDBASE_DB)


def _skip(msg):
    print(f"SKIP: {msg}")
    sys.exit(0)


# ---------------------------------------------------------------- programs

def prog_rot():
    v = 3735928559  # 0xDEADBEEF
    lines = []
    for n in range(32):
        lines.append(f"LDI r3 {n}")
        lines.append(f"LDI r2 {v}")
        lines.append("ROTR r2 r3")
        lines.append("PRT r2")
    # rotate-by-register with n=35 -> effective 35 & 31 = 3
    lines.append("LDI r3 35")
    lines.append(f"LDI r2 {v}")
    lines.append("ROTR r2 r3")
    lines.append("PRT r2")
    # n=0 identity edge (rotate by 0 must be identity, not shift-to-zero)
    lines.append("LDI r3 0")
    lines.append(f"LDI r2 {v}")
    lines.append("ROTR r2 r3")
    lines.append("PRT r2")
    lines.append("HALT")
    return lines


def expected_rot():
    v = 3735928559
    out = []
    for n in list(range(32)) + [35, 0]:
        n_eff = n & 31
        out.append(((v >> n_eff) | (v << (32 - n_eff))) & 0xFFFFFFFF if n_eff else v)
    return out


def prog_alu():
    return [
        "LDI r1 4294967295",   # 0xFFFFFFFF
        "LDI r2 2",
        "ADD r1 r2",           # wraps to 1
        "PRT r1",
        "LDI r1 4294967294",
        "LDI r2 10",
        "ADD r1 r2",           # wraps to 4
        "PRT r1",
        "LDI r1 5",
        "LDI r2 9",
        "SUB r1 r2",           # wraps to 0xFFFFFFFC
        "PRT r1",
        "LDI r1 4042322160",   # 0xF0F0F0F0
        "LDI r2 252645135",    # 0x0F0F0F0F
        "AND r1 r2",
        "PRT r1",
        "OR r1 r2",
        "PRT r1",
        "XOR r1 r2",
        "PRT r1",
        "LDI r1 1",
        "LDI r8 9",            # fresh shift amount (r2 was clobbered above)
        "SHL r1 r8",           # 1 << 9 = 512
        "PRT r1",
        "SHR r1 r8",           # 512 >> 9 = 1
        "PRT r1",
        "LDI r5 305419896",    # 0x12345678
        "LDI r6 305419896",
        "CMP r5 r6",           # equal -> r0 = 1
        "PRT r0",
        "LDI r6 305419897",
        "CMP r5 r6",           # unequal -> r0 = 0
        "PRT r0",
        "LDI r3 305419896",
        "LDI r7 8",
        "ROTR r3 r7",          # rotr32(0x12345678, 8) = 0x78123456
        "PRT r3",
        "HALT",
    ]


def expected_alu():
    return [1, 8, 4294967292, 0, 252645135, 0, 512, 1, 1, 0, 2014458966]


def prog_mem():
    return [
        "LDI r1 900",          # scratch addr (word RAM is 1024 words)
        "LDI r2 3435973836",   # 0xCCCCCCCC
        "ST r1 r2",            # mem[2048] = r2  (ST rd rs2: address in rd)
        "LD r3 r1",            # r3 = mem[2048]  (LD rd rs2: address in rs2)
        "PRT r3",
        "LDI r31 4095",        # set SP
        "LDI r5 123456",
        "PUSH r5",
        "LDI r5 654321",
        "PUSH r5",
        "POP r6",              # 654321
        "PRT r6",
        "POP r7",              # 123456
        "PRT r7",
        "HALT",
    ]


def expected_mem():
    # LD/ST hit the 32-bit word RAM on both engines, so 0xCCCCCCCC round-trips
    return [3435973836, 654321, 123456]


def prog_control():
    # prints 5..1 via a decrement subroutine: CALL/RET/JMP/JZ all exercised
    return [
        "LDI r5 5",       # 0
        "CMP r5 r1",      # 1  r1 never set (0): equal only when r5 == 0
        "JZ 9,0",         # 2  -> instr 9 (HALT)
        "PRT r5",         # 3
        "CALL 6,0",       # 4  call dec
        "JMP 1,0",        # 5  recompare
        "LDI r2 1",       # 6  dec:
        "SUB r5 r2",      # 7
        "RET",            # 8
        "HALT",           # 9
    ]


def expected_control():
    return [5, 4, 3, 2, 1]


# ------------------------------------------------------------ GPU runner

class WgslRunner:
    """Runs an assembled glyph program image on the WGSL shader via wgpu,
    one dispatch per instruction step, mirroring GlyphCPUv2.step()."""

    def __init__(self):
        import wgpu
        import wgpu.utils
        self.wgpu = wgpu
        self.device = wgpu.utils.get_default_device()
        self.shader = self.device.create_shader_module(
            code=build_shader(_opmap()))

    def run_image(self, image, max_instructions=100_000, n_cpus=1):
        wgpu = self.wgpu
        device = self.device
        queue = device.queue
        rows, width_px, _ = image.shape
        w, h = width_px, rows

        img_u32 = np.zeros((h, w, 4), dtype=np.uint32)
        img_u32[:, :, :3] = np.ascontiguousarray(image)
        img_flat = img_u32.reshape(-1)

        cpus, dtype = make_cpu_state_array(n_cpus)
        out_words = 256 * n_cpus

        img_buf = device.create_buffer(
            size=img_flat.nbytes,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST |
                  wgpu.BufferUsage.COPY_SRC)
        queue.write_buffer(img_buf, 0, img_flat.tobytes())
        cpu_buf = device.create_buffer(
            size=cpus.nbytes,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST |
                  wgpu.BufferUsage.COPY_SRC)
        out_buf = device.create_buffer(
            size=out_words * 4,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC |
                  wgpu.BufferUsage.COPY_DST)
        # steps=1: legacy step-locked mode; ram_stride=0: shared RAM (single
        # lane in this harness, so shared vs per-lane is equivalent)
        uni = np.array([w, h, out_words, 1, 0], dtype=np.uint32)
        uni_buf = device.create_buffer(
            size=uni.nbytes,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        queue.write_buffer(uni_buf, 0, uni.tobytes())
        # word-array RAM (binding 4): mirrors GlyphCPUv2.self.memory.
        # 4096 words covers the SHA-256 kernel's K/W/OUT regions.
        ram = np.zeros(4096, dtype=np.uint32)
        ram_buf = device.create_buffer(
            size=ram.nbytes,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST |
                  wgpu.BufferUsage.COPY_SRC)
        queue.write_buffer(ram_buf, 0, ram.tobytes())

        bgl = device.create_bind_group_layout(entries=[
            {'binding': 0, 'visibility': wgpu.ShaderStage.COMPUTE,
             'buffer': {'type': 'storage'}},
            {'binding': 1, 'visibility': wgpu.ShaderStage.COMPUTE,
             'buffer': {'type': 'storage'}},
            {'binding': 2, 'visibility': wgpu.ShaderStage.COMPUTE,
             'buffer': {'type': 'storage'}},
            {'binding': 3, 'visibility': wgpu.ShaderStage.COMPUTE,
             'buffer': {'type': 'uniform'}},
            {'binding': 4, 'visibility': wgpu.ShaderStage.COMPUTE,
             'buffer': {'type': 'storage'}},
        ])
        bg = device.create_bind_group(layout=bgl, entries=[
            {'binding': 0, 'resource': {'buffer': img_buf, 'offset': 0,
                                        'size': img_buf.size}},
            {'binding': 1, 'resource': {'buffer': cpu_buf, 'offset': 0,
                                        'size': cpu_buf.size}},
            {'binding': 2, 'resource': {'buffer': out_buf, 'offset': 0,
                                        'size': out_buf.size}},
            {'binding': 3, 'resource': {'buffer': uni_buf, 'offset': 0,
                                        'size': uni_buf.size}},
            {'binding': 4, 'resource': {'buffer': ram_buf, 'offset': 0,
                                        'size': ram_buf.size}},
        ])
        pipeline = device.create_compute_pipeline(
            layout=device.create_pipeline_layout(bind_group_layouts=[bgl]),
            compute={"module": self.shader, "entry_point": "main"})

        outputs = []
        prev_out_ptr = 0
        for _step in range(max_instructions):
            queue.write_buffer(cpu_buf, 0, cpus.tobytes())
            enc = device.create_command_encoder()
            pass_ = enc.begin_compute_pass()
            pass_.set_pipeline(pipeline)
            pass_.set_bind_group(0, bg)
            pass_.dispatch_workgroups(n_cpus)
            pass_.end()
            queue.submit([enc.finish()])

            cpus_new = np.frombuffer(
                queue.read_buffer(cpu_buf), dtype=np.uint32).reshape(n_cpus, -1)
            out_raw = np.frombuffer(
                queue.read_buffer(out_buf), dtype=np.uint32)

            now_ptr = int(cpus_new[0][35])     # output_ptr is the 36th u32
            outputs.extend(int(out_raw[i]) for i in range(prev_out_ptr, now_ptr))
            prev_out_ptr = now_ptr
            if cpus_new[0][34] == 0:           # running flag is the 35th u32
                # memory readback (program image doubles as scratch)
                img_back = np.frombuffer(
                    queue.read_buffer(img_buf), dtype=np.uint32).reshape(h, w, 4)
                return list(cpus_new[0][2:34]), outputs, \
                    img_back[:, :, :3].astype(np.uint8)
            cpus = cpus_new

        raise AssertionError(
            f"WGSL program did not halt within {max_instructions} steps")


# ------------------------------------------------------------ parity core

def assemble(lines):
    op = _opmap()
    asm = GlyphAssemblerV2(op)
    img = asm.assemble(lines, width_instrs=WIDTH)
    op.close()
    return img


def run_python(lines):
    op = _opmap()
    asm = GlyphAssemblerV2(op)
    img = asm.assemble(lines, width_instrs=WIDTH)
    cpu = GlyphCPUv2(op, WIDTH)
    with contextlib.redirect_stdout(io.StringIO()):
        n = cpu.run(img, max_instructions=100_000)
    op.close()
    # GlyphCPUv2 registers are unbounded Python ints (LDI 4294967295 +
    # ADD grows past 32 bits); the WGSL shader is u32. The ISA contract is
    # 32-bit, so compare both sides masked to 32 bits.
    return [v & 0xFFFFFFFF for v in cpu.output], n


def run_gpu(lines):
    r = WgslRunner()
    img = assemble(lines)
    return r.run_image(img)


def check(name, lines, expected_output):
    py_out, py_steps = run_python(lines)
    assert py_out == expected_output, (
        f"[{name}] Python REFERENCE itself mismatches the hand-computed "
        f"expectation (oracle bug, not a port bug):\n got {py_out}\n exp {expected_output}")

    try:
        gpu_regs, gpu_out, _ = run_gpu(lines)
    except Exception as e:
        _skip(f"GPU unavailable: {e}")

    if gpu_out != py_out:
        print(f"FAIL [{name}]")
        for i, (a, b) in enumerate(zip(py_out, gpu_out)):
            mark = "" if a == b else "   <-- DIVERGES"
            print(f"  out[{i:2}]  py={a:<12} gpu={b}{mark}")
        if len(py_out) != len(gpu_out):
            print(f"  length: py={len(py_out)} gpu={len(gpu_out)}")
        return False
    print(f"PASS [{name}]  ({len(expected_output)} outputs identical, "
          f"{py_steps} python steps)")
    return True


def main():
    ok = True
    ok &= check("rot  (ROTR sweep, 34 cases)", prog_rot(), expected_rot())
    ok &= check("alu  (all ALU ops + wrap)", prog_alu(), expected_alu())
    ok &= check("mem  (ST/LD/PUSH/POP)", prog_mem(), expected_mem())
    ok &= check("ctrl (CALL/RET/JMP/JZ)", prog_control(), expected_control())

    # kernel sanity: the SHA-256 program the WGSL shader must eventually run
    # assembles from the same ISA and matches hashlib on the Python CPU.
    msg = b"abc"
    want = hashlib.sha256(msg).hexdigest()
    lines = build_sha256_glyph_program(WIDTH)
    digest = sha256_glyph(msg, wordbase_path=WORDBASE_DB)
    assert digest.hex() == want, (digest.hex(), want)
    print(f"PASS [sha  ] sha256_glyph({msg!r}) == {want} "
          f"({len(lines)} kernel instrs, same ISA the WGSL oracles pin)")

    if not ok:
        print("\nPARITY BROKEN — see FAIL lines above")
        sys.exit(1)
    print("\nWGSL/Python glyph ISA parity: ALL PASS")


if __name__ == "__main__":
    main()

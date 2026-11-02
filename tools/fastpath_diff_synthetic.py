#!/usr/bin/env python3
"""Differential test: execute_decoded() vs decode_and_execute() in SPATIAL_RV64I.wgsl.

The pre-decoded fast path is disabled in-shader (DECODED_FASTPATH_DISABLED = true,
~3-5x slower) because with it live a fresh Alpine boot deadlocks in
queued_spin_lock_slowpath at `percpu:`. The root cause is a per-opcode semantic
divergence between the two execution paths (comment suspects: shift ops, the *W
word variants, AMO, LR/SC).

This runs each instruction through BOTH paths from an identical initial state and
reports the first opcode whose result differs. Fix that, flip the flag, re-verify
the boot, and the fast path is back.

Path selection: SpatialRV64ICore.SHADER_TRANSFORM (added for this) rewrites the
flag at shader-load time. Default class = fast path OFF (decode_and_execute);
_CoreFast subclass = fast path ON (execute_decoded).
"""
import subprocess, struct, sys, tempfile, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spatial_rv64i_cpu import SpatialRV64ICore

FLAG_OFF = 'let DECODED_FASTPATH_DISABLED: bool = true;'
FLAG_ON  = 'let DECODED_FASTPATH_DISABLED: bool = false;'


class _CoreFast(SpatialRV64ICore):
    SHADER_TRANSFORM = staticmethod(lambda code: code.replace(FLAG_OFF, FLAG_ON))


def asm1(line: str) -> int:
    """Assemble one RV64 instruction to its 32-bit word."""
    with tempfile.TemporaryDirectory() as d:
        s = Path(d) / "a.s"; o = Path(d) / "a.o"; b = Path(d) / "a.bin"
        s.write_text(line + "\n")
        subprocess.run(["riscv64-linux-gnu-as", "-march=rv64ima", "-o", str(o), str(s)],
                       check=True, capture_output=True)
        subprocess.run(["riscv64-linux-gnu-objcopy", "-O", "binary", str(o), str(b)],
                       check=True, capture_output=True)
        raw = b.read_bytes()
    assert len(raw) == 4, f"{line!r} -> {len(raw)} bytes (RVC or pseudo?)"
    return struct.unpack("<I", raw)[0]


# Operand batteries chosen to hit the classic decode/execute split points:
#  - shift amount with bit 5 set (RV64 word shifts use shamt[4:0])
#  - sign bit set in the 32-bit result (W ops sign-extend to 64)
#  - INT_MIN / -1 (div overflow), 0 divisor
S = 1 << 63
NEG1 = (1 << 64) - 1
I32MIN = 0xFFFFFFFF80000000
BIG = 0xDEADBEEFCAFEF00D

REG_SETS = [
    {6: 0x00000000FFFFFFFF, 7: 40},          # shift by >31
    {6: 0xFFFFFFFF80000000, 7: 4},           # sign bit in low32
    {6: BIG, 7: 33},
    {6: I32MIN, 7: NEG1},                    # div overflow
    {6: 0x123456789ABCDEF0, 7: 0},           # div by zero
    {6: 0x00000000FFFFFFFF, 7: 0x00000000FFFFFFFF},
    {6: 5, 7: 0xFFFFFFFFFFFFFFFB},           # -5
]

ALU_LINES = [
    # baseline (expected identical) ...
    "add x5,x6,x7", "sub x5,x6,x7", "and x5,x6,x7", "or x5,x6,x7", "xor x5,x6,x7",
    "sll x5,x6,x7", "srl x5,x6,x7", "sra x5,x6,x7", "slt x5,x6,x7", "sltu x5,x6,x7",
    "slli x5,x6,7", "srli x5,x6,7", "srai x5,x6,7",
    "slli x5,x6,40", "srli x5,x6,40", "srai x5,x6,40",     # shamt bit5
    "addi x5,x6,-1", "addiw x5,x6,-1",
    # word ops
    "addw x5,x6,x7", "subw x5,x6,x7", "sllw x5,x6,x7", "srlw x5,x6,x7", "sraw x5,x6,x7",
    "slliw x5,x6,3", "srliw x5,x6,3", "sraiw x5,x6,3",
    "slliw x5,x6,31", "srliw x5,x6,31", "sraiw x5,x6,31",
    # M-extension
    "mul x5,x6,x7", "mulh x5,x6,x7", "mulhu x5,x6,x7", "mulhsu x5,x6,x7",
    "div x5,x6,x7", "divu x5,x6,x7", "rem x5,x6,x7", "remu x5,x6,x7",
    "mulw x5,x6,x7", "divw x5,x6,x7", "divuw x5,x6,x7", "remw x5,x6,x7", "remuw x5,x6,x7",
    "lui x5,0xABCDE", "auipc x5,0xABCDE",
]

# AMO / LR-SC: rs1 (x6) = data word address; rs2 (x7) = operand.
AMO_LINES = [
    "amoswap.w x5,x7,(x6)", "amoadd.w x5,x7,(x6)", "amoxor.w x5,x7,(x6)",
    "amoand.w x5,x7,(x6)", "amoor.w x5,x7,(x6)",
    "amomin.w x5,x7,(x6)", "amomax.w x5,x7,(x6)", "amominu.w x5,x7,(x6)", "amomaxu.w x5,x7,(x6)",
    "amoswap.d x5,x7,(x6)", "amoadd.d x5,x7,(x6)",
    "amomin.d x5,x7,(x6)", "amomax.d x5,x7,(x6)",
    "lr.w x5,(x6)", "lr.d x5,(x6)",
]
AMO_DATA_ADDR = 0x400
AMO_MEM_VALS = [0x00000001_00000002, 0xFFFFFFFF_80000000, 0x7FFFFFFF_FFFFFFFF]
AMO_RS2_VALS = [1, 0xFFFFFFFF_FFFFFFFF, 0x80000000_00000000]


def run(core_cls, instr_words, regs, mem, nsteps=1):
    if isinstance(instr_words, int):
        instr_words = [instr_words]
    c = core_cls(memory_size_bytes=64 * 1024)
    c.load_program(b"".join(struct.pack("<I", w) for w in instr_words),
                   entry_point=0, ram_base=0)
    for r, v in regs.items():
        c.write_register(r, v & ((1 << 64) - 1))
    for a, v in (mem or {}).items():
        c.write_mem_word(a, v & 0xFFFFFFFF)
        c.write_mem_word(a + 4, (v >> 32) & 0xFFFFFFFF)
    c.step(nsteps)
    st = c.get_state()
    out = {
        "pc": st["pc"], "trap": int(st["trap_pending"]),
        "regs": [(int(lo) | (int(hi) << 32)) for lo, hi in st["regs"]],
        "fallback": st["bb_fallback_insts"], "threaded": st["bb_threaded_insts"],
        "total": st["bb_total_insts"],
        "resv": (int(st["reservation_valid"]), int(st["reservation_addr_low"]),
                 int(st["reservation_addr_high"])),
        "mode": int(st["mode"]),
    }
    # A handful of CSRs the spinlock / trap paths touch.
    for name, addr in [("mstatus", 0x300), ("mepc", 0x341), ("mcause", 0x342),
                       ("mtval", 0x343), ("sstatus", 0x100), ("sepc", 0x141),
                       ("scause", 0x142), ("satp", 0x180)]:
        out["csr_" + name] = c.read_csr(addr)
    if mem:
        a = next(iter(mem))
        out["mem"] = c.read_mem_word(a) | (c.read_mem_word(a + 4) << 32)
    return out


def diff(a, b):
    ds = []
    if a["pc"] != b["pc"]:
        ds.append(f"pc {a['pc']:#x} vs {b['pc']:#x}")
    if a["trap"] != b["trap"]:
        ds.append(f"trap {a['trap']} vs {b['trap']}")
    if a["mode"] != b["mode"]:
        ds.append(f"mode {a['mode']} vs {b['mode']}")
    if a["resv"] != b["resv"]:
        ds.append(f"reservation {a['resv']} vs {b['resv']}")
    for i, (x, y) in enumerate(zip(a["regs"], b["regs"])):
        if x != y:
            ds.append(f"x{i} {x:#018x} vs {y:#018x}")
    for k in a:
        if k.startswith("csr_") and a[k] != b[k]:
            ds.append(f"{k} {a[k]:#x} vs {b[k]:#x}")
    if a.get("mem") != b.get("mem"):
        ds.append(f"mem {a.get('mem'):#x} vs {b.get('mem'):#x}")
    return ds


LOAD_LINES = ["lb x5,0(x6)", "lh x5,0(x6)", "lw x5,0(x6)", "lwu x5,0(x6)",
              "ld x5,0(x6)", "lbu x5,0(x6)", "lhu x5,0(x6)",
              "lb x5,3(x6)", "lh x5,2(x6)", "lw x5,4(x6)"]
STORE_LINES = ["sb x7,0(x6)", "sh x7,0(x6)", "sw x7,0(x6)", "sd x7,0(x6)",
               "sb x7,3(x6)", "sh x7,2(x6)", "sw x7,4(x6)"]
DATA_ADDR = 0x400


def main():
    cases = []            # (name, tag, words, regs, mem, nsteps)
    for line in ALU_LINES:
        w = asm1(line)
        for rs in REG_SETS:
            cases.append((line, repr(rs), w, dict(rs), None, 1))
    for line in LOAD_LINES:
        w = asm1(line)
        for mv in AMO_MEM_VALS:
            cases.append((f"{line} [mem={mv:#x}]", "", w, {6: DATA_ADDR}, {DATA_ADDR: mv}, 1))
    for line in STORE_LINES:
        w = asm1(line)
        for r2 in (0xDEADBEEF_A5A5F00D, 0xFFFFFFFF_FFFFFFFF, 1):
            cases.append((f"{line} [rs2={r2:#x}]", "", w, {6: DATA_ADDR, 7: r2},
                          {DATA_ADDR: 0x11111111_22222222, DATA_ADDR + 8: 0x33333333_44444444}, 1))
    for line in AMO_LINES:
        w = asm1(line)
        for mv in AMO_MEM_VALS:
            for r2 in AMO_RS2_VALS:
                cases.append((f"{line} [mem={mv:#x} rs2={r2:#x}]", "", w,
                              {6: AMO_DATA_ADDR, 7: r2}, {AMO_DATA_ADDR: mv}, 1))
    # LR/SC pairs (2 steps) — spinlock primitive.
    for w1line, w2line in [("lr.w x5,(x6)", "sc.w x8,x7,(x6)"),
                           ("lr.d x5,(x6)", "sc.d x8,x7,(x6)")]:
        w1, w2 = asm1(w1line), asm1(w2line)
        for mv in AMO_MEM_VALS:
            cases.append((f"{w1line}; {w2line} [mem={mv:#x}]", "", [w1, w2],
                          {6: AMO_DATA_ADDR, 7: 0x99}, {AMO_DATA_ADDR: mv}, 2))
    # Control-flow ops: branch target / sign-extension, JAL/JALR target.
    for line in ["beq x6,x7,.+8", "bne x6,x7,.+8", "blt x6,x7,.+8", "bge x6,x7,.+8",
                 "bltu x6,x7,.+8", "bgeu x6,x7,.+8", "beq x6,x7,.-4", "blt x6,x7,.-4",
                 "jal x5,.+8", "jal x5,.-4", "jalr x5,x6,4", "jalr x5,x6,-2", "jalr x5,x6,0"]:
        w = asm1(line)
        for rs in [{6: 5, 7: 5}, {6: 5, 7: 6}, {6: (1 << 64) - 1, 7: 1},
                   {6: 1 << 63, 7: 1}, {6: 0x400, 7: 0x400}, {6: 0x402, 7: 0}]:
            cases.append((line, repr(rs), w, dict(rs), None, 1))
    # 2-instruction linear sequences: engage basic-block threading.
    for a in ["addw x5,x6,x7", "srlw x5,x6,x7", "sraiw x5,x6,20", "slli x5,x6,40",
              "mulw x5,x6,x7", "sub x5,x6,x7", "add x9,x5,x6"]:
        for b in ["add x9,x5,x6", "addw x9,x5,x6", "srli x9,x5,3", "xor x9,x5,x7"]:
            wa, wb = asm1(a), asm1(b)
            for rs in REG_SETS[:4]:
                cases.append((f"THREAD [{a}; {b}]", repr(rs), [wa, wb], dict(rs), None, 2))

    print(f"{len(cases)} cases\n")
    fails = []
    fastpath_used = 0
    for name, tag, w, regs, mem, nsteps in cases:
        try:
            slow = run(SpatialRV64ICore, w, regs, mem, nsteps)   # decode_and_execute
            fast = run(_CoreFast, w, regs, mem, nsteps)          # execute_decoded / threaded
        except Exception as e:
            print(f"  ERR  {name} {tag}: {e}")
            continue
        if fast["fallback"] < fast["total"]:
            fastpath_used += 1
        ds = diff(slow, fast)
        if ds:
            fails.append((name, tag, ds, slow, fast))
            print(f"  DIFF {name} {tag}")
            for d in ds:
                print(f"       {d}")
            print(f"       slow fb/thr/tot={slow['fallback']}/{slow['threaded']}/{slow['total']}"
                  f"  fast fb/thr/tot={fast['fallback']}/{fast['threaded']}/{fast['total']}")

    print(f"\n{fastpath_used}/{len(cases)} cases actually exercised the fast path")
    if not fails:
        print("NO DIVERGENCE FOUND in tested set.")
        return 0
    print(f"\n{len(fails)} diverging case(s). Diverging mnemonics:")
    seen = []
    for name, *_ in fails:
        m = name.split()[0].split("[")[0]
        if m not in seen:
            seen.append(m)
    for m in seen:
        print(f"  {m}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

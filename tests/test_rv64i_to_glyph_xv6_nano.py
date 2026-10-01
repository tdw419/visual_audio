"""
xv6-nano kernel composition -- see systems/XV6_NANO_ROADMAP.md.

K1: the unified cooperative kernel image (`tests/fixtures/xv6_nano.c`,
`-DSCENARIO=1`) -- `kinit` freelist (G7) + `userinit` proc table (G4) +
`scheduler()` round-robin via the verified `switch_to` primitive (G1/G3) +
per-task console output (G12).

GROUND TRUTH is the GPU `SpatialRV64ICore` (it runs real RISC-V, including
the `switch_to` context-switch asm). GlyphCPUv2 must match it bit-for-bit.
There is no native-x86 execution leg: `switch_to` is RISC-V assembly, so the
image only runs on the two RISC-V engines -- the same 2-way setup G3's
`switch_round_robin` fixture uses. Expected values are hand-derived from the
round-robin schedule and asserted against BOTH engines.

K1 schedule (3 procs, WORK_UNITS=3, scheduler sweeps proc[0..2] per pass):
  pass 1  A B C   (each proc: 1 unit, yield)
  pass 2  A B C
  pass 3  A B C
  pass 4  -       (each proc's loop is done -> state=DONE, yield; no output)
  pass 5  no RUNNABLE -> scheduler returns -> ecall/HALT
  => console "ABCABCABC", 12 switches (9 work + 3 finishing), iters [3,3,3]
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.rv64i_to_glyph import (  # noqa: E402
    PTR_TABLE_BASE,
    GO5_XV6_PTR_TABLE_BASE,
    assemble_glyph_to_pixels,
    build_pointer_table,
    parse_elf,
    parse_elf_data_sections,
    transpile_elf_to_glyph,
)
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.spatial_rv64i_cpu import SpatialRV64ICore  # noqa: E402

_GCC_BIN = "riscv64-unknown-elf-gcc"
_OBJCOPY_BIN = "riscv64-unknown-elf-objcopy"
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "xv6_nano.c"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

# Genuinely-unlowered opcodes (would be real breakage -- no libgcc, no
# mapper case). `sra`/`srai` ARE lowered (sign-extended, commit 7e95e22) and
# `sh`/`lhu`/`auipc` are handled (G10/G11); a *negative* `sra` would still
# diverge on the 64-bit GPU core (G10 class), but that is caught by the
# GPU-vs-Glyph equality assertion, not this fast-fail list.
_FORBIDDEN = {"mul", "mulh", "mulhu", "div", "divu", "rem", "remu", "lh"}


def _build(scenario: int, tmp: Path):
    c_path = tmp / f"xv6_nano_s{scenario}.c"
    c_path.write_text(f'#define SCENARIO {scenario}\n#include "{_FIXTURE}"\n')
    elf_path = tmp / f"s{scenario}.elf"
    bin_path = tmp / f"s{scenario}.bin"
    # The whole kernel (incl. K4's shell) compiles into every scenario now:
    # PTR_TABLE_BASE was raised to 0x1800, clear of the kernel's .bss
    # (~0xC30). Default .bss placement (after .text) is fine.
    # rv64i_to_glyph maps RV xN -> glyph rN 1:1, but glyph r27..r31 are the
    # transpiler's own scratch + hardware call-stack pointer. Small scenarios
    # never make GCC reach for x27..x31; GO-3's SYS_read dispatcher branch has
    # enough register pressure that it does (observed: `dst` landed in x28 =
    # glyph's call-stack pointer -> silent heap corruption). Fence those RV
    # regs off for SCENARIO 9 so codegen stays within the glyph-safe file.
    # SCENARIO 10 (GO-4) and SCENARIO 11 (GO-5) add SYS_draw and shell/dispatch
    # register pressure -- fence x27..x31 off so codegen stays in glyph-safe file.
    extra = (["-ffixed-x27", "-ffixed-x28", "-ffixed-x29", "-ffixed-x30",
              "-ffixed-x31"] if scenario in (9, 10, 11) else [])
    res = subprocess.run(
        [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
         "-fno-builtin", "-w", "-Wl,-Ttext=0x0", *extra,
         str(c_path), "-o", str(elf_path)],
        capture_output=True, text=True)
    assert res.returncode == 0, f"RISC-V GCC failed: {res.stderr}"
    objdump = subprocess.run(
        ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
        capture_output=True, text=True).stdout
    bad = set(re.findall(r"\t([a-z][a-z0-9.]+)\t", objdump)) & _FORBIDDEN
    assert not bad, f"scenario {scenario} codegen uses unlowered/unsafe opcode(s): {bad}"
    subprocess.run([_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)], check=True)
    return elf_path.read_bytes(), bin_path.read_bytes(), objdump


def _read_syms(elf_bytes, tmp, names):
    p = tmp / "sym.elf"
    p.write_bytes(elf_bytes)
    out = subprocess.run(["riscv64-unknown-elf-nm", str(p)], capture_output=True, text=True).stdout
    s = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] in names:
            s[parts[2]] = int(parts[0], 16)
    return s


def _console(word_at, base, clen):
    return bytes((word_at((base + i) & ~3) >> (((base + i) & 3) * 8)) & 0xFF
                 for i in range(clen))


def _sym_ranges(elf_bytes, tmp, names):
    """name -> (start, end) byte range, from `nm --print-size`."""
    p = tmp / "sr.elf"
    p.write_bytes(elf_bytes)
    out = subprocess.run(["riscv64-unknown-elf-nm", "--print-size", "--numeric-sort", str(p)],
                         capture_output=True, text=True).stdout
    r = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] in names:
            start = int(parts[0], 16)
            size = int(parts[1], 16)
            r[parts[3]] = (start, start + size)
    return r


def _run_gpu(bin_data, entry_addr):
    core = SpatialRV64ICore(36864)  # 192*192 perfect square
    core.load_program(bin_data, entry_point=entry_addr)
    st = core.run_until_halt(max_cycles=2_000_000, chunk_size=64)
    assert st["halted"] == 1, "GPU core failed to halt cleanly"
    return core


class _WatchedMem(list):
    """Records (rv_pc, word_index) for every `self.memory[w] = v` the
    GlyphCPUv2 does -- the K3 harness box checker. `_holder[0]` is set to
    the live cpu so __setitem__ can read cpu.pc; `_pcmap` turns the pixel PC
    into the emitted RV byte address."""
    def __init__(self, n):
        super().__init__([0] * n)
        self.stores = []
        self._holder = [None]
        self._pcmap = {}

    def __setitem__(self, i, v):
        if isinstance(i, int):
            cpu = self._holder[0]
            rv_pc = None
            if cpu is not None:
                x, y = cpu.pc
                rv_pc = self._pcmap.get(y * 64 + x // 4)
            self.stores.append((rv_pc, i))
        super().__setitem__(i, v)


def _pcmap_from_source(glyph_source):
    """instruction-index -> RV byte addr, from the emitted `:pc_XXXXXXXX`
    labels (one per RV instruction, before its glyph ops)."""
    m = {}
    idx = 0
    cur = None
    for line in glyph_source.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith(":"):
            if s[1:].startswith("pc_"):
                cur = int(s[4:], 16)
            continue
        m[idx] = cur
        idx += 1
    return m


def _seed_input_ring(write_word, data):
    """GO-3: seed the MMIO input ring the SUPER-mode syscall_dispatch reads
    for SYS_read -- INPUT_LEN + the scripted byte stream packed little-endian
    into INPUT_DATA words. `write_word(byte_addr, u32)` is engine-specific."""
    from tools.glyph_isa_v2 import (
        INPUT_DATA_ADDR, INPUT_DATA_CAP, INPUT_LEN_ADDR,
    )
    assert len(data) <= INPUT_DATA_CAP, "scripted input exceeds INPUT_DATA_CAP"
    write_word(INPUT_LEN_ADDR, len(data))
    for i in range(0, len(data), 4):
        chunk = data[i:i + 4]
        write_word(INPUT_DATA_ADDR + i,
                   int.from_bytes(chunk + b"\x00" * (4 - len(chunk)), "little"))


def _run_glyph(elf_bytes, trace_stores=False, kfault_rv_addr=None, ksys_rv_addr=None,
               input_bytes=None, ptr_table_base=None):
    glyph_source = transpile_elf_to_glyph(elf_bytes, entry_symbol="_start",
                                          byte_to_word_mem=True,
                                          ptr_table_base=ptr_table_base)
    # RULING_go5_ptr_table_vs_bss.md constraint 1: the seeded table base must
    # equal the emitted literal base -- a mismatch is a silent wrong-jump bug.
    _seeded_base = (PTR_TABLE_BASE if ptr_table_base is None
                    else ptr_table_base)
    assert f"LDI r30 0x{_seeded_base:x}" in glyph_source, \
        f"emitted table base literal != seeded base 0x{_seeded_base:x}"
    cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
    pixels, coords = assemble_glyph_to_pixels(glyph_source, cols_instrs=64, min_rows=32)
    mem = _WatchedMem(16384) if trace_stores else None
    cpu.memory = mem if trace_stores else [0] * 16384
    for vaddr, blob in parse_elf_data_sections(elf_bytes):
        for i, byte in enumerate(blob):
            a = vaddr + i
            w = a >> 2
            sh = (a & 3) * 8
            cpu.memory[w] = (cpu.memory[w] & ~(0xFF << sh)) | (byte << sh)
    tv, tb, _ = parse_elf(elf_bytes)
    for wi, packed in build_pointer_table(tb, tv, coords).items():
        idx = (_seeded_base >> 2) + wi
        if 0 <= idx < len(cpu.memory):
            cpu.memory[idx] = packed
    if trace_stores:
        mem._pcmap = _pcmap_from_source(glyph_source)
        mem._holder[0] = cpu
        mem.stores.clear()          # drop the seeding writes above
    if kfault_rv_addr is not None:
        # E-K1: seed the KFAULT_PC reserved MMIO word with the packed pixel
        # PC of the kernel's fault handler. The C kernel writes the box
        # ranges + MODE_LATCH itself, but it has no way to name a pixel
        # coordinate -- so the loader translates &fault_handler here, exactly
        # as it already does for the jalr pointer table.
        from tools.glyph_isa_v2 import KFAULT_PC_ADDR
        col, row = coords[f":pc_{kfault_rv_addr:08x}"]
        cpu.memory[KFAULT_PC_ADDR >> 2] = ((row & 0xFFFF) << 16) | (col & 0xFFFF)
    if ksys_rv_addr is not None:
        from tools.glyph_isa_v2 import KSYS_PC_ADDR
        col, row = coords[f":pc_{ksys_rv_addr:08x}"]
        cpu.memory[KSYS_PC_ADDR >> 2] = ((row & 0xFFFF) << 16) | (col & 0xFFFF)
    if input_bytes is not None:
        _seed_input_ring(lambda a, v: cpu.memory.__setitem__(a >> 2, v), input_bytes)
    cpu.pc = (0, 0)
    cpu.running = True
    for _ in range(3_000_000):
        if not cpu.step(pixels):
            break
    assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"
    return cpu


def test_k1_unified_image():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, _objdump = _build(1, tmp)
        want = {"g_console", "g_clen", "g_total_switches", "g_iters"}
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"
        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        EXP_CONSOLE = b"ABCABCABC"
        EXP_SWITCHES = 12
        EXP_ITERS = [3, 3, 3]

        # --- ground truth: GPU SpatialRV64ICore ---
        gpu = _run_gpu(bin_data, entry_addr)
        g_clen = gpu.read_mem_word(sym["g_clen"]) & 0xFFFFFFFF
        g_console = _console(gpu.read_mem_word, sym["g_console"], g_clen)
        g_switches = gpu.read_mem_word(sym["g_total_switches"]) & 0xFFFFFFFF
        g_iters = [gpu.read_mem_word(sym["g_iters"] + 4 * i) & 0xFFFFFFFF for i in range(3)]
        assert g_console == EXP_CONSOLE, f"GPU console {g_console!r} != {EXP_CONSOLE!r}"
        assert g_switches == EXP_SWITCHES, f"GPU switches {g_switches} != {EXP_SWITCHES}"
        assert g_iters == EXP_ITERS, f"GPU iters {g_iters} != {EXP_ITERS}"

        # --- GlyphCPUv2 must match bit-for-bit ---
        cpu = _run_glyph(elf_bytes)
        y_clen = cpu.memory[sym["g_clen"] >> 2] & 0xFFFFFFFF
        y_console = _console(lambda a: cpu.memory[a >> 2], sym["g_console"], y_clen)
        y_switches = cpu.memory[sym["g_total_switches"] >> 2] & 0xFFFFFFFF
        y_iters = [cpu.memory[(sym["g_iters"] >> 2) + i] & 0xFFFFFFFF for i in range(3)]
        assert y_console == EXP_CONSOLE, f"Glyph console {y_console!r} != {EXP_CONSOLE!r}"
        assert y_switches == EXP_SWITCHES, f"Glyph switches {y_switches} != {EXP_SWITCHES}"
        assert y_iters == EXP_ITERS, f"Glyph iters {y_iters} != {EXP_ITERS}"
        assert (y_console, y_switches, y_iters) == (g_console, g_switches, g_iters), \
            "GlyphCPUv2 diverged from SpatialRV64ICore"


def test_k2_exit_reap():
    """SCENARIO 2: proc[1] runs 2 units then sys_exit(0x42); the scheduler
    marks it ZOMBIE, reaps its exit code, drops it from the run queue;
    proc[0]/proc[2] finish their 3 units; the image halts when the queue
    empties.

    sweep 1  A B C
    sweep 2  A B C
    sweep 3  A  (p1: loop done -> sys_exit(0x42) -> ZOMBIE, reaped)  C
    sweep 4  (p0 DONE)  (p1 ZOMBIE, skipped -- no switch)  (p2 DONE)
    => console "ABCABCAC", switches 3+3+3+2 = 11, iters [3,2,3],
       g_xcode [0, 0x42, 0], g_reaped_mask 0b010
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, _ = _build(2, tmp)
        want = {"g_console", "g_clen", "g_total_switches", "g_iters",
                "g_xcode", "g_reaped_mask"}
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"
        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        EXP_CONSOLE = b"ABCABCAC"
        EXP_SWITCHES = 11
        EXP_ITERS = [3, 2, 3]
        EXP_XCODE = [0, 0x42, 0]
        EXP_REAPED = 0b010

        def read_all(word_at, w2=None):
            wa = word_at if w2 is None else w2
            clen = wa(sym["g_clen"]) & 0xFFFFFFFF
            return (
                _console(wa, sym["g_console"], clen),
                wa(sym["g_total_switches"]) & 0xFFFFFFFF,
                [wa(sym["g_iters"] + 4 * i) & 0xFFFFFFFF for i in range(3)],
                [wa(sym["g_xcode"] + 4 * i) & 0xFFFFFFFF for i in range(3)],
                wa(sym["g_reaped_mask"]) & 0xFFFFFFFF,
            )

        gpu = _run_gpu(bin_data, entry_addr)
        g = read_all(gpu.read_mem_word)
        assert g == (EXP_CONSOLE, EXP_SWITCHES, EXP_ITERS, EXP_XCODE, EXP_REAPED), \
            f"GPU {g!r} != expected"

        cpu = _run_glyph(elf_bytes)
        y = read_all(None, w2=lambda a: cpu.memory[a >> 2])
        assert y == (EXP_CONSOLE, EXP_SWITCHES, EXP_ITERS, EXP_XCODE, EXP_REAPED), \
            f"Glyph {y!r} != expected"
        assert y == g, "GlyphCPUv2 diverged from SpatialRV64ICore"


def _boxsum_check(scenario, tmp):
    """Run scenario, return (gpu_boxsum, glyph_boxsum, out_of_box_words,
    arena_base_addr) -- the K3 oracle pieces."""
    elf_bytes, bin_data, _ = _build(scenario, tmp)
    sym = _read_syms(elf_bytes, tmp, {"g_boxsum", "g_arena", "proc"})
    rng = _sym_ranges(elf_bytes, tmp,
                      {"box_fill", "box_over", "proc", "g_boxsum", "kmem_pool"})
    assert "box_fill" in rng, "box_fill not found"
    _tv, _tb, symbols = parse_elf(elf_bytes)
    entry_addr = next(a for a, n in symbols.items() if n == "_start")

    gpu = _run_gpu(bin_data, entry_addr)
    gpu_boxsum = [gpu.read_mem_word(sym["g_boxsum"] + 4 * i) & 0xFFFFFFFF for i in range(3)]

    cpu = _run_glyph(elf_bytes, trace_stores=True)
    glyph_boxsum = [cpu.memory[(sym["g_boxsum"] >> 2) + i] & 0xFFFFFFFF for i in range(3)]

    task_lo_hi = [rng["box_fill"]] + ([rng["box_over"]] if "box_over" in rng else [])

    def in_task_code(pc):
        return pc is not None and any(lo <= pc < hi for lo, hi in task_lo_hi)

    arena_w0 = sym["g_arena"] >> 2
    arena_w_end = arena_w0 + (192 >> 2)          # NPROC*ARENA_SLOT = 192 bytes = 48 words
    # A box task legitimately also touches the kernel objects the kernel
    # hands it: its declared output slot g_boxsum[id], its own proc entry
    # (state=DONE / xcode, always-inlined at the task PC), and its kernel
    # stack (kmem_pool). Those are whitelisted; anything else outside the
    # arena is a box violation.
    def whitelisted(w):
        if arena_w0 <= w < arena_w_end:
            return True
        for name in ("g_boxsum", "proc", "kmem_pool"):
            lo, hi = rng.get(name, (1, 0))
            if lo >> 2 <= w < (hi + 3) >> 2:
                return True
        return False

    oob = sorted({w for pc, w in cpu.memory.stores
                  if in_task_code(pc) and not whitelisted(w)})
    return gpu_boxsum, glyph_boxsum, oob, sym["g_arena"]


def test_k3_in_box():
    """SCENARIO 3: every proc fills only its own arena slot -> the box
    checker sees zero task stores outside the arena, and the per-slot
    checksums agree GPU vs Glyph."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gpu_bs, gl_bs, oob, _arena = _boxsum_check(3, tmp)
        EXP = [64 * 0x41, 64 * 0x42, 64 * 0x43]   # 4160, 4224, 4288
        assert gpu_bs == EXP, f"GPU boxsum {gpu_bs} != {EXP}"
        assert gl_bs == EXP, f"Glyph boxsum {gl_bs} != {EXP}"
        assert gl_bs == gpu_bs
        assert oob == [], f"in-box scenario had out-of-box task stores: {oob!r}"


def test_k3_out_of_box_flagged():
    """SCENARIO 4: proc[2] writes one byte past the arena. The box checker's
    out-of-box set is exactly {word(g_arena + NPROC*ARENA_SLOT)}."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        gpu_bs, gl_bs, oob, arena = _boxsum_check(4, tmp)
        EXP = [64 * 0x41, 64 * 0x42, 64 * 0x43]
        assert gpu_bs == EXP and gl_bs == EXP, f"boxsum GPU {gpu_bs} Glyph {gl_bs} != {EXP}"
        expected_oob_word = (arena + 192) >> 2
        assert oob == [expected_oob_word], (
            f"box checker flagged {oob!r}, expected exactly [{expected_oob_word}] "
            f"(g_arena=0x{arena:x} + 192)")


def test_k4_nano_shell():
    """SCENARIO 5: proc[0] runs the shell over canned input
    "help\\necho hi there\\nps\\n". First-word tokenizer, cmd_table[] of
    {name, fn} dispatched through a function pointer (the G5 jalr primitive;
    _run_glyph seeds PTR_TABLE_BASE for it). Expected console:
      help    -> "help ps echo\\n"
      echo .. -> "hi there\\n"
      ps      -> proc[0]=RUNNING, proc[1..2]=UNUSED -> "R--\\n"
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, _ = _build(5, tmp)
        sym = _read_syms(elf_bytes, tmp, {"g_console", "g_clen"})
        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        WANT = b"help ps echo\nhi there\nR--\n"

        gpu = _run_gpu(bin_data, entry_addr)
        g_clen = gpu.read_mem_word(sym["g_clen"]) & 0xFFFFFFFF
        g_console = _console(gpu.read_mem_word, sym["g_console"], g_clen)
        assert g_console == WANT, f"GPU console {g_console!r} != {WANT!r}"

        cpu = _run_glyph(elf_bytes)
        y_clen = cpu.memory[sym["g_clen"] >> 2] & 0xFFFFFFFF
        y_console = _console(lambda a: cpu.memory[a >> 2], sym["g_console"], y_clen)
        assert y_console == WANT, f"Glyph console {y_console!r} != {WANT!r}"
        assert y_console == g_console, "GlyphCPUv2 diverged from SpatialRV64ICore"


def _body(objdump, name):
    """The disassembly lines of one function, `<name>:` to the next blank."""
    out, grab = [], False
    for line in objdump.splitlines():
        if line.endswith(f"<{name}>:"):
            grab = True
            continue
        if grab:
            if not line.strip():
                break
            out.append(line)
    return out


def test_ek1_bounded_user_store():
    """SCENARIO 6 -- GlyphCPUv2 itself enforces each user task's memory box.

    proc[0]/proc[1] run `s6_inbox`: fill their own arena slot, mark
    themselves DONE (their proc[] entry -- box1), yield. proc[2] runs
    `s6_over`: fills its slot, then stores one byte past the whole arena --
    outside box0 and box1. GlyphCPUv2 blocks the store, records FAULT_ADDR,
    drops to SUPER and vectors to `fault_handler`, which reaps proc[2]
    (state=FAULTED, g_fault_pid). proc[0]/proc[1] finish; the image halts.

    Per roadmap E5 the fault path has no GPU oracle (SpatialRV64ICore has no
    box -- it would just perform the store). The GPU leg only anchors the
    in-box writes; the trap itself is checked GlyphCPUv2-vs-contract.
    """
    from tools.glyph_isa_v2 import MODE_SUPER

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, objdump = _build(6, tmp)

        want = {"g_arena", "g_fault_pid", "g_fault_addr", "proc",
                "fault_handler"}
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"
        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # s6_inbox is a non-leaf (it yields): its switch_to prologue spills
        # ra/s0 to the kalloc'd stack page -> that page is box2. If box2 were
        # wrong the spill itself would trap and proc[0] would never reach
        # DONE, so the [DONE, DONE, FAULTED] assertion below is the real
        # check. This just documents the layout that makes box2 necessary.
        assert any(re.search(r"\bsw\b\s+ra,\s*-?\d+\(sp\)", ln)
                   for ln in _body(objdump, "s6_inbox")), \
            "expected s6_inbox to spill ra to its stack (box2 rationale)"

        ARENA = sym["g_arena"]
        ARENA_BYTES = 3 * 64
        PROC = sym["proc"]
        DONE, FAULTED = 3, 5

        # --- GPU leg: reference for the in-box arena fills only ---
        gpu = _run_gpu(bin_data, entry_addr)
        gpu_arena = bytes(_console(gpu.read_mem_word, ARENA, ARENA_BYTES))
        assert gpu_arena == (b"\x41" * 64 + b"\x42" * 64 + b"\x43" * 64), \
            f"GPU arena fill unexpected: {gpu_arena!r}"

        # --- GlyphCPUv2 with enforcement ---
        cpu = _run_glyph(elf_bytes, kfault_rv_addr=sym["fault_handler"])

        gl_arena = bytes((cpu.memory[(ARENA + i) >> 2] >> (((ARENA + i) & 3) * 8)) & 0xFF
                         for i in range(ARENA_BYTES))
        assert gl_arena == gpu_arena, \
            f"in-box fills diverged: Glyph {gl_arena!r} != GPU {gpu_arena!r}"

        # the blocked store never landed
        past = ARENA + ARENA_BYTES
        past_byte = (cpu.memory[past >> 2] >> ((past & 3) * 8)) & 0xFF
        assert past_byte == 0, f"out-of-box store was NOT blocked (g_arena[192]=0x{past_byte:02x})"

        # exactly proc[2] was reaped, at exactly that address
        assert (cpu.memory[sym["g_fault_pid"] >> 2] & 0xFFFFFFFF) == 3, "wrong / no g_fault_pid"
        assert (cpu.memory[sym["g_fault_addr"] >> 2] & 0xFFFFFFFF) == past, \
            f"g_fault_addr 0x{cpu.memory[sym['g_fault_addr'] >> 2]:x} != 0x{past:x}"

        st = [cpu.memory[(PROC + i * 128 + 64) >> 2] & 0xFFFFFFFF for i in range(3)]
        assert st == [DONE, DONE, FAULTED], f"proc states {st} != [DONE, DONE, FAULTED]"

        # engine ended cleanly, back in supervisor mode, fault latched
        assert cpu.mode == MODE_SUPER, f"engine left in mode {cpu.mode}"
        assert cpu.faulted is True, "cpu.faulted not set"


def test_ek2_syscall_boundary():
    """SCENARIO 7 -- the only sanctioned USER->kernel path is SYSCALL.

    proc[0] runs `s7_task`: writes its arena slot (in-box), then
    `__syscall(SYS_write, "hi\\n", 3)` -- lowered to `ebreak` -> glyph
    SYSCALL. GlyphCPUv2 marshals a7/a0/a1 into ISO_SYS_*, drops to SUPER,
    jumps the loader-seeded KSYS_PC (`syscall_dispatch`), which writes "hi\\n"
    to g_console and `mret`s (-> SYSRET: mode=USER, result to a0, resume
    after the ebreak). The task then does a DIRECT `g_console[0] = '!'` --
    kernel memory, outside its box -> E-K1 trap -> fault_handler reaps it.

    No GPU leg: SpatialRV64ICore models neither `ebreak`-as-syscall nor
    `mret` nor the box, so per roadmap E5 this is GlyphCPUv2-vs-contract.
    """
    from tools.glyph_isa_v2 import MODE_SUPER

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, _bin, objdump = _build(7, tmp)
        want = {"g_console", "g_clen", "g_fault_pid", "g_fault_addr", "proc",
                "fault_handler", "syscall_dispatch"}
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"

        cpu = _run_glyph(elf_bytes,
                         kfault_rv_addr=sym["fault_handler"],
                         ksys_rv_addr=sym["syscall_dispatch"])

        CONSOLE, CLEN, PROC = sym["g_console"], sym["g_clen"], sym["proc"]
        FAULTED = 5

        clen = cpu.memory[CLEN >> 2] & 0xFFFFFFFF
        console = bytes((cpu.memory[(CONSOLE + i) >> 2] >> (((CONSOLE + i) & 3) * 8)) & 0xFF
                        for i in range(clen))

        # the syscall's output is there; the blocked direct write ('!' at
        # index 0) is NOT (else byte 0 would be 0x21 and clen would differ)
        assert console == b"hi\n", f"console {console!r} != b'hi\\n' (clen={clen})"

        assert (cpu.memory[sym["g_fault_pid"] >> 2] & 0xFFFFFFFF) == 1, "wrong / no g_fault_pid"
        assert (cpu.memory[sym["g_fault_addr"] >> 2] & 0xFFFFFFFF) == CONSOLE, \
            f"g_fault_addr 0x{cpu.memory[sym['g_fault_addr'] >> 2]:x} != &g_console 0x{CONSOLE:x}"
        assert (cpu.memory[(PROC + 64) >> 2] & 0xFFFFFFFF) == FAULTED, \
            "proc[0] not FAULTED after the illegal direct write"
        assert cpu.mode == MODE_SUPER and cpu.faulted is True


# --- GO-1: the E-K1/E-K2 isolation layer, ported to the GPU engine --------
# systems/GPU_OS_ROADMAP.md. SpatialRV64ICore gains a mode bit + 3-range box
# check on user-mode stores + trap-to-KFAULT_PC + ebreak/mret syscall path
# (reversing isolation-roadmap non-goal E). GlyphCPUv2 stays the bit-exact
# reference; this test runs SCENARIO 6 + 7 on BOTH engines and asserts the
# GPU results equal the GlyphCPUv2 results.
#
# GPU reserved-block byte layout mirrors BOX_MMIO_BASE in glyph_isa_v2.py.
# Unlike GlyphCPUv2 (packed pixel PCs) the GPU engine runs a flat binary, so
# KFAULT_PC / KSYS_PC / switch_to range are seeded as real RV byte addresses.
_ISO_KFAULT_PC_ADDR = 0x8004
_ISO_KSYS_PC_ADDR = 0x8008
_ISO_SWITCH_LO_ADDR = 0x8040   # GPU-only: switch_to's byte range; its terminal
_ISO_SWITCH_HI_ADDR = 0x8044   # `ret` is GlyphCPUv2's KJMP privilege boundary


def _run_gpu_iso(bin_data, entry_addr, kfault_addr, ksys_addr, switch_lo, switch_hi,
                 input_bytes=None):
    core = SpatialRV64ICore(36864)  # same core the K1-K4 GPU leg uses; 0x8000
    core.load_program(bin_data, entry_point=entry_addr)  # block + GPR snapshot
    core.write_mem_word(_ISO_KFAULT_PC_ADDR, kfault_addr)  # fit under 0x8150
    if ksys_addr:
        core.write_mem_word(_ISO_KSYS_PC_ADDR, ksys_addr)
    core.write_mem_word(_ISO_SWITCH_LO_ADDR, switch_lo)
    core.write_mem_word(_ISO_SWITCH_HI_ADDR, switch_hi)
    if input_bytes is not None:                            # GO-3: MMIO input ring
        _seed_input_ring(core.write_mem_word, input_bytes)
    st = core.run_until_halt(max_cycles=2_000_000, chunk_size=64)
    assert st["halted"] == 1, "GPU core failed to halt cleanly"
    return core


def _gpu_iso_results(core, sym):
    clen = core.read_mem_word(sym["g_clen"]) & 0xFFFFFFFF
    console = _console(core.read_mem_word, sym["g_console"], clen)
    states = [core.read_mem_word(sym["proc"] + i * 128 + 64) & 0xFFFFFFFF for i in range(3)]
    return {
        "g_fault_pid": core.read_mem_word(sym["g_fault_pid"]) & 0xFFFFFFFF,
        "g_fault_addr": core.read_mem_word(sym["g_fault_addr"]) & 0xFFFFFFFF,
        "proc_states": states,
        "g_console": console,
        "g_clen": clen,
    }


def _glyph_iso_results(cpu, sym):
    clen = cpu.memory[sym["g_clen"] >> 2] & 0xFFFFFFFF
    console = _console(lambda a: cpu.memory[a >> 2], sym["g_console"], clen)
    states = [cpu.memory[(sym["proc"] + i * 128 + 64) >> 2] & 0xFFFFFFFF for i in range(3)]
    return {
        "g_fault_pid": cpu.memory[sym["g_fault_pid"] >> 2] & 0xFFFFFFFF,
        "g_fault_addr": cpu.memory[sym["g_fault_addr"] >> 2] & 0xFFFFFFFF,
        "proc_states": states,
        "g_console": console,
        "g_clen": clen,
    }


@pytest.mark.parametrize("scenario", [6, 7])
def test_go1_isolation_on_gpu(scenario):
    """SCENARIO 6 + 7 run on SpatialRV64ICore with the isolation layer and
    produce results bit-identical to GlyphCPUv2 (`_run_glyph`):
    g_fault_pid, g_fault_addr, proc[] states, g_console, g_clen."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, _objdump = _build(scenario, tmp)

        want = {"g_console", "g_clen", "g_fault_pid", "g_fault_addr", "proc",
                "g_arena", "fault_handler", "switch_to"}
        if scenario == 7:
            want.add("syscall_dispatch")
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"
        # switch_to is a bare __asm__ block (no .size directive), so nm reports
        # no size -- derive its byte range from the disassembly instead.
        _sw_lines = _body(_objdump, "switch_to")
        assert _sw_lines, "switch_to not in disassembly"
        _sw_addrs = [int(ln.split(":")[0].strip(), 16) for ln in _sw_lines
                     if ln.strip() and ":" in ln and ln.split(":")[0].strip()]
        switch_lo, switch_hi = _sw_addrs[0], _sw_addrs[-1] + 4

        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")
        ksys_addr = sym["syscall_dispatch"] if scenario == 7 else 0

        # --- GlyphCPUv2 reference (the bit-exact oracle) ---
        cpu = _run_glyph(
            elf_bytes,
            kfault_rv_addr=sym["fault_handler"],
            ksys_rv_addr=(sym["syscall_dispatch"] if scenario == 7 else None),
        )
        want_res = _glyph_iso_results(cpu, sym)

        # --- GPU SpatialRV64ICore with the GO-1 isolation layer ---
        core = _run_gpu_iso(bin_data, entry_addr, sym["fault_handler"],
                            ksys_addr, switch_lo, switch_hi)
        got_res = _gpu_iso_results(core, sym)

        assert got_res == want_res, (
            f"scenario {scenario}: GPU isolation result diverged from GlyphCPUv2\n"
            f"  GPU   = {got_res}\n  Glyph = {want_res}")

        # sanity: the box actually blocked something and the survivors ran
        FAULTED = 5
        assert FAULTED in got_res["proc_states"], "no proc was reaped"
        if scenario == 7:
            assert got_res["g_console"] == b"hi\n"


# --- GO-2: the box as a 2D tile -----------------------------------------------
# systems/GPU_OS_ROADMAP.md GO-2 (folds in isolation-roadmap E-K3). A task's
# permitted memory is a rectangle on the pixel grid: byte addr a -> word a>>2
# -> (row,col) = (w // W_MEM, w % W_MEM). W_MEM is shared byte-for-byte across
# tools/glyph_isa_v2.py, tools/SPATIAL_RV64I.wgsl and tests/fixtures/xv6_nano.c.
# SCENARIO 8: one task confined to a tile fills every in-tile cell (no trap),
# then stores one cell of the row just below the tile -> trap -> reaped. Run
# on BOTH engines; assert bit-identical.
_S8_TROW, _S8_TCOL, _S8_TH, _S8_TW = 4, 8, 4, 8


@pytest.mark.parametrize("scenario", [8])
def test_go2_tile_box_on_gpu(scenario):
    """SCENARIO 8 -- a task whose box is a 2D tile (row, col, h, w) in grid
    coordinates. In-tile strided writes must not trap; one out-of-tile store
    traps into fault_handler and the proc is reaped. GlyphCPUv2 (the bit-exact
    reference) and SpatialRV64ICore must agree on g_fault_pid, g_fault_addr,
    proc[] states, g_console, g_clen -- and on the tile contents of g_grid."""
    from tools.glyph_isa_v2 import W_MEM

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, _objdump = _build(scenario, tmp)

        want = {"g_console", "g_clen", "g_fault_pid", "g_fault_addr", "proc",
                "g_grid", "fault_handler", "switch_to"}
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"

        _sw_lines = _body(_objdump, "switch_to")
        assert _sw_lines, "switch_to not in disassembly"
        _sw_addrs = [int(ln.split(":")[0].strip(), 16) for ln in _sw_lines
                     if ln.strip() and ":" in ln and ln.split(":")[0].strip()]
        switch_lo, switch_hi = _sw_addrs[0], _sw_addrs[-1] + 4

        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        GRID = sym["g_grid"]

        def _cell(r, c):
            return GRID + ((_S8_TROW + r) * W_MEM + (_S8_TCOL + c)) * 4
        oob = GRID + ((_S8_TROW + _S8_TH) * W_MEM + _S8_TCOL) * 4

        # --- GlyphCPUv2 reference (the bit-exact oracle) ---
        cpu = _run_glyph(elf_bytes, kfault_rv_addr=sym["fault_handler"])
        want_res = _glyph_iso_results(cpu, sym)

        # --- GPU SpatialRV64ICore with the GO-2 tile predicate ---
        core = _run_gpu_iso(bin_data, entry_addr, sym["fault_handler"],
                            0, switch_lo, switch_hi)
        got_res = _gpu_iso_results(core, sym)

        assert got_res == want_res, (
            f"scenario {scenario}: GPU tile result diverged from GlyphCPUv2\n"
            f"  GPU   = {got_res}\n  Glyph = {want_res}")

        # the trap fired at the first cell below the tile, proc[0] reaped
        assert got_res["g_fault_addr"] == oob, \
            f"g_fault_addr 0x{got_res['g_fault_addr']:x} != &g_grid OOB 0x{oob:x}"
        assert got_res["g_fault_pid"] == 1
        assert got_res["proc_states"][0] == 5, "proc[0] not FAULTED"

        # every in-tile cell got written (0x41 + id, id == 0); nothing else did
        for reader in (core.read_mem_word, lambda a: cpu.memory[a >> 2]):
            written = 0
            for r in range(_S8_TH):
                for c in range(_S8_TW):
                    v = reader(_cell(r, c)) & 0xFFFFFFFF
                    assert v == 0x41, f"in-tile cell ({r},{c}) = 0x{v:x} != 0x41"
                    written += 1
            assert written == _S8_TH * _S8_TW, "wrong in-tile cell count"
            assert reader(oob) & 0xFFFFFFFF == 0, "the out-of-tile store landed"


# --- GO-3: real interactive shell input --------------------------------------
# systems/GPU_OS_ROADMAP.md GO-3. K4's nano-shell read a canned g_shell_input[];
# GO-3 feeds it host input through SYS_read (syscall #2) backed by an MMIO input
# ring (INPUT_LEN/CURSOR/DATA at BOX_MMIO_BASE + 0x170/0x174/0x180) the harness
# fills before the run. The SUPER-mode C syscall_dispatch copies one line out of
# the ring per SYS_read and advances the cursor; 0 bytes = input exhausted.
# SCENARIO 9: the shell runs a scripted command sequence and its console output
# is bit-identical between GlyphCPUv2 (reference) and SpatialRV64ICore. No engine
# change -- the dispatcher runs in SUPER, so its ring loads / buffer stores are
# never box-checked; GO-3 is fixture + test only.
_GO3_SCRIPT = b"echo hi\nhelp\nps\n"
_GO3_WANT = b"hi\nhelp ps echo\nR--\n"


@pytest.mark.parametrize("scenario", [9])
def test_go3_shell_input_on_gpu(scenario):
    """SCENARIO 9 -- the nano-shell reads a host-fed scripted command sequence
    via SYS_read from an MMIO input ring, dispatches each command through the
    G5 fn-pointer table, and routes every command's output through
    __syscall(SYS_write, ...). GlyphCPUv2 (the bit-exact reference) and
    SpatialRV64ICore must produce identical g_console / g_clen, equal to the
    expected transcript."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, _objdump = _build(scenario, tmp)

        want = {"g_console", "g_clen", "proc", "fault_handler",
                "syscall_dispatch", "switch_to"}
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"

        _sw_lines = _body(_objdump, "switch_to")
        assert _sw_lines, "switch_to not in disassembly"
        _sw_addrs = [int(ln.split(":")[0].strip(), 16) for ln in _sw_lines
                     if ln.strip() and ":" in ln and ln.split(":")[0].strip()]
        switch_lo, switch_hi = _sw_addrs[0], _sw_addrs[-1] + 4

        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # --- GlyphCPUv2 reference (the bit-exact oracle) ---
        cpu = _run_glyph(elf_bytes,
                         kfault_rv_addr=sym["fault_handler"],
                         ksys_rv_addr=sym["syscall_dispatch"],
                         input_bytes=_GO3_SCRIPT)
        y_clen = cpu.memory[sym["g_clen"] >> 2] & 0xFFFFFFFF
        y_console = _console(lambda a: cpu.memory[a >> 2], sym["g_console"], y_clen)

        # --- GPU SpatialRV64ICore with the GO-1/GO-2 isolation layer ---
        core = _run_gpu_iso(bin_data, entry_addr, sym["fault_handler"],
                            sym["syscall_dispatch"], switch_lo, switch_hi,
                            input_bytes=_GO3_SCRIPT)
        g_clen = core.read_mem_word(sym["g_clen"]) & 0xFFFFFFFF
        g_console = _console(core.read_mem_word, sym["g_console"], g_clen)

        assert y_console == _GO3_WANT, f"Glyph console {y_console!r} != {_GO3_WANT!r}"
        assert g_console == _GO3_WANT, f"GPU console {g_console!r} != {_GO3_WANT!r}"
        assert (y_console, y_clen) == (g_console, g_clen), \
            "GlyphCPUv2 diverged from SpatialRV64ICore"


# --- GO-4: framebuffer output ----------------------------------------------
# systems/GPU_OS_ROADMAP.md GO-4. A W_MEM-aligned fixture global unsigned
# g_fb[W_MEM * FB_H] IS the screen -- FB row y is grid row base+y, using the
# first FB_W words of each W_MEM-wide grid row (a genuine rectangle on the
# GO-2 pixel grid). SYS_draw (syscall #3): __syscall(SYS_draw, (y<<16)|x, val)
# -> the SUPER-mode syscall_dispatch writes g_fb[y*W_MEM + x] = val iff
# x < FB_W && y < FB_H, else returns (uint)-1. SCENARIO 10: the shell reads
# "plot\n" via GO-3's SYS_read, runs cmd `plot`, which SYS_draws a
# deterministic pattern (0x40 + ((x+y)&0x0F)) over the whole rect. g_fb reads
# back bit-identical between GlyphCPUv2 (reference) and SpatialRV64ICore and
# equal to the expected pattern. No engine change -- fixture + test only.
_GO4_FB_W = 8
_GO4_FB_H = 6
_GO4_SCRIPT = b"plot\n"


@pytest.mark.parametrize("scenario", [10])
def test_go4_framebuffer_on_gpu(scenario):
    """SCENARIO 10 -- the nano-shell reads "plot\\n" via SYS_read, dispatches
    `plot` through the G5 fn-pointer table, and cmd9_plot draws every cell of
    the FB rect via __syscall(SYS_draw, ...). GlyphCPUv2 (the bit-exact
    reference) and SpatialRV64ICore must produce an identical g_fb, equal to
    the pattern 0x40 + ((x + y) & 0x0F), with a word just outside the rect
    left at 0 (bounds check + no spillover)."""
    from tools.glyph_isa_v2 import W_MEM
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, _objdump = _build(scenario, tmp)

        want = {"g_fb", "g_console", "g_clen", "proc", "fault_handler",
                "syscall_dispatch", "switch_to"}
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"

        _sw_lines = _body(_objdump, "switch_to")
        assert _sw_lines, "switch_to not in disassembly"
        _sw_addrs = [int(ln.split(":")[0].strip(), 16) for ln in _sw_lines
                     if ln.strip() and ":" in ln and ln.split(":")[0].strip()]
        switch_lo, switch_hi = _sw_addrs[0], _sw_addrs[-1] + 4

        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        FB = sym["g_fb"]

        def _cell(reader, x, y):
            return reader(FB + (y * W_MEM + x) * 4) & 0xFFFFFFFF

        # --- GlyphCPUv2 reference (the bit-exact oracle) ---
        cpu = _run_glyph(elf_bytes,
                         kfault_rv_addr=sym["fault_handler"],
                         ksys_rv_addr=sym["syscall_dispatch"],
                         input_bytes=_GO4_SCRIPT)
        y_read = lambda a: cpu.memory[a >> 2]

        # --- GPU SpatialRV64ICore with the GO-1/GO-2 isolation layer ---
        core = _run_gpu_iso(bin_data, entry_addr, sym["fault_handler"],
                            sym["syscall_dispatch"], switch_lo, switch_hi,
                            input_bytes=_GO4_SCRIPT)
        g_read = core.read_mem_word

        for y in range(_GO4_FB_H):
            for x in range(_GO4_FB_W):
                exp = 0x40 + ((x + y) & 0x0F)
                yv, gv = _cell(y_read, x, y), _cell(g_read, x, y)
                assert yv == exp, f"Glyph g_fb[{x},{y}]=0x{yv:x} != 0x{exp:x}"
                assert gv == exp, f"GPU g_fb[{x},{y}]=0x{gv:x} != 0x{exp:x}"
                assert yv == gv, f"g_fb[{x},{y}] Glyph 0x{yv:x} != GPU 0x{gv:x}"

        # words just right of the drawn rect (still inside g_fb, never a draw
        # target since x < FB_W) stayed 0 -- bounds check held, no row spillover
        for oob in (FB + _GO4_FB_W * 4, FB + (W_MEM + _GO4_FB_W) * 4):
            assert y_read(oob) & 0xFFFFFFFF == 0, "Glyph: out-of-rect word written"
            assert g_read(oob) & 0xFFFFFFFF == 0, "GPU: out-of-rect word written"


# --- GO-5: end-to-end GPU OS scenario --------------------------------------
# systems/GPU_OS_ROADMAP.md GO-5. Compose GO-1..GO-4: 3 procs, each a disjoint tile,
# isolation enforced. proc[0] runs the nano-shell over host-fed scripted input;
# a text command writes to console via SYS_write, `plot` draws the framebuffer
# via SYS_draw, and `ps` shows proc states. proc[1] runs, yields, and exits
# cleanly. proc[2] makes one deliberate out-of-tile store that traps into
# fault_handler and is reaped (K2) with trap exit code 139.
_GO5_FB_W = 8
_GO5_FB_H = 6
_GO5_SCRIPT = b"echo hi\nplot\nps\n"
_GO5_WANT = b"hi\nRZZ\n"


@pytest.mark.parametrize("scenario", [11])
def test_go5_e2e_on_gpu(scenario):
    """SCENARIO 11 (GO-5) -- full composition on SpatialRV64ICore vs GlyphCPUv2:
    all 3 procs isolated in disjoint 2D tiles, shell running scripted commands,
    framebuffer drawn, out-of-tile store trapped and reaped, clean termination."""
    from tools.glyph_isa_v2 import W_MEM
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        elf_bytes, bin_data, _objdump = _build(scenario, tmp)

        want = {"g_fb", "g_console", "g_clen", "g_xcode", "g_reaped_mask",
                "proc", "fault_handler", "syscall_dispatch", "switch_to"}
        sym = _read_syms(elf_bytes, tmp, want)
        assert want <= set(sym), f"missing symbols: {want - set(sym)}"

        _sw_lines = _body(_objdump, "switch_to")
        assert _sw_lines, "switch_to not in disassembly"
        _sw_addrs = [int(ln.split(":")[0].strip(), 16) for ln in _sw_lines
                     if ln.strip() and ":" in ln and ln.split(":")[0].strip()]
        switch_lo, switch_hi = _sw_addrs[0], _sw_addrs[-1] + 4

        _tv, _tb, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        FB = sym["g_fb"]

        def _cell(reader, x, y):
            return reader(FB + (y * W_MEM + x) * 4) & 0xFFFFFFFF

        # --- GlyphCPUv2 reference (the bit-exact oracle) ---
        cpu = _run_glyph(elf_bytes,
                         kfault_rv_addr=sym["fault_handler"],
                         ksys_rv_addr=sym["syscall_dispatch"],
                         input_bytes=_GO5_SCRIPT,
                         ptr_table_base=GO5_XV6_PTR_TABLE_BASE)
        y_read = lambda a: cpu.memory[a >> 2]

        # --- GPU SpatialRV64ICore with the GO-1/GO-2 isolation layer ---
        core = _run_gpu_iso(bin_data, entry_addr, sym["fault_handler"],
                            sym["syscall_dispatch"], switch_lo, switch_hi,
                            input_bytes=_GO5_SCRIPT)
        g_read = core.read_mem_word

        # Clause 1 & 2: bit-identical console and matches expected transcript
        y_clen = y_read(sym["g_clen"]) & 0xFFFFFFFF
        g_clen = g_read(sym["g_clen"]) & 0xFFFFFFFF
        assert y_clen == g_clen, f"g_clen Glyph {y_clen} != GPU {g_clen}"

        y_console = _console(y_read, sym["g_console"], y_clen)
        g_console = _console(g_read, sym["g_console"], g_clen)
        assert y_console == _GO5_WANT, f"Glyph console {y_console!r} != {_GO5_WANT!r}"
        assert g_console == _GO5_WANT, f"GPU console {g_console!r} != {_GO5_WANT!r}"
        assert y_console == g_console, "g_console Glyph diverged from GPU"

        # Clause 1 & 3: bit-identical g_fb and matches SCENARIO 10 pattern
        for y in range(_GO5_FB_H):
            for x in range(_GO5_FB_W):
                exp = 0x40 + ((x + y) & 0x0F)
                yv, gv = _cell(y_read, x, y), _cell(g_read, x, y)
                assert yv == exp, f"Glyph g_fb[{x},{y}]=0x{yv:x} != 0x{exp:x}"
                assert gv == exp, f"GPU g_fb[{x},{y}]=0x{gv:x} != 0x{exp:x}"
                assert yv == gv, f"g_fb[{x},{y}] Glyph 0x{yv:x} != GPU 0x{gv:x}"

        # Clause 1, 4 & 5: g_reaped_mask and g_xcode
        y_reaped = y_read(sym["g_reaped_mask"]) & 0xFFFFFFFF
        g_reaped = g_read(sym["g_reaped_mask"]) & 0xFFFFFFFF
        assert y_reaped == 0b111, f"Glyph g_reaped_mask {y_reaped:#b} != 0b111"
        assert g_reaped == 0b111, f"GPU g_reaped_mask {g_reaped:#b} != 0b111"
        assert y_reaped == g_reaped, f"g_reaped_mask Glyph {y_reaped:#b} != GPU {g_reaped:#b}"

        y_xcode = [y_read(sym["g_xcode"] + 4 * i) & 0xFFFFFFFF for i in range(3)]
        g_xcode = [g_read(sym["g_xcode"] + 4 * i) & 0xFFFFFFFF for i in range(3)]
        assert y_xcode == [0, 0, 139], f"Glyph g_xcode {y_xcode} != [0, 0, 139]"
        assert g_xcode == [0, 0, 139], f"GPU g_xcode {g_xcode} != [0, 0, 139]"
        assert y_xcode == g_xcode, f"g_xcode Glyph {y_xcode} != GPU {g_xcode}"


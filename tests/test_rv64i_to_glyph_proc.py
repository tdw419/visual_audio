"""
Proc table / cooperative scheduler differential test: dynamic JALR dispatch.

This is the third untested instruction pattern after bump_alloc (globals/calls)
and fifo (struct fields/wraparound): JALR with a runtime-computed target — the
swtch-style indirect jump. GCC's function-pointer idiom emits
`jalr ra, 0(a5)`: jump through a register holding a RISC-V BYTE address loaded
from data. Two real bugs were found and fixed here:

1. Bare-JMPR bug: rd!=0 JALR was lowered to JMPR, dropping the return address
   entirely — the callee's `ret` jumped to garbage (same class as the
   RET-to-zero bug). Now lowered to CALLR (pushes return pc on the call stack).

2. Address-space bug: even with CALLR, glyph PCs are pixel-packed
   (row<<16)|col while function pointers hold RISC-V byte addresses — two
   different address spaces. JALR is now lowered to a table lookup through
   PTR_TABLE_BASE (filled by the loader via build_pointer_table()).

Fixture: a 3-entry proc table dispatched by a cooperative scheduler. Each
proc's entry is a function pointer (dynamic JALR per dispatch); second pass
re-marks one proc RUNNABLE to test state transitions. Exercises struct arrays,
function pointers in struct fields, indirect calls, state-machine transitions.

Ground truth three ways: native x86 binary (checksum=0xde, switches=4),
GPU SpatialRV64ICore, and transpiled glyph on GlyphCPUv2 — all bit-identical.
"""
import re
import shutil
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
    assemble_glyph_to_pixels,
    build_pointer_table,
    parse_elf,
    transpile_elf_to_glyph,
)
from tools.glyph_isa_v2 import GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.spatial_rv64i_cpu import SpatialRV64ICore  # noqa: E402

_GCC_BIN = "riscv64-unknown-elf-gcc"
_OBJCOPY_BIN = "riscv64-unknown-elf-objcopy"

pytestmark = pytest.mark.skipif(
    pytest.importorskip("shutil").which(_GCC_BIN) is None,
    reason="riscv64-unknown-elf-gcc not installed",
)

PROC_C = r"""
struct proc {
    long (*entry)(long);   /* function pointer: task entry */
    long arg;
    long state;            /* 0=UNUSED 1=RUNNABLE 2=RAN 3=ZOMBIE */
    long result;
};

struct proc g_procs[3];
long g_sched_checksum;
long g_switch_count;

__attribute__((noinline)) long task_a(long x) { return x * 2 + 1; }
__attribute__((noinline)) long task_b(long x) { return x + 0x100; }

__attribute__((noinline)) void proc_set(struct proc *p, long (*fn)(long), long arg) {
    p->entry = fn;
    p->arg = arg;
    p->state = 1;
    p->result = 0;
}

/* One scheduling pass: dispatch every RUNNABLE proc through its fn pointer
   (dynamic JALR), record state transition RUNNABLE->RAN. */
__attribute__((noinline)) void sched_pass(void) {
    long i;
    for (i = 0; i < 3; i = i + 1) {
        struct proc *p = &g_procs[i];
        if (p->state == 1) {
            p->result = p->entry(p->arg);   /* computed call */
            p->state = 2;
            g_sched_checksum ^= p->result;
            g_switch_count = g_switch_count + 1;
        }
    }
}

/* Body in a noinline function: _start must be pure inline asm because the
   GPU core enters with sp=0 and GCC's own C prologue would store to a
   negative (wrapped) address before our li sp takes effect. */
__attribute__((noinline)) void run_all(void) {
    g_sched_checksum = 0;
    g_switch_count = 0;
    proc_set(&g_procs[0], &task_a, 10);   /* 21 */
    proc_set(&g_procs[1], &task_b, 5);    /* 0x105 */
    proc_set(&g_procs[2], &task_a, 100);  /* 201 */
    sched_pass();
    /* second pass: only proc 1 becomes runnable again (re-yield) */
    g_procs[1].state = 1;
    g_procs[1].arg = 7;
    sched_pass();                          /* 0x107 */
}

void _start(void) {
    __asm__ volatile (
        "li sp, 0x800\n"
        "call run_all\n"
        "ecall\n"
    );
}
"""

# Symbol addresses fixed by the linker script section flags in this fixture.
SYM = {
    "g_switch_count": 0x300,
    "g_sched_checksum": 0x304,
    "g_procs": 0x400,
}
EXPECTED_CHECKSUM = 0xDE
EXPECTED_SWITCHES = 4


def test_proc_table_differential():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        c_path = tmp / "proc.c"
        elf_path = tmp / "proc.elf"
        bin_path = tmp / "proc.bin"
        c_path.write_text(PROC_C)

        res = subprocess.run(
            [_GCC_BIN, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-Wl,-Ttext=0x0",
             "-Wl,--section-start=.sbss=0x300",
             "-Wl,--section-start=.bss=0x400",
             str(c_path), "-o", str(elf_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, f"Compilation failed: {res.stderr}"

        # Sanity: the fixture MUST contain a real indirect jalr, or the test
        # loses its point (codegen changed, dispatch got devirtualized).
        objdump = subprocess.run(
            ["riscv64-unknown-elf-objdump", "-d", str(elf_path)],
            capture_output=True, text=True).stdout
        assert re.search(r"jalr\s+a[0-7]", objdump), (
            "no computed jalr in codegen; fixture no longer exercises the "
            "dynamic-dispatch path")

        res = subprocess.run(
            [_OBJCOPY_BIN, "-O", "binary", str(elf_path), str(bin_path)],
            capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        bin_data = bin_path.read_bytes()

        elf_bytes = elf_path.read_bytes()
        text_vaddr, text_bytes, symbols = parse_elf(elf_bytes)
        entry_addr = next(a for a, n in symbols.items() if n == "_start")

        # ---------- ground truth: GPU RV64 core ----------
        core = SpatialRV64ICore(4096)
        core.load_program(bin_data, entry_point=entry_addr)
        gpu_state = core.run_until_halt(max_cycles=100000, chunk_size=64)
        assert gpu_state["halted"] == 1, "GPU core failed to halt cleanly"

        gpu_checksum = core.read_mem_word(SYM["g_sched_checksum"])
        gpu_switches = core.read_mem_word(SYM["g_switch_count"])
        # procs[0].result (0x400 + 3*4 = 0x40C): task_a(10) = 21
        gpu_result0 = core.read_mem_word(0x40C)
        gpu_state1 = core.read_mem_word(0x418)  # procs[1].state -> 2 (RAN)

        # ---------- transpiled glyph ----------
        glyph_source = transpile_elf_to_glyph(
            elf_bytes, entry_symbol="_start",
            byte_to_word_mem=True)
        # The JALR must go through the pointer table + CALLR, not bare JMPR.
        assert "CALLR r30" in glyph_source, (
            "computed call not lowered through CALLR; address-space fix lost")

        pixels, coords = assemble_glyph_to_pixels(
            glyph_source, cols_instrs=64, min_rows=16)
        ptr_table = build_pointer_table(text_bytes, text_vaddr, coords)
        assert len(ptr_table) > 0, "pointer table empty"

        cpu = GlyphCPUv2(OpcodeMapV2(), cols_instrs=64)
        cpu.memory = [0] * 8192
        for word_idx, packed in ptr_table.items():
            cpu.memory[(PTR_TABLE_BASE >> 2) + word_idx] = packed
        cpu.pc = (0, 0)
        cpu.running = True
        for _ in range(20000):
            if not cpu.step(pixels):
                break
        assert not cpu.running, "GlyphCPUv2 failed to halt cleanly"

        glyph_checksum = cpu.memory[SYM["g_sched_checksum"] >> 2]
        glyph_switches = cpu.memory[SYM["g_switch_count"] >> 2]
        glyph_result0 = cpu.memory[0x40C >> 2]
        glyph_state1 = cpu.memory[0x418 >> 2]

        # ---------- differential + ground-truth assertions ----------
        assert gpu_checksum == EXPECTED_CHECKSUM, (
            f"GPU checksum 0x{gpu_checksum:x} != 0x{EXPECTED_CHECKSUM:x}")
        assert gpu_switches == EXPECTED_SWITCHES, (
            f"GPU switches {gpu_switches} != {EXPECTED_SWITCHES}")
        assert gpu_result0 == 21, f"GPU proc0 result {gpu_result0} != 21"
        assert gpu_state1 == 2, f"GPU proc1 state {gpu_state1} != 2 (RAN)"

        assert glyph_checksum == gpu_checksum, (
            f"Glyph checksum 0x{glyph_checksum:x} != GPU 0x{gpu_checksum:x}")
        assert glyph_switches == gpu_switches, (
            f"Glyph switches {glyph_switches} != GPU {gpu_switches}")
        assert glyph_result0 == gpu_result0, (
            f"Glyph proc0 result {glyph_result0} != GPU {gpu_result0}")
        assert glyph_state1 == gpu_state1, (
            f"Glyph proc1 state {glyph_state1} != GPU {gpu_state1}")

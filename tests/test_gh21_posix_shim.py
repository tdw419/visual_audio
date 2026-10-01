#!/usr/bin/env python3
"""tests/test_gh21_posix_shim.py — GH-21 POSIX Syscall Shim gate (RED).

Spec (roadmap row GH-21, systems/GLYPH_SELF_HOSTING_ROADMAP.md):

  userspace ABI adapter TILES mapping standard RV32/RV64 Linux ECALLs
  (sys_read=63, sys_write=64, sys_openat=56, sys_close=57, sys_exit=93,
  sys_brk=214) to in-image Glyph syscalls / Pixel-FS tiles; enables
  standard compiled C binaries to run unmodified.

  Gate: a compiled C binary calling write(1, msg, len) + exit(0) links
  against the shim, lowers to GlyphIR, executes with word-exact stdout
  at UART/mailbox; unrecognized ecall traps cleanly.

LANDED-ABI FACTS this gate is written against (GH-18 e3d3c13 + 07106ab,
GH-20 0d83f89 — no re-derivation, the receipts are the contract):

  - The engine marshals SYSCALL as: SYS_N <- a7 (r17), SYS_A0 <- a0 (r10),
    SYS_A1 <- a1 (r11); KSYS_PC trap; SYSRET restores the pre-trap file
    and delivers SYS_A0 into a0 (glyph_isa_v2.py:780-806). a2 is NOT
    marshaled — the shim ABI therefore passes write()'s length IMPLICITLY:
    the sys_write tile copies a FIXED 2-word stdout window (the gate
    binary's msg is 5 bytes + NUL = 2 words). The oracle pins the exact
    mutation; the on-die leg proves the same bytes land in the UART words.
  - The dispatcher masks sys_n UNSIGNED: idx = (n - 6) & 15. The POSIX
    numbers alias into the same 16-slot table:
      214 -> idx  0 -> word 1568     93 -> idx 7 -> word 1575
       56 -> idx  2 -> word 1570     63 -> idx 9 -> word 1577
       57 -> idx  3 -> word 1571     64 -> idx 10 -> word 1578
    The GH-21 bake mode ("posix") arms BOX2 and the vpn-6 PIX table page
    like admit; its table slots carry SHIM TILES admitted through
    autoatlas.admit_syscall ONLY (proof = admission, E_ATLAS_UNVERIFIED
    otherwise — same door as GH-20's SYS 10/11/12).
  - A C binary is transpiled by rv64i_to_glyph.transpile_elf_to_glyph
    (the GH-15 dual-path: byte-exact emission, IR StaticVerifier as the
    rejection gate). ECALL lowers to HALT today; the shim's loader
    rewrites the ECALL pattern (LDI r17 <nr> / HALT) into
    (LDI r17 <nr> / SYSCALL r10) AFTER the IR gate — the rewrite is
    1:1 instruction-count, so the verified module shape is preserved.
  - GNU mapping/linker symbols ($xrv32i2p1, __global_pointer$, ...) are
    NOTYPE filler that produce illegal glyph labels — the loader filters
    them before transpilation (receipt: first compile attempt died in
    raise_lines_to_ir with "illegal label line ':$xrv32i2p1'").
  - ABI version word 952: GH-21 bumps the low byte 0x18 -> 0x19
    (0x00020019) in the posix-mode image.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import (                              # noqa: E402 (RED)
    posix_shim_kernel_image,       # does not exist yet — RED at import
    GH18_TABLE_WORD,
    GH18_ABI_WORD,
)
from tools.glyph_isa_v2 import (                                 # noqa: E402
    SYS_A0_ADDR, SYS_A1_ADDR,
)

_GCC = "riscv64-unknown-elf-gcc"
OBJCOPY = "riscv64-unknown-elf-objcopy"

# ── GH-21 ABI constants ──────────────────────────────────────────────────
GH21_ABI_VERSION = 0x00020019            # low byte bumped 0x18 -> 0x19
KERNEL_OK = 0xCAFE0000 | 25              # posix-mode status tail id 25

# the POSIX numbers and the table slots the unsigned mask aliases them to
N_POSIX = {
    "openat": 56,    # idx 2
    "close": 57,     # idx 3
    "read": 63,      # idx 9
    "write": 64,     # idx 10
    "exit": 93,      # idx 7
    "brk": 214,      # idx 0
}


def _slot(sys_n: int) -> int:
    return GH18_TABLE_WORD + ((sys_n - 6) & 15)


# receipt words (GH-21's own; never written by the GH-18/20 kernels)
GH21_STDOUT_A = 718          # word-exact stdout channel (BOX1 word 0)
GH21_STDOUT_B = 719          # second stdout word
GH21_EXIT_CODE = 720         # sys_exit status code lands here


# ── the gate binary: standard C, no glyph anything ───────────────────────

FIXTURE_C = """\
extern int write(int fd, const void *buf, unsigned len);
extern void exit(int code);
static const char msg[6] = { 'H','E','L','L','O',0 };
void _start(void) {
    write(1, msg, 5);
    exit(0);
}
"""

SHIM_S = """\
    .text
    .globl write
write:
    li a7, 64
    ecall
    ret
    .globl exit
exit:
    li a7, 93
    ecall
    ret
"""

LINKER_JUNK = ("__global_pointer$", "__SDATA_BEGIN__", "__BSS_END__",
               "__bss_start", "__DATA_BEGIN__", "__DATA_END__")


def _require_toolchain() -> None:
    if shutil.which(_GCC) is None:
        pytest.skip("riscv64-unknown-elf-gcc not installed")


def _compile_elf(tmp: Path) -> bytes:
    """Standard freestanding compile of FIXTURE_C linked against the
    ECALL thunks (shim.S). No glyph awareness anywhere in this step."""
    src, elf = tmp / "g21.c", tmp / "g21.elf"
    asm = tmp / "shim.S"
    src.write_text(FIXTURE_C)
    asm.write_text(SHIM_S)
    subprocess.run(
        [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
         "-fno-builtin", "-ffreestanding", "-w", "-c", str(src),
         "-o", str(tmp / "g21.o")],
        check=True, capture_output=True, timeout=60)
    subprocess.run(
        [_GCC, "-march=rv32i", "-mabi=ilp32", "-nostdlib",
         "-Wl,-Ttext=0x0", "-Wl,--entry=_start", "-w",
         str(tmp / "g21.o"), str(asm), "-o", str(elf)],
        check=True, capture_output=True, timeout=60)
    return elf.read_bytes()


def _load_posix_program(elf_bytes: bytes) -> str:
    """The GH-21 loader: parse ELF -> filter linker junk symbols ->
    transpile (IR gate inside) -> rewrite ECALL lowering into SYSCALL ->
    seed the C runtime (sp init + .data/.rodata init).

    ECALL lowers to HALT (rv64i_to_glyph); the shim rewrites the exact
    pattern 'LDI r17 <nr>' + 'HALT' into 'LDI r17 <nr>' + 'SYSCALL r10'
    (1:1 instruction count — the IR-verified module shape is preserved;
    the rewrite happens AFTER the IR gate by design, mirroring how the
    GH-18 admit path rewrites HALT into the KJMP home after ingest)."""
    import rv64i_to_glyph as r2g

    base, text, symbols = r2g.parse_elf(elf_bytes)
    symbols = {a: n for a, n in symbols.items()
               if not n.startswith("$") and n not in LINKER_JUNK}
    lines = r2g.transpile_rv32i_to_glyph(
        text_bytes=text, symbols=symbols, base_addr=base,
        entry_symbol="_start", use_ir=True,
        cols_instrs=8).splitlines()
    # cols_instrs=8 MUST match the splice image's 8-column layout: the auto
    # stack address is computed from (code_rows + gap) * cols — at the
    # default 64 the loader bakes sp=4351 (vpn 16), but the posix kernel
    # identity-maps only vpns 0..7, so the task's first stack store faults
    # (receipt 2026-09-09, dbg_jc_stack3: fault_addr 0xFFFFFFFC at the
    # _start prologue's ST). At 8 cols the auto sp is 671 -> vpn 2, mapped.

    out: list[str] = []
    prev = ""
    for ln in lines:
        s = ln.split(";")[0].strip()
        if not s or s.startswith(":"):
            out.append(ln)          # labels/blank lines don't break the
            continue                # LDI-r17/HALT adjacency (receipt: the
                                    # transpiler interposes :pc_ labels)
        if s == "HALT" and prev.startswith("LDI r17 "):
            out.append("SYSCALL r10")
            prev = "SYSCALL r10"
            continue
        out.append(ln)
        prev = s

    # ── C runtime seed (probe-green receipts 2026-09-09) ──────────────
    # 1. sp init (dbg_gh21_green13-era probes / dbg_jc_stack3): the
    #    transpiler lowers RV32 sp to glyph r2 but only inits r31 (the
    #    CALL stack); the C prologue's first `addi sp, sp, -16` then
    #    computes r2 = 0 - 16 = 0xFFFFFFFC and the paged USER store
    #    faults. `LDI r2 1023` (vpn 3, identity-mapped) fixes it.
    # 2. .rodata/.data init (dbg_gh21_final): the loader transpiles .text
    #    only — msg ('HELLO') at byte 0x1048 (word 1042) was never seeded
    #    and the write tile LD'd zeros. Emit data-init stores from
    #    parse_elf_data_sections right after the sp init.
    init: list[str] = []
    for vaddr, blob in r2g.parse_elf_data_sections(elf_bytes):
        for wi in range(0, len(blob), 4):
            word = int.from_bytes(blob[wi:wi + 4].ljust(4, b"\0"), "little")
            w = (vaddr + wi) >> 2
            init.append(f"LDI r20 {word & 0xFFFF}")
            hi = (word >> 16) & 0xFFFF
            if hi:
                init.append(f"LDI r21 {hi}")
                init.append("LDI r22 16")
                init.append("SHL r21 r22")
                init.append("OR r20 r21")
            init.append(f"LDI r15 {w}")
            init.append("ST r15 r20")

    idx = next(i for i, ln in enumerate(out)
               if ln.split(";")[0].strip().startswith("LDI r31"))
    # keep :__entry (first line) + the r31 init; insert r2 + data-init
    # before the transpiler's leading `JMP :_start`.
    jmp_idx = next(i for i in range(idx + 1, len(out))
                   if out[i].startswith("JMP "))
    seeded = (out[:idx + 1]
              + ["LDI r2 1023            ; C data stack pointer (sp)"]
              + init
              + out[jmp_idx:])
    return "\n".join(seeded) + "\n"


# ── leg 1: ABI version word bumped in the posix-mode image ──────────────

def test_gh21_abi_version_word_bumped():
    """mem[952] == 0x00020019 at boot in the posix-mode image."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "gh21.npy"
        posix_shim_kernel_image(build_default_atlas(), out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=60000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        assert receipt["memory"][GH18_ABI_WORD] == GH21_ABI_VERSION
        assert receipt["status_word_value"] == KERNEL_OK


# ── leg 2: compiled C binary runs word-exact stdout + clean exit ────────

def test_gh21_c_binary_write_exit_word_exact():
    """write(1, msg, 5) + exit(0) from a REAL compiled RV32I binary:
    'HELLO' packed word-exactly into the stdout words, exit code 0 in
    GH21_EXIT_CODE, clean kernel tail (no fault, status KERNEL_OK)."""
    _require_toolchain()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = _compile_elf(tmp)
        program = _load_posix_program(elf)

        out = tmp / "gh21.npy"
        posix_shim_kernel_image(build_default_atlas(), out_path=out,
                                user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=120000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        # msg = 'HELLO\0' at some word-aligned address: word0 = 'HELL',
        # word1 = 'O\0\0\0' (little-endian). The tile copies both words
        # to the stdout channel.
        expect_a = (ord('H') | (ord('E') << 8) | (ord('L') << 16)
                    | (ord('L') << 24))
        expect_b = ord('O')
        assert mem[GH21_STDOUT_A] == expect_a, hex(mem[GH21_STDOUT_A])
        assert mem[GH21_STDOUT_B] == expect_b, hex(mem[GH21_STDOUT_B])
        assert mem[GH21_EXIT_CODE] == 0, "exit(0) code not delivered"
        assert receipt["status_word_value"] == KERNEL_OK


# ── leg 3: unrecognized ecall traps cleanly ─────────────────────────────

def test_gh21_unrecognized_ecall_traps_clean():
    """A POSIX number whose aliased slot is UNLIT (e.g. SYS 11 -> idx 5,
    no shim tile there) must hit the unknown-syscall handler: 'E' in
    BADSYS (730), clean SYSRET, kernel tails to KERNEL_OK."""
    _require_toolchain()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        unknown_c = FIXTURE_C.replace(
            "    write(1, msg, 5);\n",
            "    __asm__ volatile (\"li a7, 11\\n\\tecall\");\n")
        src, elf = tmp / "u.c", tmp / "u.elf"
        src.write_text(unknown_c)
        (tmp / "shim.S").write_text(SHIM_S)
        subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32", "-O1", "-nostdlib",
             "-fno-builtin", "-ffreestanding", "-w", "-c", str(src),
             "-o", str(tmp / "u.o")],
            check=True, capture_output=True, timeout=60)
        subprocess.run(
            [_GCC, "-march=rv32i", "-mabi=ilp32", "-nostdlib",
             "-Wl,-Ttext=0x0", "-Wl,--entry=_start", "-w",
             str(tmp / "u.o"), str(tmp / "shim.S"), "-o", str(elf)],
            check=True, capture_output=True, timeout=60)
        program = _load_posix_program(elf.read_bytes())

        out = tmp / "gh21u.npy"
        posix_shim_kernel_image(build_default_atlas(), out_path=out,
                                user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=120000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        mem = receipt["memory"]
        assert mem[730] == 69, hex(mem[730])      # 'E' — clean errno marker
        assert receipt["status_word_value"] == KERNEL_OK


# ── leg 4: shim tiles enter ONLY via admission (proof = admission) ──────

def test_gh21_shim_tiles_admitted_not_free(monkeypatch):
    """Monkeypatched escalate returns unverified -> every shim admission
    is rejected (E_ATLAS_UNVERIFIED) and the table stays untouched:
    baking the posix image with a fully-rejected pipeline leaves all six
    POSIX slots ZERO, and the C program's write dispatches to unknown."""
    from tools.glyph_gpt import autoatlas as aa
    from tools.glyph_gpt.escalate import EscalationResult

    def _fail(*a, **k):
        return EscalationResult(
            contract=a[0] if a else "", verified=False,
            attempts=k.get("max_attempts", 6),
            error="no candidate verified in N")
    monkeypatch.setattr(aa, "escalate", _fail)

    _require_toolchain()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        elf = _compile_elf(tmp)
        program = _load_posix_program(elf)

        out = tmp / "gh21r.npy"
        img = posix_shim_kernel_image(build_default_atlas(), out_path=out,
                                      user_program=program,
                                      admit_shims=True)
        runner = GlyphRunner(img, ram_words=16384)
        # the six POSIX slots are all zero in the image's pixel surface
        h, w, _ = runner.image.shape
        from tools.glyph_gpt.baker import GH18_TABLE_PIX_WORD
        for name, n in N_POSIX.items():
            pw = GH18_TABLE_PIX_WORD + ((_slot(n) - GH18_TABLE_WORD) & 0xFF)
            px = runner.image.reshape(-1, 3)[pw]
            assert tuple(px[:3]) == (0, 0, 0), (
                f"{name} slot pixel non-zero despite E_ATLAS_UNVERIFIED")
        receipt = runner.run(max_instructions=120000, trace=True)
        assert receipt["halted"] is True
        mem = receipt["memory"]
        assert mem[730] == 69, "unadmitted write must trap to unknown"
        assert receipt["status_word_value"] == KERNEL_OK


# ── leg 5: full-GH regression stays green (structural pin) ──────────────

def test_gh21_loader_preserves_ir_shape_and_flags():
    """Structural: the loader's ECALL rewrite is 1:1 (instruction count
    identical, no HALT-before-LDI-r17 rewritten) and the transpile path
    is the IR-gated one. Skips cleanly without the toolchain."""
    _require_toolchain()
    with tempfile.TemporaryDirectory() as d:
        elf = _compile_elf(Path(d))
        import rv64i_to_glyph as r2g
        base, text, symbols = r2g.parse_elf(elf)
        symbols = {a: n for a, n in symbols.items()
                   if not n.startswith("$") and n not in LINKER_JUNK}
        plain = r2g.transpile_rv32i_to_glyph(
            text_bytes=text, symbols=symbols, base_addr=base,
            entry_symbol="_start", use_ir=True)
        rewritten = _load_posix_program(elf)
        # The C-runtime seed (sp init + data init) is a deliberate,
        # probe-green ADDITION (receipts dbg_jc_stack3 / dbg_gh21_final):
        # the 1:1 pin applies to the ECALL REWRITE, so the seed size is
        # computed exactly from the loader's documented emission rules and
        # subtracted. Per data word the loader emits LDI r20 + LDI r15 +
        # ST (3), plus LDI r21/LDI r22 16/SHL/OR (4) when the high half
        # is nonzero; plus the one LDI r2 (sp) line. The r31 sp swap is
        # count-neutral (LDI r31 4351 -> LDI r31 671, same shape).
        n_seed = 1  # LDI r2 1023
        for _vaddr, blob in r2g.parse_elf_data_sections(elf):
            for wi in range(0, len(blob), 4):
                word = int.from_bytes(blob[wi:wi + 4].ljust(4, b"\0"),
                                      "little")
                n_seed += 3 + (4 if (word >> 16) & 0xFFFF else 0)

        def _instrs(txt: str) -> list[str]:
            return [ln.split(";")[0].strip() for ln in txt.splitlines()
                    if ln.strip() and not ln.strip().startswith(":")
                    and not ln.strip().startswith("#")]
        n_plain = len(_instrs(plain))
        n_rw = len(_instrs(rewritten))
        assert n_plain == n_rw - n_seed, (
            f"ECALL rewrite must be instruction-count neutral: "
            f"plain {n_plain} vs rewritten-minus-seed {n_rw - n_seed}")
        # the rewrite itself swaps HALT -> SYSCALL 1:1
        n_halt = sum(1 for s in _instrs(plain) if s == "HALT")
        n_sys = sum(1 for s in _instrs(rewritten) if s == "SYSCALL r10")
        assert n_sys == n_halt, f"{n_sys} SYSCALL vs {n_halt} HALT"
        assert "SYSCALL r10" in rewritten
        # every rewritten SYSCALL is preceded by LDI r17 (the shim
        # contract) — labels/comments interposed by the transpiler don't
        # break the adjacency
        lines = rewritten.splitlines()
        for i, ln in enumerate(lines):
            if ln.split(";")[0].strip() == "SYSCALL r10":
                j = i - 1
                while j >= 0:
                    s = lines[j].split(";")[0].strip()
                    if s and not s.startswith(":"):
                        break
                    j -= 1
                assert j >= 0 and lines[j].split(";")[0].strip().startswith(
                    "LDI r17 "), (
                    f"SYSCALL at line {i} not preceded by LDI r17")

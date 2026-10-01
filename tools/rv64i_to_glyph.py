#!/usr/bin/env python3
"""
rv64i_to_glyph.py — Transpiles RV32I / RV64I machine code to Geometry OS Glyph ISA v2 assembly.

Reads RISC-V ELF binaries (or raw instruction streams), decodes integer instructions
using tools.rv64i_decode, lowers them into Glyph ISA v2 assembly, and optionally
assembles them to fixed-width spatial pixel images via GlyphAssemblerV2.
"""

import argparse
import re
import struct
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple, Union

import numpy as np

# Ensure tools/ and repo root are on path
_TOOLS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TOOLS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import rv64i_decode
from rv64i_decode import (
    decode_instruction,
    OP_ADDI, OP_SLTI, OP_SLTIU, OP_XORI, OP_ORI, OP_ANDI, OP_SLLI, OP_SRLI, OP_SRAI,
    OP_BEQ, OP_BNE, OP_BLT, OP_BGE, OP_BLTU, OP_BGEU,
    OP_LB, OP_LH, OP_LW, OP_LBU, OP_LHU, OP_LD, OP_LWU,
    OP_SB, OP_SH, OP_SW, OP_SD,
    OP_ADD, OP_SUB, OP_SLL, OP_SLT, OP_SLTU, OP_XOR, OP_SRL, OP_SRA, OP_OR, OP_AND,
    OP_LUI, OP_AUIPC, OP_JAL, OP_JALR, OP_ECALL, OP_EBREAK, OP_MRET
)
from glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2, INSTR_WIDTH

# Rows of blank pixels reserved below the code image for the glyph hardware
# call stack (r31), which grows DOWNWARD from `stack_addr` one pixel per
# frame. 16 rows at the default 64-instr width is ~4K frames of headroom --
# far past any realistic call depth. Used by both the auto `stack_addr`
# computation in `transpile_rv32i_to_glyph` and the row padding in
# `assemble_glyph_to_pixels` so the two always agree.
_STACK_GAP_ROWS = 16
_AUTO_STACK_SENTINEL = "__AUTO_STACK_ADDR__"


def _auto_stack_addr(n_glyph_instr: int, cols_instrs: int) -> int:
    """Flat pixel index for r31's initial value: just inside a blank band
    `_STACK_GAP_ROWS` rows below the last code row, so the downward-growing
    call stack never reaches the instruction pixels and the outermost
    RET reads a zero pixel (-> clean halt)."""
    code_rows = -(-n_glyph_instr // cols_instrs)  # ceil
    return (code_rows + _STACK_GAP_ROWS) * cols_instrs * INSTR_WIDTH - 1


# Byte address of the dynamic-jump pointer table in the glyph data memory.
# The table is indexed by (PTR_TABLE_BASE + rv_byte_addr) >> 2 — i.e. entry i
# lives at glyph word (PTR_TABLE_BASE + 4*i) >> 2 — so it must be 4-aligned.
# 0x2000 (word 2048): above a kernel-sized writable segment -- xv6-nano's
# .data+.bss ends ~0x1d20 (the linker page-aligns .data away from the
# read-only .rodata) -- and still below the fixtures' sp (0x800 for the
# small ones, 0x4000 for the kernel/printf ones) so the RV stack never
# reaches it. cpu.memory must be >= word 2048 + (#jump targets); all
# fixtures use >= 8192 words. Loader fills it via build_pointer_table().
PTR_TABLE_BASE = 0x2000

# RULING_go5_ptr_table_vs_bss.md (2026-09-15): lane-local additive override.
# `ptr_table_base=None` on the transpile entry points means the canonical
# PTR_TABLE_BASE above -- every existing caller is byte-identical. A fixture
# whose .bss overlaps [0x2000, 0x2000+table_span) passes a higher base (the
# xv6-nano GO-5 harness uses 0x6000: above .bss end 0x3000, below
# BOX_MMIO_BASE 0x8000, inside the 16384-word twin RAM). Constraints per the
# ruling: 4-aligned; span [base, base+3584) < 0x8000 and inside cpu.memory;
# unreachable by the downward-growing RV stack.
GO5_XV6_PTR_TABLE_BASE = 0x6000


def build_pointer_table(
    text_bytes: bytes,
    base_addr: int,
    coords_map: Dict[str, Tuple[int, int]],
) -> Dict[int, int]:
    """
    Build the dynamic-jump pointer table mapping RISC-V byte addresses to
    pixel-packed glyph PCs.

    coords_map comes from assemble_glyph_to_pixels() (label -> (col, row)).
    Returns {rv_word_index: packed_glyph_pc} — the loader writes
    memory[(PTR_TABLE_BASE >> 2) + rv_word_index] = packed_glyph_pc for each
    entry before running the program.
    """
    table: Dict[int, int] = {}
    n_bytes = len(text_bytes)
    for offset in range(0, n_bytes, 4):
        pc = base_addr + offset
        label = f":pc_{pc:08x}"
        if label not in coords_map:
            continue
        col, row = coords_map[label]
        table[offset >> 2] = ((row & 0xFFFF) << 16) | (col & 0xFFFF)
    return table


def parse_elf(elf_bytes: bytes) -> Tuple[int, bytes, Dict[int, str]]:
    """
    Parse an ELF32 or ELF64 binary.

    Returns:
        (text_vaddr, text_bytes, symbol_map)
        symbol_map maps vaddr -> symbol_name.
    """
    if not elf_bytes.startswith(b"\x7fELF"):
        # Not an ELF; treat as raw binary with entry 0
        return 0, elf_bytes, {}

    is_32 = elf_bytes[4] == 1
    endian = "<" if elf_bytes[5] == 1 else ">"

    if is_32:
        (e_entry, e_phoff, e_shoff, e_flags, e_ehsize,
         e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx) = \
            struct.unpack_from(endian + "IIIIHHHHHH", elf_bytes, 24)
    else:
        (e_entry, e_phoff, e_shoff, e_flags, e_ehsize,
         e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx) = \
            struct.unpack_from(endian + "QQQIHHHHHH", elf_bytes, 24)

    sh_fmt = (endian + "IIIIIIIIII") if is_32 else (endian + "IIQQQQIIQQ")
    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        vals = struct.unpack_from(sh_fmt, elf_bytes, off)
        sections.append({
            "name_idx": vals[0], "type": vals[1], "flags": vals[2],
            "addr": vals[3], "offset": vals[4], "size": vals[5],
            "link": vals[6], "entsize": vals[9]
        })

    if e_shstrndx < len(sections):
        str_sec = sections[e_shstrndx]
        shstr = elf_bytes[str_sec["offset"]: str_sec["offset"] + str_sec["size"]]
    else:
        shstr = b""

    def get_sh_name(idx: int) -> str:
        end = shstr.find(b"\x00", idx)
        return shstr[idx:end].decode("ascii", errors="replace") if end != -1 else ""

    text_bytes = b""
    text_addr = 0
    symtab_sec = None
    strtab_sec = None

    for s in sections:
        s["name"] = get_sh_name(s["name_idx"])
        if s["name"] == ".text":
            text_bytes = elf_bytes[s["offset"]: s["offset"] + s["size"]]
            text_addr = s["addr"]
        elif s["type"] == 2:  # SHT_SYMTAB
            symtab_sec = s
        elif s["type"] == 3 and s["name"] == ".strtab":
            strtab_sec = s

    symbols: Dict[int, tuple] = {}
    if symtab_sec and strtab_sec:
        sym_bytes = elf_bytes[symtab_sec["offset"]: symtab_sec["offset"] + symtab_sec["size"]]
        str_bytes = elf_bytes[strtab_sec["offset"]: strtab_sec["offset"] + strtab_sec["size"]]
        sym_fmt = (endian + "IIIBBH") if is_32 else (endian + "IBBHQQ")
        entsize = symtab_sec["entsize"] or (16 if is_32 else 24)
        count = len(sym_bytes) // entsize
        for i in range(count):
            vals = struct.unpack_from(sym_fmt, sym_bytes, i * entsize)
            if is_32:
                st_name, st_value, st_size, st_info, st_other, st_shndx = vals
            else:
                st_name, st_info, st_other, st_shndx, st_value, st_size = vals
            end = str_bytes.find(b"\x00", st_name)
            name = str_bytes[st_name:end].decode("ascii", errors="replace")
            # ABS symbols (st_shndx == 0xfff1) are linker bookkeeping
            # (FILE names like "ccouDGLH.o", __global_pointer$, etc.).
            # FILE symbols must never enter the vaddr->name table: a FILE
            # symbol at 0x0 shadowed the real entry NOTYPE _start and the
            # IR verifier then rejected the ":__entry -> jmp <file>.o"
            # block as an unknown target. (Fixes R2.3 C-front-end
            # transpile rejection; -fno-ident did NOT suppress it since
            # GCC names the FILE symbol after the object file.)
            #
            # BK-11 regression RCA (2026-09-22, builder cron af3e62239ce2):
            # 6605f41a excluded ALL ABS symbols, but __global_pointer$ is
            # ABS and the GH-23 loader's DEFECT-9 fix seeds gp (x3) FROM
            # this table (tests/test_gh23_libc_runtime.py:388). With gp
            # gone, every gp-relative small-data access computes a negative
            # address (0xfffff80c-class OOB store faults) — the entire
            # tests/test_bk11_coreutils.py gate went RED (cat/echo/wc/head
            # 0/3 fixtures each; bisect 564a05af..HEAD pinned 6605f41a).
            # So: exclude FILE symbols by NAME/TYPE (they carry st_value 0
            # and would shadow _start), keep __global_pointer$ (the loader
            # captures it by exact name before its own junk filter).
            if not name:
                continue
            st_type = st_info & 0xF
            # FILE symbols (st_shndx == ABS, st_type == FILE): linker
            # bookkeeping that carries st_value 0 and would shadow the
            # real _start. Excluded by name/type, NOT by ABS-ness --
            # __global_pointer$ is also ABS and MUST stay (BK-11 RCA).
            if st_shndx == 0xFFF1 and st_type == 4:
                continue
            if st_shndx == 0:
                continue
            # Symbol-type precedence: real OBJECT/FUNC symbols must win
            # over linker-synthesized NOTYPE markers
            # (__SDATA_BEGIN__, __DATA_BEGIN__, __BSS_END__, ...) that
            # share the same st_value. Without this, g_init at 0x102c was
            # shadowed by __DATA_BEGIN__ (last-writer-wins) and callers
            # resolving globals by NAME failed. (File `p.c` and section
            # `$xrv32i2p1` symbols are NOTYPE too and were overwriting
            # real FUNC symbols at address 0.) First typed symbol wins;
            # NOTYPE only fills an address nothing typed claims.
            prev = symbols.get(st_value)
            # NOTYPE labels ($xrv32i2p1 mapping annotations, mapping
            # symbols in ARM terms) are filler too: as label text they
            # are illegal in the glyph IR (':$xrv32i2p1' rejected).
            if st_type == 0 and name.startswith("$"):
                continue
            # only OBJECT(1)/FUNC(2) are real symbols; NOTYPE(0),
            # SECTION(3) and FILE(4) are filler that must never shadow
            prev_real = prev is not None and prev[1] in (1, 2)
            if not prev_real and st_type in (1, 2):
                symbols[st_value] = (name, st_type)
            elif prev is None:
                symbols[st_value] = (name, st_type)
            # two different typed symbols at one address: keep first

    # strip the type channel; callers expect vaddr -> name
    named: Dict[int, str] = {vaddr: nm for vaddr, (nm, _t) in symbols.items()}
    return text_addr, text_bytes, named


def parse_elf_data_sections(elf_bytes: bytes) -> List[Tuple[int, bytes]]:
    """Return the initialized, loadable non-code sections as (vaddr, bytes).

    That is every SHF_ALLOC section with file-backed content (SHT_PROGBITS,
    not SHT_NOBITS) other than `.text`: `.data`, `.sdata`, `.rodata`,
    `.srodata`, etc.  `.bss`/`.sbss` are NOBITS -- already zero in a fresh
    memory -- and are skipped.

    `transpile_elf_to_glyph` only lifts `.text`; a caller running the result
    on `GlyphCPUv2` must seed `cpu.memory` with these bytes itself, the same
    way the GPU `SpatialRV64ICore.load_program` consumes the whole objcopy
    image.  Fixtures whose globals are all zero-initialized (bump_alloc,
    fifo, slab, kalloc, ...) never needed this; a fixture with a non-zero
    initializer (a string literal, `char buf[] = "..."`) does -- without it
    every such read returns 0.  Surfaced by the xv6 string.c differential.
    """
    if not elf_bytes.startswith(b"\x7fELF"):
        return []

    is_32 = elf_bytes[4] == 1
    endian = "<" if elf_bytes[5] == 1 else ">"
    if is_32:
        (_e_entry, _e_phoff, e_shoff, _e_flags, _e_ehsize,
         _e_phentsize, _e_phnum, e_shentsize, e_shnum, e_shstrndx) = \
            struct.unpack_from(endian + "IIIIHHHHHH", elf_bytes, 24)
    else:
        (_e_entry, _e_phoff, e_shoff, _e_flags, _e_ehsize,
         _e_phentsize, _e_phnum, e_shentsize, e_shnum, e_shstrndx) = \
            struct.unpack_from(endian + "QQQIHHHHHH", elf_bytes, 24)

    sh_fmt = (endian + "IIIIIIIIII") if is_32 else (endian + "IIQQQQIIQQ")
    raw = []
    for i in range(e_shnum):
        vals = struct.unpack_from(sh_fmt, elf_bytes, e_shoff + i * e_shentsize)
        raw.append({"name_idx": vals[0], "type": vals[1], "flags": vals[2],
                    "addr": vals[3], "offset": vals[4], "size": vals[5]})

    shstr = b""
    if e_shstrndx < len(raw):
        ss = raw[e_shstrndx]
        shstr = elf_bytes[ss["offset"]: ss["offset"] + ss["size"]]

    SHF_ALLOC = 0x2
    SHT_PROGBITS = 1
    out: List[Tuple[int, bytes]] = []
    for s in raw:
        end = shstr.find(b"\x00", s["name_idx"])
        name = shstr[s["name_idx"]:end].decode("ascii", "replace") if end != -1 else ""
        if name == ".text":
            continue
        if s["type"] != SHT_PROGBITS or not (s["flags"] & SHF_ALLOC):
            continue
        if s["size"] == 0:
            continue
        out.append((s["addr"], elf_bytes[s["offset"]: s["offset"] + s["size"]]))
    return out


def _emit_add_reg(lines: List[str], dst: str, rv_reg: int) -> None:
    """Emit `ADD {dst} r{rv_reg}`, UNLESS rv_reg is x0.

    x0 is RISC-V's hardwired-zero register and maps straight through to
    glyph r0 like every other register -- but glyph's CMP instruction writes
    its equality flag into r0 (JZ reads it from there), so r0 does NOT stay
    zero the way real x0 does. Adding it unconditionally reads whatever flag
    the most recent CMP left behind instead of true zero. Found via the G3
    round-robin scale test: `blez s6,label` (`bge zero,s6,label` under the
    hood) silently miscomputed once a preceding CMP in the same basic block
    left r0=1, because the transpiler read r0 as if it still meant "zero".
    Skipping the add when rv_reg==0 is both the fix and a no-op simplification
    (x + 0 == x either way).
    """
    if rv_reg != 0:
        lines.append(f"ADD {dst} r{rv_reg}")


def _emit_sub_reg(lines: List[str], dst: str, rv_reg: int) -> None:
    """Emit `SUB {dst} r{rv_reg}`, unless rv_reg is x0 -- same reasoning as
    _emit_add_reg: subtracting glyph r0 reads whatever CMP flag is currently
    there, not RV's true, always-zero x0."""
    if rv_reg != 0:
        lines.append(f"SUB {dst} r{rv_reg}")


class RVX31Record(NamedTuple):
    """Record representing an instruction referencing RV register x31 (t6)."""
    pc: int
    word: int
    op: Optional[str]
    roles: Tuple[str, ...]

    @property
    def role(self) -> str:
        return "/".join(self.roles)


class RVX31RefusalError(RuntimeError):
    """Raised when RV machine code references register x31 (t6).

    Glyph r31 is the hardware call stack pointer (CALL/RET/PUSH/POP all use it).
    Lowering RV x31 onto glyph r31 would silently corrupt the hardware call stack.
    """
    def __init__(self, message: str, violations: Optional[List[RVX31Record]] = None):
        super().__init__(message)
        self.violations: List[RVX31Record] = violations or []
        self.first_violation: Optional[RVX31Record] = self.violations[0] if self.violations else None


_OP_NAMES: Dict[int, str] = {
    getattr(rv64i_decode, k): k[3:].lower()
    for k in dir(rv64i_decode)
    if k.startswith("OP_") and k not in ("OP_INVALID", "OP_COUNT") and isinstance(getattr(rv64i_decode, k), int)
}


def _format_x31_refusal_message(violations: List[RVX31Record]) -> str:
    """Format refusal error message conforming to REFUSAL: RV x31 discipline."""
    first = violations[0]
    roles_str = "/".join(first.roles)
    op_str = f" ({first.op})" if first.op else ""
    return (
        f"REFUSAL: RV x31 (t6) referenced at pc 0x{first.pc:x}: "
        f"word 0x{first.word:08x}{op_str}, role {roles_str}. "
        f"Glyph r31 is the hardware call stack pointer; lowering x31 onto r31 would silently corrupt it."
    )


def scan_rv_x31_references(text_bytes: bytes, base_addr: int = 0) -> List[RVX31Record]:
    """Scan RV32I/RV64I text section machine code for references to x31 (t6).

    Walks 4 bytes at a time, uses decode_instruction(word), and reports every
    instruction where rd == 31, rs1 == 31, or rs2 == 31. decode_instruction
    returning None (data or unknown) is skipped.

    Args:
        text_bytes: Raw machine code bytes of the text section.
        base_addr: Base virtual address of the text section (default: 0).

    Returns:
        List of RVX31Record describing each x31 reference found.
    """
    violations: List[RVX31Record] = []
    n_bytes = len(text_bytes)
    for offset in range(0, (n_bytes // 4) * 4, 4):
        pc = base_addr + offset
        word = int.from_bytes(text_bytes[offset:offset + 4], "little")
        dec = decode_instruction(word)
        if dec is None:
            continue
        op, rd, rs1, rs2, imm, aux = dec
        roles = []
        if rd == 31:
            roles.append("dest")
        if rs1 == 31:
            roles.append("src1")
        if rs2 == 31:
            roles.append("src2")
        if roles:
            mnemonic = _OP_NAMES.get(op, f"op_{op}")
            violations.append(RVX31Record(pc=pc, word=word, op=mnemonic, roles=tuple(roles)))
    return violations


def transpile_rv32i_to_glyph(
    text_bytes: bytes,
    symbols: Optional[Dict[int, str]] = None,
    base_addr: int = 0,
    entry_symbol: Optional[str] = "_start",
    stack_addr: Optional[int] = None,
    byte_to_word_mem: bool = True,
    cols_instrs: int = 64,
    use_ir: bool = True,
    ptr_table_base: Optional[int] = None,
) -> str:
    """
    Transpile RV32I / RV64I text section machine code to Glyph ISA v2 assembly.

    Args:
        text_bytes: Raw machine code bytes of the text section.
        symbols: Map of address -> symbol name.
        base_addr: Starting address of the text section.
        entry_symbol: Symbol name for entry point, or None.
        stack_addr: Initial pixel index for the Glyph hardware call/ret stack
                    (r31), which grows downward. `None` (default) auto-sizes it
                    to `_STACK_GAP_ROWS` rows below the code image -- pass an
                    int only to override.
        byte_to_word_mem: If True, lowers byte addresses (e.g. 0x100) to 32-bit word
                          indices (0x40) when accessing Glyph CPU memory.
        cols_instrs: Instruction columns the image will be assembled at; only
                     used to place the auto stack, must match the value later
                     passed to `assemble_glyph_to_pixels`.
        use_ir: If True, runs the transpiled assembly through glyph_ir verification.

    Returns:
        String containing valid Glyph assembly text.

    Raises:
        RVX31RefusalError: If any instruction references register x31 (t6),
            as glyph r31 is reserved for the hardware call stack.
    """
    _tbl_base = (PTR_TABLE_BASE if ptr_table_base is None
                 else ptr_table_base)
    if _tbl_base % 4 != 0:
        raise ValueError(f"ptr_table_base must be 4-aligned, got 0x{_tbl_base:x}")
    violations = scan_rv_x31_references(text_bytes, base_addr=base_addr)
    if violations:
        raise RVX31RefusalError(_format_x31_refusal_message(violations), violations=violations)

    if symbols is None:
        symbols = {}

    # Identify all branch/jump targets
    targets: Set[int] = set()
    n_bytes = len(text_bytes)

    for offset in range(0, n_bytes, 4):
        pc = base_addr + offset
        word = int.from_bytes(text_bytes[offset:offset + 4], "little")
        dec = decode_instruction(word)
        if dec is None:
            continue
        op, rd, rs1, rs2, imm, aux = dec
        if op in (OP_JAL, OP_BEQ, OP_BNE, OP_BLT, OP_BGE, OP_BLTU, OP_BGEU):
            simm = imm if imm < 0x80000000 else imm - 0x100000000
            target_pc = pc + simm
            targets.add(target_pc)

    # Locate entry point
    entry_addr = base_addr
    if entry_symbol:
        for addr, name in symbols.items():
            if name == entry_symbol:
                entry_addr = addr
                break
    targets.add(entry_addr)

    start_label = symbols.get(entry_addr, f"pc_{entry_addr:08x}")
    if not start_label.startswith(":"):
        start_label = ":" + start_label

    stack_tok = _AUTO_STACK_SENTINEL if stack_addr is None else str(stack_addr)
    lines: List[str] = [
        "# Transpiled from RV32I/RV64I by rv64i_to_glyph.py",
        ":__entry",
        f"LDI r31 {stack_tok}            ; initialize hardware call stack pointer",
        f"JMP {start_label}",
        ""
    ]

    bne_counter = 0

    # Track whether x1 (ra) currently holds a call-preserved value ('call',
    # the normal case a plain `ret` expects) or was reloaded from data
    # ('data', the swtch.S-style resume case). Same instruction bytes
    # (jalr zero,0(ra)) mean opposite things depending on this: a
    # call-preserved ra is genuinely "return to whoever called this
    # function"; a data-loaded ra (e.g. `lw ra,0(a1)`) is a computed jump
    # that happens to be spelled `ret` and must go through the pointer
    # table, or it silently pops the wrong glyph call-stack frame (found by
    # tests/test_rv64i_to_glyph_switch.py — a naive RET here skipped the
    # entire coroutine body on the very first switch_to call).
    # Conservative reset to 'call' at every label/branch-target boundary:
    # only a straight-line reload with no intervening control flow since
    # function entry is trusted as 'data'.
    ra_source = 'call'

    for offset in range(0, n_bytes, 4):
        pc = base_addr + offset
        word = int.from_bytes(text_bytes[offset:offset + 4], "little")
        dec = decode_instruction(word)
        if dec is None:
            raise ValueError(f"Unsupported instruction at 0x{pc:08x}: 0x{word:08x}")

        op, rd, rs1, rs2, imm, aux = dec

        if pc in symbols or pc in targets:
            ra_source = 'call'

        # Emit label if target or symbol
        if pc in symbols:
            sname = symbols[pc]
            lines.append(f":{sname}")
        # Label EVERY pc: dynamic jumps (function pointers) can target any
        # instruction; the pointer table is built from these labels
        # post-assembly via build_pointer_table().
        lines.append(f":pc_{pc:08x}")

        if rd == 1 and op not in (OP_JAL, OP_JALR):
            # An ordinary epilogue ALSO writes ra via a load -- `lw ra,N(sp)`,
            # restoring THIS function's own saved return address from its own
            # stack frame -- and is just as RET-safe as never having touched
            # ra at all. The swtch-style case loads ra from an arbitrary
            # pointer (`lw ra,0(a1)`), not sp. rs1==2 (sp) is the
            # distinguishing signal; anything else is a genuine data load.
            ra_source = 'call' if rs1 == 2 else 'data'
        elif rd == 1 and op in (OP_JAL, OP_JALR):
            ra_source = 'call'

        # LUI
        if op == OP_LUI:
            if rd != 0:
                lines.append(f"LDI r{rd} 0x{imm & 0xFFFFFFFF:x}")

        # AUIPC (G11): rd = pc + (imm20 << 12). The transpiler walks .text at
        # fixed linked addresses, so `pc` is known statically -- this is a
        # pure compile-time constant, no runtime PC read needed. The decoder
        # already returns imm as `instr & 0xFFFFF000` (the shifted high bits),
        # and (pc + imm) & 0xFFFFFFFF equals (pc + sign_extend(imm)) mod 2^32
        # regardless of imm's top bit. GCC emits this for -mcmodel=medany
        # symbol material (`auipc rd,%pcrel_hi(sym); addi rd,rd,%pcrel_lo`);
        # the following ADDI/LW already lower and operate on the right value.
        elif op == OP_AUIPC:
            if rd != 0:
                lines.append(f"LDI r{rd} 0x{(pc + imm) & 0xFFFFFFFF:x}")

        # ADDI
        elif op == OP_ADDI:
            if rd != 0:
                if rs1 == 0:
                    lines.append(f"LDI r{rd} 0x{imm & 0xFFFFFFFF:x}")
                elif imm == 0:
                    if rd != rs1:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r{rs1}")
                elif rd == rs1:
                    # DEFECT-31b (2026-09-25, af3e tick): this branch used
                    # r29 as its imm temp unconditionally. When rd==rs1 is
                    # x29 (t4) -- gcc allocates it freely -- `LDI r29 imm`
                    # clobbered the source before `ADD r29, r29` ran.
                    # Guard: when r29 aliases rd, push it and use r26 as
                    # the temp (DEFECT-30/31 scratch-discipline fix).
                    if rd == 29:
                        lines.append("PUSH r26")
                        lines.append(f"LDI r26 0x{imm & 0xFFFFFFFF:x}")
                        lines.append(f"ADD r{rd} r26")
                        lines.append("POP r26")
                    else:
                        lines.append(f"LDI r29 0x{imm & 0xFFFFFFFF:x}")
                        lines.append(f"ADD r{rd} r29")
                else:
                    lines.append(f"LDI r{rd} 0x{imm & 0xFFFFFFFF:x}")
                    lines.append(f"ADD r{rd} r{rs1}")

        # ADD
        elif op == OP_ADD:
            if rd != 0:
                if rs1 == 0 and rs2 == 0:
                    lines.append(f"LDI r{rd} 0")
                elif rs1 == 0:
                    if rd != rs2:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r{rs2}")
                elif rs2 == 0:
                    if rd != rs1:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r{rs1}")
                elif rd == rs1:
                    lines.append(f"ADD r{rd} r{rs2}")
                elif rd == rs2:
                    lines.append(f"ADD r{rd} r{rs1}")
                else:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                    lines.append(f"ADD r{rd} r{rs2}")

        # SUB
        elif op == OP_SUB:
            if rd != 0:
                if rs2 == 0:
                    if rd != rs1:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r{rs1}")
                elif rs1 == 0:
                    if rd == rs2:
                        # `neg rd, rd` (sub rd, x0, rd): zeroing rd first would
                        # also zero the subtrahend -> always 0. Route the source
                        # through scratch before clobbering rd. GCC emits this
                        # constantly; nothing before bio.c had an in-place
                        # negate whose value reached an observable.
                        lines.append("LDI r29 0")
                        lines.append(f"SUB r29 r{rs2}")
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r29")
                    else:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"SUB r{rd} r{rs2}")
                elif rd == rs1:
                    lines.append(f"SUB r{rd} r{rs2}")
                elif rd == rs2:
                    lines.append(f"LDI r29 0")
                    lines.append(f"ADD r29 r{rs1}")
                    lines.append(f"SUB r29 r{rd}")
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r29")
                else:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                    lines.append(f"SUB r{rd} r{rs2}")

        # ANDI
        elif op == OP_ANDI:
            if rd != 0:
                if rs1 == 0:
                    lines.append(f"LDI r{rd} 0")
                elif rd == rs1:
                    lines.append(f"LDI r29 0x{imm & 0xFFFFFFFF:x}")
                    lines.append(f"AND r{rd} r29")
                else:
                    lines.append(f"LDI r{rd} 0x{imm & 0xFFFFFFFF:x}")
                    lines.append(f"AND r{rd} r{rs1}")

        # ORI
        elif op == OP_ORI:
            if rd != 0:
                if rs1 == 0:
                    lines.append(f"LDI r{rd} 0x{imm & 0xFFFFFFFF:x}")
                elif rd == rs1:
                    lines.append(f"LDI r29 0x{imm & 0xFFFFFFFF:x}")
                    lines.append(f"OR r{rd} r29")
                else:
                    lines.append(f"LDI r{rd} 0x{imm & 0xFFFFFFFF:x}")
                    lines.append(f"OR r{rd} r{rs1}")

        # XORI
        elif op == OP_XORI:
            if rd != 0:
                if rs1 == 0:
                    lines.append(f"LDI r{rd} 0x{imm & 0xFFFFFFFF:x}")
                elif rd == rs1:
                    lines.append(f"LDI r29 0x{imm & 0xFFFFFFFF:x}")
                    lines.append(f"XOR r{rd} r29")
                else:
                    lines.append(f"LDI r{rd} 0x{imm & 0xFFFFFFFF:x}")
                    lines.append(f"XOR r{rd} r{rs1}")

        # AND
        elif op == OP_AND:
            if rd != 0:
                if rs1 == 0 or rs2 == 0:
                    lines.append(f"LDI r{rd} 0")
                elif rd == rs1:
                    lines.append(f"AND r{rd} r{rs2}")
                elif rd == rs2:
                    lines.append(f"AND r{rd} r{rs1}")
                else:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                    lines.append(f"AND r{rd} r{rs2}")

        # OR
        elif op == OP_OR:
            if rd != 0:
                if rs1 == 0:
                    if rd != rs2:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r{rs2}")
                elif rs2 == 0:
                    if rd != rs1:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r{rs1}")
                elif rd == rs1:
                    lines.append(f"OR r{rd} r{rs2}")
                elif rd == rs2:
                    lines.append(f"OR r{rd} r{rs1}")
                else:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                    lines.append(f"OR r{rd} r{rs2}")

        # XOR
        elif op == OP_XOR:
            if rd != 0:
                if rs1 == 0:
                    if rd != rs2:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r{rs2}")
                elif rs2 == 0:
                    if rd != rs1:
                        lines.append(f"LDI r{rd} 0")
                        lines.append(f"ADD r{rd} r{rs1}")
                elif rd == rs1:
                    lines.append(f"XOR r{rd} r{rs2}")
                elif rd == rs2:
                    lines.append(f"XOR r{rd} r{rs1}")
                else:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                    lines.append(f"XOR r{rd} r{rs2}")

        # SLLI
        elif op == OP_SLLI:
            if rd != 0:
                shamt = imm & 31
                lines.append(f"LDI r29 {shamt}")
                if rd == rs1:
                    lines.append(f"SHL r{rd} r29")
                else:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                    lines.append(f"SHL r{rd} r29")

        # SRLI / SRAI
        elif op in (OP_SRLI, OP_SRAI):
            if rd != 0:
                shamt = imm & 31
                if rd != rs1:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                if op == OP_SRLI:
                    lines.append(f"LDI r29 {shamt}")
                    lines.append(f"SHR r{rd} r29")
                else:
                    # Arithmetic right shift. Glyph `SHR` is LOGICAL only, so
                    # sign-extend branchlessly (no NOT opcode):
                    #   sar(x,n) = ((x ^ 0x80000000) >>u n) - (0x80000000 >>u n)
                    # (x>=0: x^msb has bit31 set, the two msb>>n terms cancel
                    #  -> x>>n. x<0: the subtraction borrows the high n bits to
                    #  1s.) shamt 0 is fine: reduces to x^msb - msb == x.
                    lines.append("LDI r29 0x80000000")
                    lines.append(f"XOR r{rd} r29")
                    lines.append(f"LDI r28 {shamt}")
                    lines.append(f"SHR r{rd} r28")
                    lines.append("LDI r27 0x80000000")
                    lines.append(f"LDI r28 {shamt}")
                    lines.append("SHR r27 r28")
                    lines.append(f"SUB r{rd} r27")

        # SLL
        elif op == OP_SLL:
            if rd != 0:
                if rd == rs1:
                    lines.append(f"SHL r{rd} r{rs2}")
                else:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                    lines.append(f"SHL r{rd} r{rs2}")

        # SRL / SRA
        elif op in (OP_SRL, OP_SRA):
            if rd != 0:
                # DEFECT-30 (2026-09-15, builder cron af3e62239ce2, pins 5/6 in
                # worktree go5-ptr-base output/go5_pin5_curproc_watch_result.txt
                # + go5_pin6_s10_watch_result.txt): r26 is ALSO the glyph name
                # of RV32 x26 (s10, CALLEE-SAVED) under the identity register
                # map -- the same defect class as DEFECT-11 (SB, fixed above
                # with PUSH/POP). Measured: xv6-nano s11's scheduler keeps its
                # curproc base in s10 (lui s10,0x2 @0xb60); the reap branch
                # `sra a5,a4,s1` @0xc38 lowers with `LDI r26 31; AND r26 r9`
                # and destroys s10 (measured r26 0x2000 -> 0x1f -> 0x2 at
                # steps 5038-5039), so every later `sw s0,-324(s10)` stores to
                # 0xFFFFFEBE and curproc stays stale -> post-reap dispatches
                # run a zombie's context (GO-5 s11 g_clen 3 != 7). Fix: same
                # PUSH/POP guard as the SB RMW (safe: this sequence never
                # spans a CALL/RET boundary, and r31/x31 is fenced).
                lines.append("PUSH r26")
                # Shift count into scratch first (rs2 may alias rd).
                lines.append("LDI r26 31")
                lines.append(f"AND r26 r{rs2}")
                if rd != rs1:
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r{rs1}")
                if op == OP_SRL:
                    lines.append(f"SHR r{rd} r26")
                else:
                    # Arithmetic: same branchless sign-extend as SRAI, with
                    # the run-time count in r26.
                    lines.append("LDI r29 0x80000000")
                    lines.append(f"XOR r{rd} r29")
                    lines.append(f"SHR r{rd} r26")
                    lines.append("LDI r27 0x80000000")
                    lines.append("SHR r27 r26")
                    lines.append(f"SUB r{rd} r27")
                lines.append("POP r26")          # DEFECT-30: restore s10

        # SLT / SLTI
        # DEFECT 10 (2026-09-10, cron session; receipt
        # output/dbg_gh23_sltalias + probe_gh23_fullcmp): the rd==rs1
        # aliasing case — GCC's two-sided compare `slt a5,a5,a4` after
        # `slt a0,a4,a5` in (x>y)-(x<y) — zeroed rd (killing rs1=x) before
        # the ADD could read it, so the pattern computed (0+0-rs2)>>31 =
        # sign(0-rs2) instead of sign(rs1-rs2). The comparator returned 0
        # for every x>y pair, qsort never swapped, the GH-23 gate printed
        # UNSORTED data ('n=40,30' where 'n=10,30' was expected). Fix: route
        # rs1 through scratch r28 first, exactly the SLTU fix (see below).
        elif op in (OP_SLT, OP_SLTI):
            if rd != 0:
                if op == OP_SLT and rd == rs1:
                    # rd==rs1 aliasing: consume rs1 BEFORE clobbering rd.
                    lines.append("LDI r28 0")
                    _emit_add_reg(lines, "r28", rs1)
                    lines.append("LDI r29 31")
                    _emit_sub_reg(lines, "r28", rs2)
                    lines.append(f"SHR r28 r29")
                    lines.append(f"LDI r{rd} 0")
                    lines.append(f"ADD r{rd} r28")
                else:
                    lines.append(f"LDI r{rd} 0")
                    _emit_add_reg(lines, f"r{rd}", rs1)
                    if op == OP_SLTI:
                        lines.append(f"LDI r29 0x{imm & 0xFFFFFFFF:x}")
                        lines.append(f"SUB r{rd} r29")
                    else:
                        _emit_sub_reg(lines, f"r{rd}", rs2)
                    lines.append("LDI r29 31")
                    lines.append(f"SHR r{rd} r29")

        # SLTIU (G11): immediate form of SLTU. Same XOR-sign-bit-then-signed-
        # subtract trick, with the subtrahend a constant (sext(imm12), which
        # `imm & 0xFFFFFFFF` already is). rs1 is consumed into r28 before
        # r{rd} is written, so `rd == rs1` (GCC's `seqz rd,rd` = `sltiu
        # rd,rd,1`) is safe -- same aliasing fix as SLTU.
        elif op == OP_SLTIU:
            if rd != 0:
                lines.append("LDI r29 0x80000000")
                lines.append("LDI r28 0")
                _emit_add_reg(lines, "r28", rs1)
                lines.append("XOR r28 r29")
                lines.append(f"LDI r30 0x{imm & 0xFFFFFFFF:x}")
                lines.append("XOR r30 r29")
                lines.append("SUB r28 r30")
                lines.append("LDI r29 31")
                lines.append("SHR r28 r29")
                lines.append(f"LDI r{rd} 0")
                lines.append(f"ADD r{rd} r28")

        # SLTU (unsigned set-less-than; first hit by round-robin's
        # `!(mask & (1<<i))` -> GCC's `snez`/`seqz` pseudo-ops, which are
        # `sltu rd,zero,rs`/`sltu rd,rs,1`). Same branchless
        # sign-bit-of-difference trick as SLT, but unsigned comparison needs
        # both operands XORed with the sign bit first: that maps the
        # unsigned range [0,2^32) onto the signed range with the same
        # relative order, so a SIGNED subtract-and-check-sign-bit becomes
        # correct for the UNSIGNED comparison.
        # rd==rs1 or rd==rs2 aliasing: `snez rd,rd` (GCC's `sltu rd,zero,rd`,
        # exactly `!(mask & bit)`'s idiom) has rd==rs2. Writing `LDI r{rd} 0`
        # before rs2 is fully read -- which the first version of this did --
        # zeroes the source it still needed, corrupting every result where
        # rd aliases either operand. Found live: a round-robin scheduler's
        # "is this task done?" check spuriously fired on every yield instead
        # of only on completion, because this exact aliasing pattern was
        # the check's own boolean-normalize step. Fix: fully consume BOTH
        # operands into scratch (r28, r30) before ever writing r{rd}.
        elif op == OP_SLTU:
            if rd != 0:
                lines.append("LDI r29 0x80000000")
                lines.append("LDI r28 0")
                _emit_add_reg(lines, "r28", rs1)
                lines.append("XOR r28 r29")
                lines.append("LDI r30 0")
                _emit_add_reg(lines, "r30", rs2)
                lines.append("XOR r30 r29")
                lines.append("SUB r28 r30")
                lines.append("LDI r29 31")
                lines.append("SHR r28 r29")
                lines.append(f"LDI r{rd} 0")
                lines.append(f"ADD r{rd} r28")

        # LW
        elif op in (OP_LW, OP_LD):
            if rd != 0:
                if rs1 == 0:
                    lines.append(f"LDI r30 0x{imm & 0xFFFFFFFF:x}")
                else:
                    lines.append(f"LDI r30 0x{imm & 0xFFFFFFFF:x}")
                    lines.append(f"ADD r30 r{rs1}")
                if byte_to_word_mem:
                    lines.append("LDI r29 2")
                    lines.append("SHR r30 r29")
                lines.append(f"LD r{rd} r30")

        # SW
        elif op in (OP_SW, OP_SD):
            # DEFECT-31 (2026-09-25, af3e tick; repro
            # .builder_queue/DEFECT_31_sw_r30_alias.md): this lowering
            # used r30 as the address temp unconditionally. When the RV
            # base register rs1 IS x30 (t5) -- gcc allocates it freely
            # (`li t5,0xC00; sw t1,0(t5)`) -- the `LDI r30 <imm>`
            # clobbered the base before `ADD r30 r30` read it, so the
            # store targeted `imm` (or a chain of imms) instead of
            # base+imm. Measured: bare `sw to 0xC00` program stored
            # nothing (words 768+ stayed 0) while a non-aliased control
            # stored fine; the vol2 grep/tr/cut/sort gate legs were RED
            # on exactly this shape. FIX: when rs1 aliases r30 (or r29,
            # the shift temp), take the address temp from a saved set --
            # push r30, compute the address in r28 (with r26 as the
            # shift temp), pop r30. Mirrors the DEFECT-30 LBU fix.
            _a = "r30"
            _s = "r29"
            _pushed = None
            if rs1 == 30:
                _pushed = 30
                lines.append("PUSH r30")
                _a = "r28"
                _s = "r26"
            elif rs1 == 29:
                _a = "r28"
                _s = "r26"
            if rs1 == 0:
                lines.append(f"LDI {_a} 0x{imm & 0xFFFFFFFF:x}")
            else:
                lines.append(f"LDI {_a} 0x{imm & 0xFFFFFFFF:x}")
                lines.append(f"ADD {_a} r{rs1}")
            if byte_to_word_mem:
                lines.append(f"LDI {_s} 2")
                lines.append(f"SHR {_a} {_s}")
            if rs2 == 0:
                lines.append("LDI r28 0")
                lines.append(f"ST {_a} r28")
            else:
                lines.append(f"ST {_a} r{rs2}")
            if _pushed is not None:
                lines.append("POP r30")

        # LBU (sub-word load, G6): Glyph memory is word-indexed
        # (byte_to_word_mem), so a byte load needs the address split into
        # word_addr (addr>>2) + lane (addr&3), the full word loaded, then
        # shifted right by lane*8 bits and masked to 8 bits. Signed LB is
        # not implemented (not yet needed by any fixture) -- would need a
        # sign-extend-from-bit-7 step after the mask.
        elif op == OP_LBU:
            if rd != 0:
                # DEFECT-16c (2026-09-12, BK-11 cron session; receipts
                # output/bk11_gate_run1_red.txt + dbg_bk11_probe49/51):
                # this byte-extract sequence uses r28/r29/r30 as scratch
                # EVERY iteration -- and those are the glyph names of RV
                # x28/x29/x30 (t3/t4/t5) under the identity register map.
                # GCC hoists loop-invariant compare constants into exactly
                # these t-regs (wc: `li t3,32` = the space char, hoisted
                # out of the byte loop). The LBU scratch trashed t3 every
                # iteration (trace: r28 0x20 -> lane-shift 0x08), so the
                # next `bne a4,t3` compared against garbage and wc missed
                # the space word boundary (words 3->2). Same DEFECT-11/16
                # class as the SB/SH and branch fixes. DEFECT-30 below
                # replaces the original push-all/pop-minus-rd shape.
                # DEFECT-30 (2026-09-25, af3e tick; receipt
                # .builder_queue/DEFECT_30_lbu_scratch_stack.md): the
                # original shape pushed (28,29,30) but popped only
                # (28,29,30)-rd, so rd==r28/r29 leaked one engine-stack
                # word per executed LBU; and when rd==r29 the mask LDI
                # overwrote rd's extracted byte (every byte read 0xff).
                # FIX: push only what will be popped, and take the
                # mask/lane scratch from the pushed set so no scratch
                # aliases rd after `LD rd` is live.
                scratch = [r for r in (28, 29, 30) if r != rd]
                if len(scratch) == 2:
                    scratch.append(26)          # r26: DEFECT-11-proven
                                                # safe extra save/restore
                                                # slot for this lowering
                # Ensure _addr does not alias rs1 so LDI imm cannot clobber rs1
                avail = [r for r in scratch if r != rs1]
                _addr = avail[0]
                rem = [r for r in scratch if r != _addr]
                _lane, _mask = rem[0], rem[1]
                for _r in scratch:
                    lines.append(f"PUSH r{_r}")
                lines.append(f"LDI r{_addr} 0x{imm & 0xFFFFFFFF:x}")
                _emit_add_reg(lines, f"r{_addr}", rs1)
                # lane*8 = shift amount, computed from the BYTE address
                # before it's converted to a word index below.
                lines.append(f"LDI r{_lane} 3")
                lines.append(f"AND r{_lane} r{_addr}")
                lines.append(f"LDI r{_mask} 3")
                lines.append(f"SHL r{_lane} r{_mask}")
                if byte_to_word_mem:
                    lines.append(f"LDI r{_mask} 2")
                    lines.append(f"SHR r{_addr} r{_mask}")
                lines.append(f"LD r{rd} r{_addr}")
                lines.append(f"SHR r{rd} r{_lane}")
                lines.append(f"LDI r{_mask} 0xff")
                lines.append(f"AND r{rd} r{_mask}")
                for _r in reversed(scratch):
                    lines.append(f"POP r{_r}")

        # SB (sub-word store, G6): read-modify-write the containing word.
        # Clearing exactly the target byte lane without a NOT opcode uses
        # the identity (x | m) ^ m == x & ~m (verified: bit set in m ->
        # (x|1)^1=0; bit clear in m -> (x|0)^0=x -- matches x&~m either way).
        # 5 scratch registers (r26-r30) are simultaneously live across this
        # sequence -- more than any other lowering here -- because RMW
        # needs word_addr, shift, cur_word, the clear-mask, and the
        # insert-value all worked out before the final combine+store.
        #
        # DEFECT 11 (2026-09-10, cron session; receipts
        # output/dbg_gh23_cron1050_state.txt + probes 1107..1136): r26/r27
        # are ALSO the glyph names of RV32 x26/x27 (s10/s11, CALLEE-SAVED)
        # under the transpiler's identity register map -- and this RMW
        # sequence clobbered them WITHOUT save/restore. Every leaf function
        # containing an SB corrupted its CALLER's live s10/s11. Symptom in
        # the GH-23 gate: printf keeps its fmt-spec compare constants in
        # s10=115('s')/s11=99('c') across out_ch calls; out_ch's
        # `out_buf[out_n++] = c` lowers to SB whose RMW trashed them, so
        # the '%c'/'%s' compares never matched and printf fell through to
        # the literal-char branch, printing 'c'/'s' instead of the
        # formatted value ('!c10,20' where 'n=10,20!C' was expected).
        # FIX: wrap the RMW in PUSH/POP of r26/r27 on the engine's
        # hardware r31 stack (the same mechanism CALL/RET use; safe here
        # because the SB sequence never spans a CALL/RET boundary).
        elif op == OP_SB:
            if rs1 == 30:
                # DEFECT-31c minimal fix (2026-09-25, af3e tick; the rejected
                # full r26..r30 save/restore rewrite is preserved verbatim in
                # .builder_queue/DEFECT31c_dirty_rewrite_snapshot.diff -- it
                # was measured as a net regression: xv6 gate 4F/9P with
                # jalr-to-mid-text faults at word 1887/1953, trace
                # .builder_queue/dbg_d31c_trace_diff_af3e.py showed ZERO
                # stores to the corrupted target words, i.e. the failure is
                # control-flow in the rewritten lowering, not memory).
                # This is the same aliasing class as DEFECT-31 (SW): the
                # HEAD body's `LDI r30 imm` clobbers the base when rs1 IS
                # x30 (t5). Measured RED on HEAD:
                # dbg_d30_iso_sb_base_va_af3e.py -> t5base mem[768]=0x0
                # (nothing stored). FIX: compute the address ONCE in r28
                # (never re-derive it by re-reading the base), keep the
                # base live in r30 until the final ST's operands are done,
                # and restore r26/r27/r30 around the sequence. Every
                # non-aliased SB site emits BYTE-IDENTICAL text to HEAD
                # (the xv6 gate's SB bases are a1/a3/a4/a5/sp -- no x30).
                lines.append("PUSH r26")
                lines.append("PUSH r27")
                lines.append("PUSH r30")
                lines.append(f"LDI r28 0x{imm & 0xFFFFFFFF:x}")
                _emit_add_reg(lines, "r28", rs1)      # r28 = addr; base intact
                lines.append("LDI r27 3")
                lines.append("AND r27 r28")           # r27 = lane (addr&3)
                lines.append("LDI r29 3")
                lines.append("SHL r27 r29")           # r27 = shift
                lines.append("LDI r29 2")
                lines.append("SHR r28 r29")           # r28 = word_addr
                lines.append("LD r29 r28")            # r29 = cur_word
                lines.append("LDI r26 0")
                _emit_add_reg(lines, "r26", rs2)      # r26 = value (reads rs2
                                                      #  before r30 is masked)
                lines.append("LDI r30 0xff")
                lines.append("AND r26 r30")           # value &= 0xff
                lines.append("SHL r26 r27")           # value <<= shift
                lines.append("SHL r30 r27")           # r30 = 0xff<<shift
                lines.append("OR r29 r30")
                lines.append("XOR r29 r30")           # lane cleared
                lines.append("OR r29 r26")            # insert value
                lines.append("ST r28 r29")
                lines.append("POP r30")
                lines.append("POP r27")
                lines.append("POP r26")
            else:
                lines.append("PUSH r26")
                lines.append("PUSH r27")
                lines.append(f"LDI r30 0x{imm & 0xFFFFFFFF:x}")
                _emit_add_reg(lines, "r30", rs1)
                lines.append("LDI r28 3")
                lines.append("AND r28 r30")
                lines.append("LDI r29 3")
                lines.append("SHL r28 r29")            # r28 = shift, kept below
                lines.append(f"LDI r30 0x{imm & 0xFFFFFFFF:x}")
                _emit_add_reg(lines, "r30", rs1)
                if byte_to_word_mem:
                    lines.append("LDI r29 2")
                    lines.append("SHR r30 r29")          # r30 = word_addr, kept below
                lines.append("LD r29 r30")                # r29 = cur_word
                lines.append("LDI r27 0xff")
                lines.append("SHL r27 r28")                # r27 = mask (0xFF<<shift)
                lines.append("OR r29 r27")
                lines.append("XOR r29 r27")                 # r29 = cur_word, lane cleared
                lines.append("LDI r26 0")
                _emit_add_reg(lines, "r26", rs2)
                lines.append("LDI r27 0xff")
                lines.append("AND r26 r27")
                lines.append("SHL r26 r28")                 # r26 = (rs2&0xff)<<shift
                lines.append("OR r29 r26")
                lines.append("ST r30 r29")
                lines.append("POP r27")                     # DEFECT 11: restore
                lines.append("POP r26")                     #   the callee-saved regs

        # LHU (sub-word load, G10): same shape as LBU but 16-bit lanes.
        # A naturally-aligned halfword sits wholly in one word; lane =
        # (addr>>1)&1, i.e. bit 1 of the byte address, so shift = (addr&2)<<3
        # (0 or 16). Signed LH is not implemented -- GCC rv32i -O1 never
        # emits it (it uses `lhu` + `slli 16` + `srai 16` instead), see
        # tests/test_rv64i_to_glyph_unimplemented_ops.py.
        elif op == OP_LHU:
            if rd != 0:
                # DEFECT-16c (same class as the LBU fix above): PUSH/POP
                # the t-reg scratch around the halfword extract, minus rd.
                # DEFECT-30 (same fix as the LBU lowering above): push only
                # what is popped, and take the mask/lane scratch from the
                # pushed set so no scratch aliases rd after `LD rd`.
                scratch = [r for r in (28, 29, 30) if r != rd]
                if len(scratch) == 2:
                    scratch.append(26)          # r26: DEFECT-11-proven
                                                # safe extra save/restore
                                                # slot for this lowering
                # Ensure _addr does not alias rs1 so LDI imm cannot clobber rs1
                avail = [r for r in scratch if r != rs1]
                _addr = avail[0]
                rem = [r for r in scratch if r != _addr]
                _lane, _mask = rem[0], rem[1]
                for _r in scratch:
                    lines.append(f"PUSH r{_r}")
                lines.append(f"LDI r{_addr} 0x{imm & 0xFFFFFFFF:x}")
                _emit_add_reg(lines, f"r{_addr}", rs1)
                lines.append(f"LDI r{_lane} 2")
                lines.append(f"AND r{_lane} r{_addr}")
                lines.append(f"LDI r{_mask} 3")
                lines.append(f"SHL r{_lane} r{_mask}")   # shift (0 or 16)
                if byte_to_word_mem:
                    lines.append(f"LDI r{_mask} 2")
                    lines.append(f"SHR r{_addr} r{_mask}")
                lines.append(f"LD r{rd} r{_addr}")
                lines.append(f"SHR r{rd} r{_lane}")
                lines.append(f"LDI r{_mask} 0xffff")
                lines.append(f"AND r{rd} r{_mask}")
                for _r in reversed(scratch):
                    lines.append(f"POP r{_r}")

        # SH (sub-word store, G10): RMW the containing word, exactly like SB
        # but with a 0xFFFF lane mask and shift = (addr&2)<<3. Same DEFECT 11
        # fix: PUSH/POP r26/r27 around the RMW (see the SB comment).
        elif op == OP_SH:
            if rs1 == 30:
                # DEFECT-31c minimal fix (same shape as OP_SB above): single
                # address computation in r28, base kept live in r30, 16-bit
                # lane mask (addr&2)<<3. Byte-identical to HEAD for all
                # non-aliased sites (the else branch below IS the HEAD body).
                lines.append("PUSH r26")
                lines.append("PUSH r27")
                lines.append("PUSH r30")
                lines.append(f"LDI r28 0x{imm & 0xFFFFFFFF:x}")
                _emit_add_reg(lines, "r28", rs1)      # r28 = addr; base intact
                lines.append("LDI r27 2")
                lines.append("AND r27 r28")           # r27 = lane (addr&2)
                lines.append("LDI r29 3")
                lines.append("SHL r27 r29")           # r27 = shift (0 or 16)
                lines.append("LDI r29 2")
                lines.append("SHR r28 r29")           # r28 = word_addr
                lines.append("LD r29 r28")            # r29 = cur_word
                lines.append("LDI r26 0")
                _emit_add_reg(lines, "r26", rs2)      # r26 = value
                lines.append("LDI r30 0xffff")
                lines.append("AND r26 r30")           # value &= 0xffff
                lines.append("SHL r26 r27")           # value <<= shift
                lines.append("SHL r30 r27")           # r30 = 0xffff<<shift
                lines.append("OR r29 r30")
                lines.append("XOR r29 r30")           # lane cleared
                lines.append("OR r29 r26")            # insert value
                lines.append("ST r28 r29")
                lines.append("POP r30")
                lines.append("POP r27")
                lines.append("POP r26")
            else:
                lines.append("PUSH r26")
                lines.append("PUSH r27")
                lines.append(f"LDI r30 0x{imm & 0xFFFFFFFF:x}")
                _emit_add_reg(lines, "r30", rs1)
                lines.append("LDI r28 2")
                lines.append("AND r28 r30")
                lines.append("LDI r29 3")
                lines.append("SHL r28 r29")            # r28 = shift, kept below
                lines.append(f"LDI r30 0x{imm & 0xFFFFFFFF:x}")
                _emit_add_reg(lines, "r30", rs1)
                if byte_to_word_mem:
                    lines.append("LDI r29 2")
                    lines.append("SHR r30 r29")          # r30 = word_addr, kept below
                lines.append("LD r29 r30")                # r29 = cur_word
                lines.append("LDI r27 0xffff")
                lines.append("SHL r27 r28")                # r27 = mask (0xFFFF<<shift)
                lines.append("OR r29 r27")
                lines.append("XOR r29 r27")                 # r29 = cur_word, lane cleared
                lines.append("LDI r26 0")
                _emit_add_reg(lines, "r26", rs2)
                lines.append("LDI r27 0xffff")
                lines.append("AND r26 r27")
                lines.append("SHL r26 r28")                 # r26 = (rs2&0xffff)<<shift
                lines.append("OR r29 r26")
                lines.append("ST r30 r29")
                lines.append("POP r27")                     # DEFECT 11: restore
                lines.append("POP r26")                     #   the callee-saved regs

        # BEQ
        elif op == OP_BEQ:
            simm = imm if imm < 0x80000000 else imm - 0x100000000
            target_pc = pc + simm
            tlabel = symbols.get(target_pc, f"pc_{target_pc:08x}")
            if not tlabel.startswith(":"):
                tlabel = ":" + tlabel
            if rs1 == 0 and rs2 == 0:
                lines.append(f"JMP {tlabel}")
            elif rs1 == 0:
                # DEFECT-16b: r28 is RV x28 (t3) under the identity map --
                # save/restore it around the zero-scratch compare (same
                # class as the BLT/BGE fix; pops BEFORE the JZ so the
                # CMP flag in r0 survives).
                lines.append("PUSH r28")
                lines.append("LDI r28 0")
                lines.append(f"CMP r28 r{rs2}")
                lines.append("POP r28")
                lines.append(f"JZ {tlabel}")
            elif rs2 == 0:
                lines.append("PUSH r28")
                lines.append("LDI r28 0")
                lines.append(f"CMP r{rs1} r28")
                lines.append("POP r28")
                lines.append(f"JZ {tlabel}")
            else:
                lines.append(f"CMP r{rs1} r{rs2}")
                lines.append(f"JZ {tlabel}")

        # BNE
        elif op == OP_BNE:
            simm = imm if imm < 0x80000000 else imm - 0x100000000
            target_pc = pc + simm
            tlabel = symbols.get(target_pc, f"pc_{target_pc:08x}")
            if not tlabel.startswith(":"):
                tlabel = ":" + tlabel
            skip_lbl = f":__skip_bne_{bne_counter}"
            bne_counter += 1
            if rs1 == 0 and rs2 == 0:
                pass  # Never branches
            elif rs1 == 0:
                # DEFECT-16b: save/restore r28 (RV t3) around the
                # zero-scratch compare, pops BEFORE the JZ (see BEQ).
                lines.append("PUSH r28")
                lines.append("LDI r28 0")
                lines.append(f"CMP r28 r{rs2}")
                lines.append("POP r28")
                lines.append(f"JZ {skip_lbl}")
                lines.append(f"JMP {tlabel}")
                lines.append(skip_lbl)
            elif rs2 == 0:
                lines.append("PUSH r28")
                lines.append("LDI r28 0")
                lines.append(f"CMP r{rs1} r28")
                lines.append("POP r28")
                lines.append(f"JZ {skip_lbl}")
                lines.append(f"JMP {tlabel}")
                lines.append(skip_lbl)
            else:
                lines.append(f"CMP r{rs1} r{rs2}")
                lines.append(f"JZ {skip_lbl}")
                lines.append(f"JMP {tlabel}")
                lines.append(skip_lbl)

        # BLT
        # DEFECT-16 (2026-09-12, BK-11 cron session; receipts
        # output/bk11_gate_run1_red.txt + dbg_bk11_probe6..15): r28/r29/r30
        # are ALSO the glyph names of RV32 x28/x29/x30 (t3/t4/t5) under the
        # transpiler's identity register map -- GCC keeps loop-invariant
        # compare constants in exactly these t-registers across calls and
        # branches (observed: `li t3,1 / li t1,32 / li a7,8` hoisted out of
        # wc's word-count ladder). Every BLT/BLTU/BGE/BGEU lowering clobbers
        # all three as scratch WITHOUT save/restore, so any loop holding
        # live values in t-regs silently corrupted them at the first taken
        # or not-taken compare-branch. (The DEFECT-11 class: SB/SH got
        # PUSH/POP protection for r26/r27; the branch lowerings never did.)
        # FIX: PUSH/POP all three around the compare. The pops run BEFORE
        # the JZ: glyph CMP writes its flag to r0 and PUSH/POP don't touch
        # r0, so the flag survives the pops and BOTH the taken and
        # fall-through paths see restored t-regs.
        elif op in (OP_BLT, OP_BLTU):
            simm = imm if imm < 0x80000000 else imm - 0x100000000
            target_pc = pc + simm
            tlabel = symbols.get(target_pc, f"pc_{target_pc:08x}")
            if not tlabel.startswith(":"):
                tlabel = ":" + tlabel
            lines.append("PUSH r28")
            lines.append("PUSH r29")
            lines.append("PUSH r30")
            lines.append("LDI r30 0")
            _emit_add_reg(lines, "r30", rs1)
            _emit_sub_reg(lines, "r30", rs2)
            lines.append("LDI r29 31")
            lines.append("SHR r30 r29")
            lines.append("LDI r28 1")
            lines.append("CMP r30 r28")
            lines.append("POP r30")
            lines.append("POP r29")
            lines.append("POP r28")
            lines.append(f"JZ {tlabel}")

        # BGE
        # DEFECT-16 (same class as the BLT/BLTU fix above): PUSH/POP
        # r28/r29/r30 around the compare, pops BEFORE the JZ so the CMP
        # flag (r0) drives the branch after the t-regs are restored.
        elif op in (OP_BGE, OP_BGEU):
            simm = imm if imm < 0x80000000 else imm - 0x100000000
            target_pc = pc + simm
            tlabel = symbols.get(target_pc, f"pc_{target_pc:08x}")
            if not tlabel.startswith(":"):
                tlabel = ":" + tlabel
            lines.append("PUSH r28")
            lines.append("PUSH r29")
            lines.append("PUSH r30")
            lines.append("LDI r30 0")
            _emit_add_reg(lines, "r30", rs1)
            _emit_sub_reg(lines, "r30", rs2)
            lines.append("LDI r29 31")
            lines.append("SHR r30 r29")
            lines.append("LDI r28 0")
            lines.append("CMP r30 r28")
            lines.append("POP r30")
            lines.append("POP r29")
            lines.append("POP r28")
            lines.append(f"JZ {tlabel}")

        # JAL
        elif op == OP_JAL:
            simm = imm if imm < 0x80000000 else imm - 0x100000000
            target_pc = pc + simm
            tlabel = symbols.get(target_pc, f"pc_{target_pc:08x}")
            if not tlabel.startswith(":"):
                tlabel = ":" + tlabel
            if rd == 0:
                lines.append(f"JMP {tlabel}")
            else:
                # Glyph CALL only manages the internal r31 return-address
                # stack; it never writes a register, unlike real RV `jal rd,`
                # which puts the return address in rd as ordinary DATA
                # synchronously with the jump -- the callee sees it
                # immediately, not only after returning. Code that later
                # treats ra as data (swtch.S-style: `sw ra,0(a0)` to save it,
                # `lw ra,0(a1); ret` to jump through it) needs rd set BEFORE
                # control transfers. This doesn't disturb the normal nested-
                # call path: RET still pops r31 unconditionally, independent
                # of rd's value.
                lines.append(f"LDI r{rd} 0x{(pc + 4) & 0xFFFFFFFF:x}")
                lines.append(f"CALL {tlabel}")

        # JALR
        elif op == OP_JALR:
            if rd == 0 and rs1 == 1 and imm == 0 and ra_source == 'call':
                lines.append("RET")
            else:
                # switch_to's own terminal, data-sourced `ret` (see the
                # POP r28 note below) is also xv6-nano's privilege boundary:
                # it lowers to KJMP, not JMPR, so GlyphCPUv2 drops USER->SUPER
                # (or re-arms USER from MODE_LATCH) exactly at the context
                # switch. Any OTHER computed `jalr x0` -- tail calls, jump
                # tables -- stays JMPR and never touches privilege.
                _is_switch_ret = (rd == 0 and rs1 == 1 and imm == 0)
                if _is_switch_ret:
                    # ra_source == 'data': this is switch_to's own terminal
                    # ret (a resume, not a return), routed through the
                    # computed-jump path below instead of glyph RET. But the
                    # CALL that invoked THIS activation (`jal ra,switch_to`,
                    # rd!=0 -> glyph CALL) already pushed a frame on r31 that
                    # a genuine RET would have popped -- routing around RET
                    # here leaks that frame permanently. After enough
                    # accumulated switch_to calls, an unrelated LATER
                    # function's real `ret` pops one of these stale leaked
                    # entries instead of its own true return address and
                    # jumps into garbage. (Found live: scheduler's own
                    # correctly-classified final `ret`, after 12 switch_to
                    # calls, landed inside a task's dead-end placeholder loop
                    # instead of returning to run_all.) Fix: discard-pop one
                    # frame here to keep CALL/RET-or-equivalent balanced --
                    # assumes every ra-data-sourced ret corresponds to a
                    # function that was itself CALL-entered (true for every
                    # landed primitive; a tail-JMP-entered function with a
                    # data-sourced ret would have nothing to balance here).
                    lines.append("POP r28")
                # Dynamic target: the register holds a RISC-V byte address
                # (e.g. a function pointer loaded from data), but glyph PCs
                # are pixel-packed (row<<16)|col — different address spaces.
                # Translate through the pointer table at the (possibly
                # overridden) pointer-table base:
                # r30 = TABLE_BASE + rs1 + imm; r30 >>= 2; r30 = mem[r30].
                # The loader fills the table via build_pointer_table().
                # TICKET_R53_day1_transpiler_auipc_jalr (2026-09-22): the
                # immediate is LOAD-BEARING for rustc's call idiom
                # `auipc ra,0x0; jalr -N(ra)` — target = ra + imm. The old
                # lowering indexed the table at rs1 alone, so every rustc
                # call jumped to table[wi(ra)] = the auipc's own entry
                # (measured packed 0x3 = :pc_4 for the fib(15) repro) and
                # spun; gcc's `jalr ra,0(a5)` (imm=0) masked the defect.
                # NOTE: RISC-V clears target bit 0; no glyph AND-imm op
                # exists and no rv32 toolchain emits odd text targets, so
                # the ~1 mask is not applied (receipt honesty note).
                lines.append(f"LDI r30 0x{_tbl_base:x}")
                lines.append(f"ADD r30 r{rs1}")
                if imm != 0:
                    lines.append(f"LDI r29 0x{imm & 0xFFFFFFFF:x}")
                    lines.append("ADD r30 r29")
                lines.append("LDI r29 2")
                lines.append("SHR r30 r29")
                lines.append("LD r30 r30")
                if rd != 0:
                    # Computed CALL (GCC fn-pointer idiom `jalr ra, 0(a5)`):
                    # Glyph CALLR pushes the return pc on the call stack; the
                    # callee's plain `ret` pops it. (Bare JMPR dropped the
                    # return address; caught by the proc-table test.) Also
                    # set rd = return byte address as DATA before the jump,
                    # same reasoning as the JAL case above.
                    lines.append(f"LDI r{rd} 0x{(pc + 4) & 0xFFFFFFFF:x}")
                    lines.append("CALLR r30")
                elif _is_switch_ret:
                    lines.append("KJMP r30")
                else:
                    lines.append("JMPR r30")

        # ECALL
        elif op == OP_ECALL:
            lines.append("HALT")

        # EBREAK -> glyph SYSCALL (xv6-nano E-K2 `__syscall` intrinsic). The
        # kernel puts the syscall number in a7 and args in a0/a1 before the
        # `ebreak`; GlyphCPUv2 marshals those regs for the SUPER-mode
        # dispatcher at KSYS_PC and delivers the result back into a0.
        elif op == OP_EBREAK:
            lines.append("SYSCALL r10")

        # MRET -> glyph SYSRET: return from that dispatcher (mode=USER, resume
        # at the saved post-SYSCALL PC). Only meaningful with KSYS_PC set.
        elif op == OP_MRET:
            lines.append("SYSRET")

        else:
            raise ValueError(f"Unimplemented RV64I/RV32I opcode enum {op} at 0x{pc:08x}")

    if stack_addr is None:
        n_glyph_instr = sum(
            1 for ln in lines
            if ln.strip() and not ln.startswith(":") and not ln.startswith("#")
        )
        auto = _auto_stack_addr(n_glyph_instr, cols_instrs)
        lines = [
            ln.replace(_AUTO_STACK_SENTINEL, str(auto)) if _AUTO_STACK_SENTINEL in ln else ln
            for ln in lines
        ]

    if use_ir:
        _verify_via_ir(lines, base_addr, byte_to_word_mem, cols_instrs,
                       ptr_table_base=_tbl_base)

    return "\n".join(lines) + "\n"


def _raise_to_ir(lines, base_addr, byte_to_word_mem, cols_instrs,
                 ptr_table_base=None):
    """Raise the emitted glyph lines into a GlyphIRModule — GH-15 Step 5:
    delegates parsing to glyph_ir.raise_lines_to_ir (the ONE raiser);
    this lane keeps only its module-shape policy (literal pc_NNN labels,
    no entry fusion, pointer table, emitted-image window)."""
    import glyph_ir as gi

    policy = gi.RaisePolicy(
        entry_label="",              # labels are literal :pc_<pc>
        fuse_entry=False,
        cont_prefix="",              # unused: every block has a label
        strict_operands=False,
        window="emitted", cols_instrs=cols_instrs,
        preserves=(),
        data_bounds=(0, ((PTR_TABLE_BASE if ptr_table_base is None
                          else ptr_table_base) >> 2) - 1),
        extra_metadata={"rv_base": base_addr},
    )
    # The transpiler's emitted lines always start with the prologue label
    # :blk_0000-style labels already in the stream — no entry fusion.
    module = gi.raise_lines_to_ir(
        lines, name=f"rv_{base_addr:08x}", policy=policy,
        data_sections=[gi.DataSection(symbol=f"text_{base_addr:x}",
                                      base_word=0, words=[])],
        pointer_table=gi.PointerTable(
                                      base_word=(PTR_TABLE_BASE if ptr_table_base is None
                                                 else ptr_table_base) >> 2,
                                      block_targets=[]),
    )
    return module


def _verify_via_ir(lines, base_addr, byte_to_word_mem, cols_instrs,
                   ptr_table_base=None):
    """Dual-path gate: raise to IR and statically verify. Byte-exact
    legacy emission either way — this only ever REJECTS."""
    import glyph_ir as gi
    module = _raise_to_ir(lines, base_addr, byte_to_word_mem, cols_instrs,
                          ptr_table_base=ptr_table_base)
    gi.StaticVerifier(module).verify()


def transpile_elf_to_glyph(
    elf_path_or_bytes: Union[str, Path, bytes],
    entry_symbol: Optional[str] = "_start",
    stack_addr: Optional[int] = None,
    byte_to_word_mem: bool = True,
    cols_instrs: int = 64,
    use_ir: bool = True,
    ptr_table_base: Optional[int] = None,
) -> str:
    """Convenience function to transpile an ELF file or raw bytes to Glyph assembly.

    `stack_addr=None` (default) auto-sizes the glyph call stack past the code
    image; pass an int only to override. `cols_instrs` must match what you
    later hand to `assemble_glyph_to_pixels`.
    """
    if isinstance(elf_path_or_bytes, (str, Path)):
        with open(elf_path_or_bytes, "rb") as f:
            data = f.read()
    else:
        data = elf_path_or_bytes

    base_addr, text_bytes, symbols = parse_elf(data)
    return transpile_rv32i_to_glyph(
        text_bytes=text_bytes,
        symbols=symbols,
        base_addr=base_addr,
        entry_symbol=entry_symbol,
        stack_addr=stack_addr,
        byte_to_word_mem=byte_to_word_mem,
        cols_instrs=cols_instrs,
        use_ir=use_ir,
        ptr_table_base=ptr_table_base,
    )


def assemble_glyph_to_pixels(
    glyph_source: str,
    cols_instrs: int = 64,
    min_rows: int = 16,
    wordbase_path: Optional[Path] = None,
) -> Tuple[np.ndarray, Dict[str, Tuple[int, int]]]:
    """
    Assemble .glyph assembly text into a 2D spatial pixel buffer.

    Resolves label references into spatial coordinates `(col, row)`.

    Returns:
        (pixel_array, label_coordinates_map)
    """
    raw_lines = [line.strip() for line in glyph_source.splitlines() if line.strip() and not line.startswith('#')]

    labels: Dict[str, int] = {}
    instr_count = 0
    for line in raw_lines:
        if line.startswith(':'):
            labels[line.split()[0]] = instr_count
        else:
            instr_count += 1

    resolved: List[str] = []
    # Resolve label refs to `col,row` on whitespace-delimited token
    # boundaries. Plain substring replacement mangles any label that is a
    # substring of another (`:task` inside `:task_a`), order-dependently --
    # the transpiler's own fixed-width `:pc_%08x` labels can't collide, but
    # hand-written fixture labels can. Longest-first is a further guard.
    _pats = [(re.compile(r'(?<!\S)' + re.escape(lbl) + r'(?!\S)'), idx)
             for lbl, idx in sorted(labels.items(), key=lambda kv: -len(kv[0]))]
    for line in raw_lines:
        if line.startswith(':'):
            continue
        for pat, idx in _pats:
            col = idx % cols_instrs
            row = idx // cols_instrs
            line = pat.sub(f"{col},{row}", line)
        resolved.append(line)

    op_map = OpcodeMapV2(wordbase_path)
    assembler = GlyphAssemblerV2(op_map)
    pixels = assembler.assemble(resolved, width_instrs=cols_instrs)

    # Pad rows so the image always contains the blank band the auto-sized
    # glyph call stack lives in: `_STACK_GAP_ROWS` below the last code row
    # (the stack pointer sits one pixel inside it), plus two spare rows so the
    # pointer itself is strictly below the image top and never wraps. A
    # caller that overrode `stack_addr` upward is still covered by `min_rows`.
    code_rows = -(-instr_count // cols_instrs)  # ceil
    need_rows = max(min_rows, code_rows + _STACK_GAP_ROWS + 2)
    if pixels.shape[0] < need_rows:
        padded = np.zeros((need_rows, pixels.shape[1], 3), dtype=np.uint8)
        padded[:pixels.shape[0], :pixels.shape[1]] = pixels
        pixels = padded

    coords_map = {
        name: (idx % cols_instrs, idx // cols_instrs)
        for name, idx in labels.items()
    }
    return pixels, coords_map


def main():
    parser = argparse.ArgumentParser(
        description="Transpile RV32I/RV64I ELF machine code to Geometry OS Glyph ISA v2 assembly"
    )
    parser.add_argument("input", help="Path to input ELF or binary file")
    parser.add_argument("-o", "--output", help="Output file path (.glyph or .png)")
    parser.add_argument("--raw", action="store_true", help="Treat input as raw binary rather than ELF")
    parser.add_argument("--entry", default="_start", help="Entry symbol name (default: _start)")
    parser.add_argument("--assemble", action="store_true", help="Assemble to pixel PNG image")
    parser.add_argument("--stack-addr", type=int, default=None,
                        help="Initial hardware stack r31 pixel index (default: auto-sized past the code image)")
    parser.add_argument("--cols", type=int, default=64, help="Instruction columns per row (default: 64)")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file {input_path} does not exist", file=sys.stderr)
        sys.exit(1)

    data = input_path.read_bytes()
    try:
        if args.raw:
            glyph_text = transpile_rv32i_to_glyph(data, entry_symbol=None, stack_addr=args.stack_addr)
        else:
            glyph_text = transpile_elf_to_glyph(data, entry_symbol=args.entry, stack_addr=args.stack_addr)
    except RVX31RefusalError as exc:
        sys.stderr.write(f"{exc}\n")
        sys.exit(1)

    if args.assemble or (args.output and args.output.endswith(".png")):
        from PIL import Image
        pixels, _ = assemble_glyph_to_pixels(glyph_text, cols_instrs=args.cols)
        out_path = args.output or input_path.with_suffix(".glyph.png")
        img = Image.fromarray(pixels, "RGB")
        img.save(out_path)
        print(f"Assembled {pixels.shape[1]}x{pixels.shape[0]} pixel image saved to {out_path}")
    else:
        out_path = args.output or input_path.with_suffix(".glyph")
        with open(out_path, "w") as f:
            f.write(glyph_text)
        print(f"Transpiled Glyph assembly saved to {out_path}")


if __name__ == "__main__":
    main()

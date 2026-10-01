#!/usr/bin/env python3
"""
Glyph Stratum Spatial ISA v1.0 — fixed-width, collision-safe pixel CPU.

Every instruction is a 1x4 horizontal pixel block:
    Pixel 0 (Opcode):    semantic RGB derived from wordbase.db
    Pixel 1 (Registers): R=rs1, G=rs2, B=rd  (0xFF = UNUSED_REGISTER)
    Pixel 2 (Imm-Low):   lower 24 bits of immediate/coordinate (RGB)
    Pixel 3 (Imm-High):  upper bits / flags / padding (black = unused)

PC.x must always be a multiple of 4 (INSTR_WIDTH). Unaligned jump
targets raise SpatialMisalignmentFault.

RGB (0,0,0)-(4,4,4) is the reserved System Palette: no opcode may map
there. Collisions are resolved by reassigning the opcode to the next
free color, not by clamping (clamping would merge two opcodes).
"""

import os
from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from tools.wordbase import WordbaseManager

INSTR_WIDTH = 4
RESERVED_MAX = 4  # (0,0,0)..(4,4,4) reserved
UNUSED_REGISTER = 0xFF

# --- xv6-nano isolation (E-K1): reserved MMIO-style word block ---------------
# GlyphCPUv2's data memory (self.memory) is a flat word array. The kernel
# programs the per-task privilege box by storing to these fixed BYTE
# addresses from SUPER mode; the engine reads them every step so a write
# takes effect immediately. Word index = addr >> 2. The block sits at
# byte 0x8000 (word 0x2000) -- above the kernel's stack top (sp starts
# 0x4000, grows down) and clear of PTR_TABLE_BASE (0x2000 + a small table),
# yet inside the GPU oracle SpatialRV64ICore's 36864-byte space so the
# no-fault leg's identical MMIO stores land harmlessly there too.
# See systems/XV6_NANO_ISOLATION_ROADMAP.md (E1-E5).
BOX_MMIO_BASE = 0x8000
MODE_LATCH_ADDR = BOX_MMIO_BASE + 0x00   # kernel writes 1 (USER); engine one-shots it on the next JMPR/CALLR
KFAULT_PC_ADDR  = BOX_MMIO_BASE + 0x04   # packed pixel PC (row<<16)|col of the kernel fault handler; 0 = disabled
KSYS_PC_ADDR    = BOX_MMIO_BASE + 0x08   # E-K2: packed pixel PC of the syscall handler; unused in E-K1
BOX0_LO_ADDR    = BOX_MMIO_BASE + 0x0C   # byte range [lo, hi) the user task may store into (its arena slot)
BOX0_HI_ADDR    = BOX_MMIO_BASE + 0x10
BOX1_LO_ADDR    = BOX_MMIO_BASE + 0x14   # second permitted range (its own proc[] entry / context struct)
BOX1_HI_ADDR    = BOX_MMIO_BASE + 0x18
FAULT_ADDR_ADDR = BOX_MMIO_BASE + 0x1C   # engine writes: faulting byte address
FAULT_PC_ADDR   = BOX_MMIO_BASE + 0x20   # engine writes: packed pixel PC of the offending store
SYSCALL_PC_ADDR = BOX_MMIO_BASE + 0x24   # E-K2: saved resume PC
BOX2_LO_ADDR    = BOX_MMIO_BASE + 0x28   # third permitted range (its own kernel-stack page: a
BOX2_HI_ADDR    = BOX_MMIO_BASE + 0x2C   # yielding task's switch_to prologue spills ra/s0 here)
SYS_N_ADDR      = BOX_MMIO_BASE + 0x30   # E-K2: SYSCALL marshals a7/a0/a1 (glyph r17/r10/r11) into
SYS_A0_ADDR     = BOX_MMIO_BASE + 0x34   # these words for the SUPER-mode C dispatcher to read;
SYS_A1_ADDR     = BOX_MMIO_BASE + 0x38   # the dispatcher writes its result back into SYS_A0.
KTICK_PC_ADDR     = BOX_MMIO_BASE + 0x3C # GH-16: packed pixel PC of kernel tick handler; 0 = disabled
TIMER_COUNT_ADDR  = BOX_MMIO_BASE + 0x40 # GH-16: countdown steps remaining
TIMER_RELOAD_ADDR = BOX_MMIO_BASE + 0x44 # GH-16: reload value when timer expires
TICK_PC_ADDR      = BOX_MMIO_BASE + 0x48 # GH-16: engine writes: interrupted packed pixel PC
PAGE_TABLE_ADDR   = BOX_MMIO_BASE + 0x4C # GH-17: base word of page table in RAM; 0 = disabled
PAGE_TABLE_WORD   = PAGE_TABLE_ADDR >> 2 # 8211
PAGE_WORDS        = 256                  # GH-17: 256 words (1024 bytes) per page
PAGE_TABLE_BASE_WORD = 1536              # GH-17: architectural page table base (words 1536..1792)

# DEFECT-23-ROOT (RULING_defect23_root_pte_acceptance.md Option 1):
# Container tag for page-table windows. A page-table window starting at pt_base
# must carry PAGE_TABLE_TAG at memory[pt_base - 1] before any slot in that window
# is trusted as a mapping.
# Header-slot choice: pt_base - 1 is immediately preceding the table base.
# Putting the header at memory[pt_base] collides with slot 0 (vpn == 0 PTE),
# which breaks existing PTE values (0x7, 0x107, ...) and landed window layouts.
# Slot pt_base - 1 preserves all 256 PTE slots [pt_base, pt_base + 256),
# never collides with any vpn in [0, 255], and fits naturally in 24 bits for
# pixel-image and WGSL twin parity.
PAGE_TABLE_TAG   = 0x505447             # ASCII "PTG" (Page Table Glyph, 24-bit container tag)
PAGE_TABLE_MAGIC = PAGE_TABLE_TAG


def check_pt_tag(cpu, image, pt_base: int) -> tuple[bool, int, str]:
    """DEFECT-23-ROOT Option 1 shared predicate: verify page-table container tag.

    A page-table window starting at pt_base must carry PAGE_TABLE_TAG at pt_base - 1.
    RAM is checked first; fallback to image pixels if RAM word is 0 (GH-25 parity).
    Returns (is_valid, tag_value, fault_reason_string).
    """
    tag_addr = pt_base - 1
    tag = 0
    if 0 <= tag_addr < len(cpu.memory):
        tag = cpu.memory[tag_addr]
    if tag == 0 and image is not None:
        h_img, w_img, _ = image.shape
        if 0 <= tag_addr < w_img * h_img:
            tag = cpu._mem_read(image, tag_addr)
    if tag == PAGE_TABLE_TAG:
        return True, tag, ""
    reason = (
        f"pt_tag_mismatch got={tag:#x} expected={PAGE_TABLE_TAG:#x} "
        f"pt_base={pt_base} tag_addr={tag_addr} site=glyph_isa_v2"
    )
    return False, tag, reason


PTE_V   = 0x1   # Valid
PTE_W   = 0x2   # Writable
PTE_U   = 0x4   # User-accessible
PTE_PIX = 0x8   # Spatial pixel-backed frame in image
PTE_HILB = 0x10  # GH-25: pfn field = packed 2D Hilbert frame origin (row<<8|col)
HILB_SIDE = 64  # GH-25: frame grid is 64x64 frame slots (Hilbert curve side)

# --- xv6-nano isolation (GO-2): the box as a 2D tile ------------------------
# systems/GPU_OS_ROADMAP.md GO-2 (folds in isolation-roadmap E-K3). A task's
# permitted memory can be expressed as a rectangle on the pixel grid: a byte
# address `a` maps to word `w = a >> 2`, then to grid coordinates
# (row, col) = (w // W_MEM, w % W_MEM). W_MEM (grid width, in 32-bit words) is
# a fixed constant shared byte-for-byte with the WGSL SpatialRV64ICore engine
# (const W_MEM in tools/SPATIAL_RV64I.wgsl) and the fixture (#define W_MEM in
# tests/fixtures/xv6_nano.c). The tile words sit above the GPU engine's GPR
# snapshot block (which ends at 0x8150) so the two engines never collide.
W_MEM = 32                              # 128 bytes / grid row
TILE_ROW_ADDR   = BOX_MMIO_BASE + 0x160  # kernel-armed tile origin (grid row / col) ...
TILE_COL_ADDR   = BOX_MMIO_BASE + 0x164
TILE_H_ADDR     = BOX_MMIO_BASE + 0x168  # ... and extent. TILE_H == 0 -> tile unset / inert.
TILE_W_ADDR     = BOX_MMIO_BASE + 0x16C

# --- xv6-nano interactive shell input (GO-3): a host-fed MMIO input ring ----
# systems/GPU_OS_ROADMAP.md GO-3. The test harness writes INPUT_LEN and the
# scripted byte stream at INPUT_DATA before the run (the same way it seeds
# KFAULT_PC); the SUPER-mode C syscall_dispatch services SYS_read (syscall #2)
# by copying one line out of the ring into the caller's buffer and advancing
# INPUT_CURSOR. Neither engine needs to know these words -- the dispatcher runs
# in SUPER and its loads/stores are never box-checked. Placed above the GO-2
# tile words (end 0x816C) and the GPU engine's 32-GPR snapshot (end 0x8150);
# the 64-byte data region ends at 0x81C0 (word 8304), inside both the
# 16384-word Glyph memory and the 36864-byte SpatialRV64ICore GO test core.
INPUT_LEN_ADDR    = BOX_MMIO_BASE + 0x170  # total bytes the harness loaded
INPUT_CURSOR_ADDR = BOX_MMIO_BASE + 0x174  # bytes consumed so far (dispatcher advances)
INPUT_DATA_ADDR   = BOX_MMIO_BASE + 0x180  # start of the byte stream
INPUT_DATA_CAP    = 64                     # max scripted bytes -> ends 0x81C0

MODE_SUPER = 0
MODE_USER = 1

# BK-42: syscalls whose PATH argument (r1) is decoded by the shared
# fence-blind _read_path. The path-decode consult (_bk42_path_fault)
# covers every one of them at the SYSCALL dispatch site.
_BK42_PATH_SYSCALLS = frozenset({0x03, 0x04, 0x07, 0x08, 0x09, 0x12, 0x13})


class SpatialMisalignmentFault(Exception):
    pass


class OpcodeMapV2:
    """Opcode <-> RGB mapping with reserved-palette collision avoidance."""

    OPCODES = {
        'HALT': 'stop',
        'LDI': 'load',
        'ADD': 'add',
        'SUB': 'subtract',
        'MUL': 'multiply',
        'CMP': 'compare',
        'JMP': 'jump',
        'JZ': 'jump_if',
        # SE024: inverted-sense aliases (GLYPH_ISA_ROADMAP.md §1.1). The
        # historical name JZ actually means "jump if the CMP flag (r0) is
        # SET" — i.e. jump-if-EQUAL — and the name keeps tripping authors
        # (measured 2026-09-16: an ISA-maintainer session wrote an inverted
        # JZ loop and only the test caught it). RULING: do-not-rename JZ
        # (51-file blast radius); the mitigation is additive aliases:
        #   JNZ = jump if r0 == 0        (jump-if-NOT-zero / not-equal)
        #   JNE = jump if r0 == 0        (alias of JNZ, reads naturally
        #        after CMP; both are the exact boolean complement of JZ)
        # JZ's encoding, color, and semantics are untouched — these are
        # new opcodes, new colors, new dispatch branches only.
        'JNZ': 'jump_if_not_zero',
        'JNE': 'jump_if_not_equal',
        # SE025 (GLYPH_ISA_ROADMAP.md §1.3): CMP tri-state + sign-aware jumps.
        # CMP itself is UNTOUCHED (boolean r0) so JZ/JNZ/JNE keep legacy
        # meaning forever. CMP3 writes a real encoding to r0:
        #   r0 = 0 (rd <  rs2, SIGNED) / 1 (equal) / 2 (rd > rs2)
        # and JLT/JGT consume it. r0 remains an ordinary register: a legacy
        # CMP after CMP3 restores pure-boolean semantics, so no program can
        # observe a difference unless it opts in via CMP3.
        'CMP3': 'compare_tristate',
        'JLT': 'jump_if_less',
        'JGT': 'jump_if_greater',
        'PRT': 'print',
        'LD': 'load',
        'ST': 'store',
        'LD': 'load',
        'ST': 'store',
        'LD': 'load',
        'ST': 'store',
        'AND': 'intersect',
        'OR': 'union',
        'XOR': 'exclusive',
        'SHL': 'shift_left',
        'SHR': 'shift_right',
        'ROTR': 'rotate_right',
        'PUSH': 'push',
        'POP': 'pop',
        'CALL': 'call',
        'RET': 'return',
        'JMPR': 'jump_register',
        'CALLR': 'call_register',
        'KJMP': 'kernel_jump',
        'SYSCALL': 'system_call',
        'SYSRET': 'system_return',
        # GPU-native parallel opcodes for spatial execution
        'PARALLEL_LD': 'parallel_load',
        'PARALLEL_ST': 'parallel_store',
        'PARALLEL_ADD': 'parallel_add',
        'PARALLEL_SUB': 'parallel_sub',
        'PARALLEL_REDUCE_SUM': 'parallel_reduce_sum',
    }

    # Fixed literal colors for the opcodes added in the Turing-complete
    # expansion (AND/OR/XOR/SHL/SHR/PUSH/POP/CALL/RET/SYSCALL). Unlike the original
    # 10 opcodes (which derive their color from a wordbase.db lookup and
    # therefore shift if the wordbase changes), these are pinned so the
    # WGSL GPU port never has to be regenerated to match a live database -
    # a real requirement once a decoder is hardcoding color literals.
    FIXED_COLORS: Dict[str, Tuple[int, int, int]] = {
        'AND':  (100, 149, 237),
        'MUL':  (218, 165, 32),    # goldenrod -- pinned for twin parity (SE023)
        'JNZ':  (172, 100, 52),    # sienna -- SE024, pinned for twin parity
        'JNE':  (243, 49, 5),      # orangered -- SE024, pinned for twin parity
        'CMP3': (47, 79, 79),      # dark slate gray -- SE025, pinned for twin parity
        'JLT':  (205, 133, 63),    # peru -- SE025, pinned for twin parity
        'JGT':  (154, 205, 50),    # yellowgreen -- SE025, pinned for twin parity
        'OR':   (255, 165, 0),
        'XOR':  (238, 130, 238),
        'SHL':  (0, 206, 209),
        'SHR':  (218, 112, 214),
        'ROTR': (72, 209, 204),
        'PUSH': (34, 139, 34),
        'POP':  (139, 69, 19),
        'CALL': (75, 0, 130),
        'RET':  (255, 215, 0),
        'JMPR': (60, 179, 113),
        'CALLR': (205, 92, 92),
        'KJMP': (46, 139, 87),   # sea green -- switch_to's terminal privilege-boundary jump
        'SYSCALL': (255, 69, 0),
        'SYSRET': (255, 99, 71),   # tomato -- return from the SUPER-mode syscall dispatcher
        # GPU-native parallel opcodes - distinctive colors for spatial ops
        'PARALLEL_LD': (147, 51, 234),     # Purple
        'PARALLEL_ST': (255, 20, 147),    # Deep Pink
        'PARALLEL_ADD': (0, 255, 127),    # Spring Green
        'PARALLEL_SUB': (255, 140, 0),    # Dark Orange
        'PARALLEL_REDUCE_SUM': (0, 191, 255),  # Deep Sky Blue
    }

    def __init__(self, wordbase_path: Optional[Path] = None):
        if wordbase_path is None:
            wordbase_path = Path(__file__).parent.parent / "db" / "wordbase.db"
        self.wordbase = WordbaseManager(wordbase_path)
        self._opcode_to_rgb: Dict[str, Tuple[int, int, int]] = {}
        self._rgb_to_opcode: Dict[Tuple[int, int, int], str] = {}
        self._build_maps()

    @staticmethod
    def _is_reserved(rgb: Tuple[int, int, int]) -> bool:
        r, g, b = rgb
        return r <= RESERVED_MAX and g <= RESERVED_MAX and b <= RESERVED_MAX

    def _next_free_color(self, start: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """Walk forward from `start` until an unreserved, unused color is found."""
        r, g, b = start
        packed = (r << 16) | (g << 8) | b
        while True:
            packed = (packed + 1) % (256 ** 3)
            candidate = ((packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF)
            if self._is_reserved(candidate):
                continue
            if candidate in self._rgb_to_opcode:
                continue
            return candidate

    def _build_maps(self):
        for opcode, word in self.OPCODES.items():
            if opcode in self.FIXED_COLORS:
                rgb = self.FIXED_COLORS[opcode]
                if self._is_reserved(rgb) or rgb in self._rgb_to_opcode:
                    rgb = self._next_free_color(rgb)
            else:
                rgb = self._color_for_word(word, opcode)
                if self._is_reserved(rgb) or rgb in self._rgb_to_opcode:
                    rgb = self._next_free_color(rgb)
            self._opcode_to_rgb[opcode] = rgb
            self._rgb_to_opcode[rgb] = opcode

    def _color_for_word(self, word: str, opcode: str) -> Tuple[int, int, int]:
        result = self.wordbase.get_word(word)
        if result and result.get('color_hex') and result['color_hex'].startswith('#'):
            h = result['color_hex']
            return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))
        hash_val = sum(ord(c) * (i + 1) for i, c in enumerate(opcode))
        return ((hash_val * 7) % 256, (hash_val * 13) % 256, (hash_val * 17) % 256)

    def opcode_to_rgb(self, opcode: str) -> Tuple[int, int, int]:
        return self._opcode_to_rgb[opcode]

    def rgb_to_opcode(self, rgb: Tuple[int, int, int]) -> Optional[str]:
        return self._rgb_to_opcode.get((int(rgb[0]), int(rgb[1]), int(rgb[2])))

    def close(self):
        self.wordbase.close()


def _pack_immediate(value: int) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """Pack a signed/unsigned int into Imm-Low (24 bits) + Imm-High (24 bits)."""
    uval = value & ((1 << 48) - 1)
    low24 = uval & 0xFFFFFF
    high24 = (uval >> 24) & 0xFFFFFF
    low_px = ((low24 >> 16) & 0xFF, (low24 >> 8) & 0xFF, low24 & 0xFF)
    high_px = ((high24 >> 16) & 0xFF, (high24 >> 8) & 0xFF, high24 & 0xFF)
    return low_px, high_px


def _unpack_immediate(low_px, high_px) -> int:
    low24 = (int(low_px[0]) << 16) | (int(low_px[1]) << 8) | int(low_px[2])
    high24 = (int(high_px[0]) << 16) | (int(high_px[1]) << 8) | int(high_px[2])
    return (high24 << 24) | low24


class GlyphAssemblerV2:
    """Assemble a tiny assembly dialect into a fixed-width 4-pixel-per-instruction image."""

    def __init__(self, opcode_map: OpcodeMapV2):
        self.opcode_map = opcode_map

    def assemble(self, lines: List[str], width_instrs: int = 8) -> np.ndarray:
        import re

        # Pass 1: collect label -> instruction index.
        # A label-def line is a line whose only token matches :name (e.g. :loop).
        # Label-def lines are not instructions — they must not consume an instruction
        # slot and must not emit pixels.
        labels: Dict[str, int] = {}
        raw_instrs: List[str] = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            code_part = line.split('#')[0].strip()
            if not code_part:
                continue
            tokens = code_part.split()
            if len(tokens) == 1 and tokens[0].startswith(':') and len(tokens[0]) > 1:
                labels[tokens[0]] = len(raw_instrs)
            else:
                raw_instrs.append(code_part)

        cols = width_instrs
        # Pass 2: for each JMP/JZ/CALL operand of the form :name, rewrite to the
        # coordinate string 'col,row' (row=idx//cols, col=idx%cols of the label's
        # instruction index), resolved longest-name-first so one label name cannot
        # be mangled as a substring of another.
        sorted_labels = sorted(labels.items(), key=lambda kv: -len(kv[0]))
        resolved_instrs: List[str] = []
        for line in raw_instrs:
            for lbl, idx in sorted_labels:
                col = idx % cols
                row = idx // cols
                line = re.sub(rf"(?<!\S){re.escape(lbl)}(?!\S)", f"{col},{row}", line)
            resolved_instrs.append(line)

        # RAM-vs-pixel-space static check (backlog item (a), SE023's note):
        # a heuristic linear-scan lint, not a control-flow-sound analysis -
        # same honesty standard as SE023's bounds check and DEFECT-23-ROOT's
        # in-window-slot boundary: it catches a real class, not every case.
        # RETIRED 2026-09-22 (Pillar 3 (d) completion, claim-queue round-3
        # item 7): with all five data handlers (0x01/0x02/0x03/0x04/0x08/
        # 0x09) reading/writing RAM via the _read_path single view, the
        # image-space-write set was down to {0x11: 1} — excluded-forever per
        # DEFECT-27 — so the check could never fire for a migrating handler
        # again. Per the (A) ruling's completion terms the machinery was
        # deleted, not narrowed: the LDI-const register tracking, the GH-8b
        # FS-window exemption, and the assemble-time raise are all gone.
        # Runtime FS-window aliasing (fs_pix_enabled, GH-8b/SE017) is
        # UNCHANGED - that is a different, live mechanism. Residual honesty:
        # an LD of an address written only by 0x11's image-space write now
        # assembles clean and still reads stale RAM at runtime; that hazard
        # is out of contract per DEFECT-27.

        instrs = []
        for line in resolved_instrs:
            parts = line.split()
            opcode = parts[0]
            args = parts[1:]
            for arg in args:
                if arg.startswith(':'):
                    raise ValueError(f"Undefined label '{arg}'")
            # SE023: bounds-check numeric (col,row) jump targets. Label-resolved
            # targets are in-bounds by construction (they index real
            # instructions); hand-written coordinates are the silent-corruption
            # vector — out-of-range targets execute black-pixel NOPs (walk-off)
            # or a neighboring instruction (off-by-one), with no runtime fault.
            # NOTE: compared against the FINAL instruction count
            # (len(resolved_instrs)), not len(instrs) — this loop is still
            # appending, and a mid-loop check would reject every forward jump.
            if opcode in ('JMP', 'JZ', 'JNZ', 'JNE', 'JLT', 'JGT', 'CALL'):
                x, y = args[0].split(',')
                idx = int(y) * cols + int(x)
                if idx < 0 or idx >= len(resolved_instrs):
                    raise ValueError(
                        f"{opcode} target {args[0]} out of bounds: index {idx} "
                        f"but program has {len(resolved_instrs)} instructions"
                    )

            instrs.append(parts)

        n = len(instrs)
        rows = (n + cols - 1) // cols
        width_px = cols * INSTR_WIDTH
        image = np.zeros((max(rows, 1), width_px, 3), dtype=np.uint8)

        for idx, parts in enumerate(instrs):
            row = idx // cols
            col = idx % cols
            base_x = col * INSTR_WIDTH

            opcode = parts[0]
            args = parts[1:]
            image[row, base_x] = self.opcode_map.opcode_to_rgb(opcode)

            rs1 = rs2 = rd = UNUSED_REGISTER
            imm = 0

            if opcode == 'LDI':
                rd = int(args[0][1:])
                # Parse immediate, supporting hex (0x) and decimal
                imm_str = args[1]
                if imm_str.startswith('0x') or imm_str.startswith('0X'):
                    imm = int(imm_str, 16)
                else:
                    imm = int(imm_str)
            elif opcode in ('ADD', 'SUB', 'MUL', 'CMP', 'CMP3', 'LD', 'AND', 'OR', 'XOR', 'SHL', 'SHR', 'ROTR'):
                rd = int(args[0][1:])
                rs2 = int(args[1][1:])
            elif opcode == 'ST':
                # ST <addr_reg> <value_reg> -> memory[addr_reg] = value_reg.
                # Encoded as rs1/rs2 (not rd/rs2) to match the live CPU
                # dispatch branch, which reads the address from rs1. Prior
                # encoding put the address in rd, which the CPU never read,
                # so ST always crashed with UNUSED_REGISTER (0xFF) as rs1.
                rs1 = int(args[0][1:])
                rs2 = int(args[1][1:])
            elif opcode in ('JMPR', 'CALLR', 'KJMP'):
                # Single operand: the register holding the packed
                # (row<<16)|col jump/call target — the same packing JMP's
                # immediate uses, just read from a register instead of
                # baked in at assemble time. This is what makes dispatch
                # dynamic: the target can be data (e.g. a WCB's stored
                # entry point) rather than a fixed label.
                rd = int(args[0][1:])
            elif opcode in ('PRT', 'PUSH', 'POP', 'SYSCALL'):
                rd = int(args[0][1:])
                # Parse immediate for SYSCALL
                if opcode == 'SYSCALL' and len(args) > 1:
                    imm_str = args[1]
                    if imm_str.startswith('0x') or imm_str.startswith('0X'):
                        imm = int(imm_str, 16)
                    else:
                        imm = int(imm_str)
            elif opcode in ('JMP', 'JZ', 'JNZ', 'JNE', 'JLT', 'JGT', 'CALL'):
                x, y = args[0].split(',')
                imm = (int(y) << 16) | int(x)  # pack coord into imm
            elif opcode in ('HALT', 'RET', 'SYSRET'):
                pass
            elif opcode == 'PARALLEL_LD':
                # PARALLEL_LD rd addr count - load count values starting at addr into rd
                rd = int(args[0][1:])
                imm_str = args[1]
                if imm_str.startswith('0x') or imm_str.startswith('0X'):
                    addr = int(imm_str, 16)
                else:
                    addr = int(imm_str)
                # count can be immediate or register
                if len(args) > 2:
                    if args[2].startswith('r'):
                        rs2 = int(args[2][1:])
                        imm = addr  # Just addr in imm, count in rs2
                    else:
                        # Immediate count: pack both addr and count into imm
                        count = int(args[2])
                        imm = (count << 24) | addr  # Pack count in high bits, addr in low bits
                        rs2 = 0  # Clear rs2 since count is in imm
            elif opcode == 'PARALLEL_ST':
                # PARALLEL_ST addr_reg rs count - store count values from rs starting at address in addr_reg
                if args[0].startswith('r'):
                    # Address is in a register
                    addr_reg = int(args[0][1:])
                    rs = int(args[1][1:])
                    if len(args) > 2:
                        if args[2].startswith('r'):
                            rs2 = int(args[2][1:])  # count in register
                            imm = 0  # dummy
                        else:
                            # Immediate count
                            count = int(args[2])
                            imm = count
                            rs2 = 0
                    # Store addr_reg in rs1 temporarily for the CPU to resolve
                    rs1 = addr_reg
                    # Make rd = rs (source register)
                    rd = rs
                else:
                    # Immediate address (fallback)
                    imm_str = args[0]
                    if imm_str.startswith('0x') or imm_str.startswith('0X'):
                        imm = int(imm_str, 16)
                    else:
                        imm = int(imm_str)
                    rs2 = int(args[1][1:])
                    rd = int(args[2][1:])
            elif opcode in ('PARALLEL_ADD', 'PARALLEL_SUB'):
                # PARALLEL_ADD rd rs1 rs2 count - elementwise add/sub of count values
                rd = int(args[0][1:])
                rs1 = int(args[1][1:])
                rs2 = int(args[2][1:])
                # count is in immediate
                if len(args) > 3:
                    imm_str = args[3]
                    if imm_str.startswith('0x') or imm_str.startswith('0X'):
                        imm = int(imm_str, 16)
                    else:
                        imm = int(imm_str)
            elif opcode == 'PARALLEL_REDUCE_SUM':
                # PARALLEL_REDUCE_SUM rd addr count - sum count values starting at addr into rd
                rd = int(args[0][1:])
                imm_str = args[1]
                if imm_str.startswith('0x') or imm_str.startswith('0X'):
                    imm = int(imm_str, 16)
                else:
                    imm = int(imm_str)
                # count can be immediate or register
                if len(args) > 2:
                    if args[2].startswith('r'):
                        rs2 = int(args[2][1:])
                    else:
                        # Immediate count: store count in imm, CPU handles it
                        count = int(args[2])
                        # Pack both addr and count into imm: low 24 bits = addr, high 24 bits = count
                        # But for simplicity, we'll use a different encoding
                        imm = (count << 24) | imm  # Pack count in high bits
                        rs2 = 0

            image[row, base_x + 1] = (rs1, rs2, rd)
            low_px, high_px = _pack_immediate(imm)
            image[row, base_x + 2] = low_px
            image[row, base_x + 3] = high_px

        return image


# --- 0x07 SYSCALL_RUN containment (RULING_run_syscall_containment) -----------
_RUNNER = subprocess.run


def _spawn(argv: List[str], cwd: str, timeout: int = 30):
    return _RUNNER(argv, cwd=cwd, timeout=timeout, capture_output=True)


def _get_run_allowlist() -> Set[str]:
    raw = os.environ.get("GLYPH_RUN_ALLOW", "").strip()
    if not raw:
        return set()
    allowed = set()
    for entry in raw.split(":"):
        entry = entry.strip()
        if entry and os.path.isabs(entry):
            allowed.add(os.path.realpath(entry))
    return allowed


def _get_fs_allow_roots() -> Set[str]:
    """0x13/0x03/0x04 SYSCALL host-FS containment (BK-15 + BK-44).

    GLYPH_FS_ALLOW: colon-separated absolute roots whose realpaths bound
    host-directory enumeration (0x13, BK-15), host-file writes (0x03)
    and host-file reads (0x04) — the latter two added by BK-44: BK-15's
    landing rationale ("enumeration is the more invasive primitive, it
    must not be cheaper to reach than RUN", :577-579) was measured
    INVERTED (probe_bk44_red_af3e, md5 7a268057e72bd67f7f00e8d9f301dc09,
    at HEAD 07eefcc2): under the identical empty env, 0x03 destroyed/
    overwrote host files and 0x04 exfiltrated host file CONTENT while
    0x13 was refused — the two strictly more invasive primitives were
    cheaper to reach than the one that only names files. Same containment
    model as 0x07/0x12's GLYPH_RUN_ALLOW (RULING precedent 97b7732d).
    Empty set = all three host-FS arms are refused everywhere
    (deny-by-default; a caller that never set the env must not get a
    free host-FS walk).
    """
    raw = os.environ.get("GLYPH_FS_ALLOW", "").strip()
    if not raw:
        return set()
    allowed = set()
    for entry in raw.split(":"):
        entry = entry.strip()
        if entry and os.path.isabs(entry):
            allowed.add(os.path.realpath(entry))
    return allowed


class GlyphCPUv2:
    """Fixed-width spatial CPU: PC.x always a multiple of INSTR_WIDTH."""

    def __init__(self, opcode_map: OpcodeMapV2, cols_instrs: int, fs_pix_enabled: bool = False):
        self.opcode_map = opcode_map
        self.cols_instrs = cols_instrs
        self.fs_pix_enabled = fs_pix_enabled
        # item-25 VFS-2: optional attached VFS backend. None (the default)
        # keeps every FILE syscall on the landed host path, byte-unchanged;
        # a GlyphVfs attached via attach() re-routes 0x03/0x04/0x13.
        self.vfs = None
        self.registers = [0] * 32
        self.memory = [0] * 1024
        self.pc = (0, 0)
        self.running = False
        self.output = []
        self.current_imm = 0  # Current instruction's immediate value (for syscalls)
        # xv6-nano isolation (E-K1). Inert until a program stores a nonzero
        # KFAULT_PC / MODE_LATCH into the reserved MMIO words -- every existing
        # image runs entirely in MODE_SUPER with no box check.
        self.mode = MODE_SUPER
        self.fault_addr = 0
        self.fault_pc = 0
        self.faulted = False
        self.fault_reason = None  # DEFECT-23: evidence string on ceiling faults (see :764)
        self.halt_reason = None  # None = normal HALT/EXIT; else names why running
        # went False with no fault set - the "silent halt" class (opcode-None
        # pixel, walk-off, trap fallthrough with no handler installed) that
        # cost the whole SE021 session (turn 2 stopped silently on an
        # opcode-None pixel; nothing distinguished it from a clean HALT until
        # someone read the code). Mirrors self.fault_reason's shape exactly.
        self._syscall_regs = None  # register-file snapshot across a SYSCALL->SYSRET trap
        self._tick_regs = None  # register-file snapshot across a tick (DEFECT-18, ruling 2026-09-12 option (a))
        self._tick_pc = None  # interrupted PC snapshot across a tick
        self._tile_confinement = False  # BK-38 / RULING_BK38_READ_POSTURE: armed on spawn(tile=...) only
        self._bk76_ever_user = False  # BK-76: engine has run USER instrs post-arm

    def _check_alignment(self, x: int):
        if x % INSTR_WIDTH != 0:
            raise SpatialMisalignmentFault(f"PC.x={x} is not aligned to {INSTR_WIDTH}")

    def _addr_to_xy(self, image: np.ndarray, addr: int) -> Tuple[int, int]:
        """Linear-wrap: scalar address -> pixel coordinate (scanline order)."""
        height, width, _ = image.shape
        addr %= width * height
        return addr % width, addr // width

    @staticmethod
    def _hilb_frame_pix_word(pfn_field: int, offset: int) -> int:
        """GH-25: packed 2D frame origin -> image pixel word via the verified
        Hacker's Delight xy2d curve (mirrors tools.geos_hilbert and the WGSL
        twin's hilb_frame_word; bitwise so both engines cannot drift)."""
        col = pfn_field & 0xFF
        row = (pfn_field >> 8) & 0xFF
        side = HILB_SIDE
        d = 0
        s = side >> 1
        x, y = col, row
        while s > 0:
            rx = 1 if (x & s) else 0
            ry = 1 if (y & s) else 0
            d += s * s * ((3 * rx) ^ ry)
            if ry == 0:
                if rx == 1:
                    x = side - 1 - x
                    y = side - 1 - y
                x, y = y, x
            s >>= 1
        return d * PAGE_WORDS + offset

    # --- GH-8b pixel-aliased FS window ------------------------------------
    # Word addresses in [1024, 1280) alias image pixels: 2 pixels per 32-bit
    # word (pixel W*2 = bits 23..0, pixel W*2+1 = bits 31..24), so kernel
    # LD/ST on FSTAB (1024..) / file data (1044..) mutate the SAVED ndarray
    # — the image is the disk, bit-exact through PNG round-trips. The zone
    # sits ABOVE all legacy RAM scratch (<1024: GH-2/3/5 mailboxes, status
    # words) and BELOW BOX MMIO (8192+), so GH-1..7 kernels are untouched.
    _FS_PIX_LO_WORD = 1024
    _FS_PIX_HI_WORD = 1280

    def _fs_pix_read(self, image: np.ndarray, word: int) -> int:
        h, w, _ = image.shape
        lin = (word * 2) % (w * h)
        x, y = lin % w, lin // w
        lo = (int(image[y, x][0]) << 16) | (int(image[y, x][1]) << 8) | int(image[y, x][2])
        lin2 = (word * 2 + 1) % (w * h)
        hi = int(image[lin2 // w, lin2 % w][2])
        return ((lo | (hi << 24)) & 0xFFFFFFFF)

    def _fs_pix_write(self, image: np.ndarray, word: int, value: int):
        h, w, _ = image.shape
        value &= 0xFFFFFFFF
        lin = (word * 2) % (w * h)
        image[lin // w, lin % w] = ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
        lin2 = (word * 2 + 1) % (w * h)
        image[lin2 // w, lin2 % w] = (0, 0, (value >> 24) & 0xFF)
        # write-through mirror: keeps legacy receipts (memory[] reads of
        # window words) coherent; the PIXELS remain the persisted truth --
        # on reboot memory[] is zero but the image still carries the data.
        if word < len(self.memory):
            self.memory[word] = value

    def _mem_read(self, image: np.ndarray, addr: int) -> int:
        if self.fs_pix_enabled and self._FS_PIX_LO_WORD <= addr < self._FS_PIX_HI_WORD:
            return self._fs_pix_read(image, addr)
        x, y = self._addr_to_xy(image, addr)
        r, g, b = image[y, x]
        return (int(r) << 16) | (int(g) << 8) | int(b)

    def _mem_write(self, image: np.ndarray, addr: int, value: int):
        if self.fs_pix_enabled and self._FS_PIX_LO_WORD <= addr < self._FS_PIX_HI_WORD:
            self._fs_pix_write(image, addr, value)
            return
        x, y = self._addr_to_xy(image, addr)
        value &= 0xFFFFFF
        image[y, x] = ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)

    _ISO_TOP_WORD = TILE_W_ADDR >> 2

    @property
    def _iso_enabled(self) -> bool:
        """The isolation MMIO block only exists when data memory is large
        enough to hold it (the xv6-nano harness sizes it to 16384 words).
        Smaller images -- the SHA-256 kernel, unit fixtures -- never see the
        box check or the mode latch."""
        return len(self.memory) > self._ISO_TOP_WORD

    def _addr_in_box(self, byte_addr: int) -> bool:
        """E-K1: is `byte_addr` inside either kernel-programmed range? An
        unset range (HI == 0) never matches, so a partially-configured box
        still confines. Word stores are checked at their base byte."""
        if not self._iso_enabled:
            return True
        lo0 = self.memory[BOX0_LO_ADDR >> 2]
        hi0 = self.memory[BOX0_HI_ADDR >> 2]
        lo1 = self.memory[BOX1_LO_ADDR >> 2]
        hi1 = self.memory[BOX1_HI_ADDR >> 2]
        lo2 = self.memory[BOX2_LO_ADDR >> 2]
        hi2 = self.memory[BOX2_HI_ADDR >> 2]
        if ((hi0 and lo0 <= byte_addr < hi0)
                or (hi1 and lo1 <= byte_addr < hi1)
                or (hi2 and lo2 <= byte_addr < hi2)):
            return True
        # GO-2: the 2D tile predicate. When a tile is armed (TILE_H != 0) the
        # permitted region also includes the rectangle [TILE_ROW, TILE_ROW +
        # TILE_H) x [TILE_COL, TILE_COL + TILE_W) in (row, col) grid
        # coordinates derived from the byte address (row = (addr >> 2) //
        # W_MEM, col = (addr >> 2) % W_MEM). An unset tile is inert.
        h = self.memory[TILE_H_ADDR >> 2]
        if h:
            w = self.memory[TILE_W_ADDR >> 2]
            trow = self.memory[TILE_ROW_ADDR >> 2]
            tcol = self.memory[TILE_COL_ADDR >> 2]
            word = byte_addr >> 2
            row, col = word // W_MEM, word % W_MEM
            if trow <= row < trow + h and tcol <= col < tcol + w:
                return True
        return False

    def _physical_in_tile(self, word_addr: int) -> bool:
        """BK-66 (DESIGN RULING 2026-09-28, commit 9714a363): the GO-2 tile
        predicate applied to a TRANSLATED physical word address — the paged
        arms' post-translation fence consult. A vaddr-side check is defeated
        by construction (the attacker owns the page table: BK-66 T1/T2 map
        in-tile vaddrs onto out-of-tile physical words), so the consult runs
        AFTER pfn decode and NO consult in the paged path ever sees a vaddr.
        An unset tile (TILE_H == 0) is inert — byte-identical legacy paging
        for unfenced tasks. Framed arms (PIX/HILB) pass their decoded image
        word; plain arms pass the RAM paddr. Same grid math as _addr_in_box's
        tile branch (row = word // W_MEM, col = word % W_MEM)."""
        h = self.memory[TILE_H_ADDR >> 2]
        if not h:
            return True
        w = self.memory[TILE_W_ADDR >> 2]
        trow = self.memory[TILE_ROW_ADDR >> 2]
        tcol = self.memory[TILE_COL_ADDR >> 2]
        row, col = word_addr // W_MEM, word_addr % W_MEM
        return trow <= row < trow + h and tcol <= col < tcol + w

    def _paged_paddr_fence_fault(self, phys_word: int, vaddr: int, op: str,
                                  x: int, y: int):
        """BK-66: the E-K1-shaped refusal for a paged access whose
        TRANSLATED physical target falls outside the armed tile. Mirrors the
        unpaged fence arms' fault discipline: record FAULT_ADDR (physical
        byte address — the address the fence judged) + FAULT_PC, drop to
        SUPER, and vector through KFAULT_PC with the BK-52 kf==0 guard
        (no handler installed -> stop loudly, never replay-and-land).
        Returns the vector target for the caller's next_pc."""
        self.fault_addr = (phys_word << 2) & 0xFFFFFFFF
        self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
        self.faulted = True
        self.fault_reason = (
            f"paged_paddr_fence op={op} paddr={phys_word} vaddr={vaddr << 2:#x} "
            f"mode=USER site=glyph_isa_v2"
        )
        if len(self.memory) > (FAULT_PC_ADDR >> 2):
            self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
            self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
        self.mode = MODE_SUPER
        kf = self.memory[KFAULT_PC_ADDR >> 2] if len(self.memory) > (KFAULT_PC_ADDR >> 2) else 0
        if kf != 0:
            tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
            target_x = tx * INSTR_WIDTH
            self._check_alignment(target_x)
            return (target_x, ty)
        self.running = False
        return None

    # BK-76 (RULING_BK76_EXEMPTION_POSTURE.md, Option A): the :968 SUPER
    # MMIO-window exemption short-circuits translation for the whole box
    # block, and research ticks 19-21 measured that a tile-confined task's
    # own text can SYSCALL into SUPER and re-write the DISPATCH VECTOR
    # words through it (KSYS chain [7,7,52,0], persistence 75 fires, E1
    # sentinel landing). The refusal is scoped to the VECTOR WORDS ONLY —
    # a block-wide refuse would break lawful post-USER SUPER handler
    # stores live gates pin (xv6-nano ISO_SYS_A0 word 8205, GH-16's
    # MODE_LATCH re-latch, GO-3's ISO_INPUT_CURSOR). Ruling invariant 2:
    # guest-seeded handlers have no lawful reason to mutate the vectors
    # dynamically during guest dispatch. Boot-phase config (GH-25 fault
    # image, GH-16/GH-6 kernels, loader seeding) happens BEFORE the first
    # USER instruction, so the _bk76_ever_user latch (set on the USER->SUPER
    # transition these attacks all require) leaves every landed image's
    # setup untouched. No vector is taken (tick-19's KFAULT restart loop:
    # 162 fires under fault-path refusal) — stop and stay stopped.
    _BK76_LOCKED_WORDS = frozenset({
        KFAULT_PC_ADDR >> 2, KSYS_PC_ADDR >> 2, KTICK_PC_ADDR >> 2})

    # BK-41 (DIRECTIVE_BK41_CONFIG_BLOCK.md, step 2 of BK-39's resolution):
    # the kernel-write-only BOX_MMIO CONFIG block, as measured at HEAD
    # 0f8d904e (probe_bk41_config_arms_af3e.py). The USER arms are already
    # closed (item-29's out-of-box ST + BK-39's write_arm_fence cover every
    # guest USER store; C1-C5 all refused pre-fix), so the surviving hole is
    # the :968 SUPER exemption arm — a post-SYSCALL handler (or any
    # post-USER SUPER code) can rewrite the CONFIG block (BOX ranges, timer
    # words, vectors) and land the store clean (C6/C7). The lock below
    # extends the BK-76 refusal from the three vector words to the whole
    # guest-defeatable config set. MEASURED SCOPE AMENDMENT (filed in
    # BK41_DESIGN_NOTES.md + the directive's receipt appendix): MODE_LATCH
    # (8192) and the TILE words (8280..8283) are EXCLUDED — the landed
    # xv6-nano S6/S11 schedulers re-arm them post-USER every context switch
    # (instrumented: S11 writes 8192 + 8280 from SUPER after tasks ran
    # USER, and the run only halts cleanly WITH those stores); locking them
    # would be a lawful write caught in the net (directive rule 4).
    # SYS_A0/A1 (8205/8206) and the INPUT ring (8237+) stay guest-writable
    # per BK-76 §0's boundary (xv6-nano syscall_dispatch writes ISO_SYS_A0).
    _BK41_LOCKED_WORDS = frozenset({
        KFAULT_PC_ADDR >> 2, KSYS_PC_ADDR >> 2, KTICK_PC_ADDR >> 2,
        BOX0_LO_ADDR >> 2, BOX0_HI_ADDR >> 2,
        BOX1_LO_ADDR >> 2, BOX1_HI_ADDR >> 2,
        BOX2_LO_ADDR >> 2, BOX2_HI_ADDR >> 2,
        TIMER_COUNT_ADDR >> 2, TIMER_RELOAD_ADDR >> 2})

    def _bk76_exemption_refuse(self, word_addr: int, val: int, x: int, y: int):
        """BK-76 Option A no-vector refusal: drop the store, fault, stop."""
        self.fault_addr = (word_addr << 2) & 0xFFFFFFFF
        self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
        self.faulted = True
        self.fault_reason = (
            f"mmio_exemption_refused word={word_addr} val={val:#x} "
            f"mode=SUPER site=glyph_isa_v2"
        )
        if len(self.memory) > (FAULT_PC_ADDR >> 2):
            self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
            self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
        self.mode = MODE_SUPER
        self.running = False  # NO vector: restart-loop immunity (tick-19)

    # BK-39 (oracle twin of the landed WGSL stack_fence_fault,
    # wgsl_glyph_isa_v2.py:625): the stack path (PUSH/POP/CALL/RET/CALLR)
    # touches memory through the IMAGE plane via _mem_write/_mem_read, and
    # PARALLEL_ST/PARALLEL_LD write/read self.memory with bounds checks
    # only — none of these consulted the E-K1 fence, so a tile-confined
    # USER task stored/read out-of-tile clean (probes probe_pst_fence_af3e
    # / probe_wgsl_stack_fence_af3e) and could self-grant BOX0. The
    # consult runs PER-OP on the exact word the operation touches — NOT
    # inside _mem_write/_mem_read: a shared-site consult would double-
    # fence the paged frame arms (BK-66's post-translation consult owns
    # the paged path) and would change every non-stack caller's semantics
    # (twin landing posture, wgsl_glyph_isa_v2.py:607-628). The judged
    # term is the SAME _addr_in_box (boxes + GO-2 tile) the ST arm uses;
    # SUPER is exempt (kernel KJMP/entry stacks untouched). Callers own
    # the E-K1 tail and consult BEFORE the pre-decrement/read so a
    # refused op mutates nothing.
    def _stack_fence_fault(self, word_addr: int, x: int, y: int, op: str):
        """E-K1 refusal for a USER fence-confined op touching `word_addr`.
        Records FAULT_ADDR/FAULT_PC, drops to SUPER, and vectors through
        KFAULT_PC with the BK-52 kf==0 guard (no handler -> stop loudly).
        Returns the vector target for the caller's next_pc, or None when
        stepping stops (kf == 0) — the _paged_paddr_fence_fault contract.
        The caller must NOT execute the operation when this fires."""
        if not self._iso_enabled or self.mode != MODE_USER:
            return None
        if not self._tile_confinement:
            return None
        if self._addr_in_box(word_addr << 2):
            return None
        self.fault_addr = (word_addr << 2) & 0xFFFFFFFF
        self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
        self.faulted = True
        self.fault_reason = (
            f"write_arm_fence op={op} word={word_addr} "
            f"addr={self.fault_addr:#x} mode=USER site=glyph_isa_v2"
        )
        if len(self.memory) > (FAULT_PC_ADDR >> 2):
            self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
            self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
        self.mode = MODE_SUPER
        kf = self.memory[KFAULT_PC_ADDR >> 2] if len(self.memory) > (KFAULT_PC_ADDR >> 2) else 0
        if kf != 0:
            # BK-52 guard parity: no kf==0 replay-and-land.
            tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
            target_x = tx * INSTR_WIDTH
            self._check_alignment(target_x)
            return (target_x, ty)
        self.running = False
        return None

    def _bk40_dest_fault(self, dest, length, kind: str):
        """BK-40: fence the syscall DATA handlers' dest windows.

        A tiled USER task's syscall handlers (0x02 READ, 0x04 FILE_READ,
        0x13 FILE_LIST, 0x11 STORE_CODE) copy bytes/words into guest RAM
        (or the image plane, 0x11) with bounds checks only — the fence
        never fires (probe_syscall_fence_af3e, md5 cee48c7b). Consult the
        dest window BEFORE the handler runs and refuse the WHOLE syscall
        through the SAME E-K1 tail _stack_fence_fault uses (fault_addr =
        word<<2, fault_pc packed, mode->SUPER, KFAULT_PC vector, kf==0
        stop): the handler never executes, nothing lands, no partial
        same term set as every landed consult: USER +
        _tile_confinement + _iso_enabled; the term is _addr_in_box
        (boxes + GO-2 tile). `dest`/`length` are WORD granular for ALL
        four handlers (each writes self.memory[dest+i], one byte per
        word — no byte packing anywhere in this class). Returns
        the vector target for the caller's next_pc, or None when no
        consult fires or stepping stopped (kf==0).
        """
        if not self._iso_enabled or self.mode != MODE_USER:
            return None
        if not self._tile_confinement:
            return None
        if length <= 0:
            return None
        # All four handlers write WORD-granular (self.memory[dest + i],
        # one byte/word per word — no byte packing). The window is words
        # [dest, dest + length); every word must be inside the fence
        # term, else refuse at the FIRST offending word (E-K1's "the op
        # is abandoned" discipline).
        for w in range(dest, dest + length):
            if not self._addr_in_box(w << 2):
                return self._stack_fence_fault(w, self.pc[0], self.pc[1],
                                               f"syscall_dest_fence:{kind}")
        return None

    def _bk42_source_fault(self, src, length, kind: str):
        """BK-42: fence a syscall's DATA SOURCE window (0x03 FILE_WRITE).

        Mirror of _bk40_dest_fault for the one handler that READS guest
        RAM and sinks it to the HOST (open(path,"wb"),
        glyph_isa_v2 _handle_syscall 0x03): the data loop crosses the
        fence with no consult — full exfil from a tiled USER task
        (probe_fw_exfil_af3e, md5 d7a9aa69). The window is WORD-granular
        (the handler reads self.memory[src+i], one byte per word —
        identical convention to the BK-40 dest windows); any
        out-of-fence word in [src, src+length) refuses the WHOLE syscall
        through the SAME E-K1 tail (_stack_fence_fault): handler never
        runs, no host file is created or touched. Same term set as every
        landed consult: USER + _tile_confinement + _iso_enabled, term
        _addr_in_box (boxes + GO-2 tile). Returns the vector target for
        the caller's next_pc, or None when no consult fires or stepping
        stopped (kf==0).
        """
        if not self._iso_enabled or self.mode != MODE_USER:
            return None
        if not self._tile_confinement:
            return None
        if length <= 0:
            return None
        for w in range(src, src + length):
            if not self._addr_in_box(w << 2):
                return self._stack_fence_fault(w, self.pc[0], self.pc[1],
                                               f"syscall_source_fence:{kind}")
        return None

    def _bk42_path_fault(self, path_addr: int, tag: str = "path_decode_fence"):
        """BK-42: fence the shared syscall PATH-argument decode.

        _read_path walks self.memory words until a NUL with no box check
        — the filename IS a fence-blind cross-fence READ channel: an
        unterminated in-tile path decodes into the NEIGHBOR's RAM and the
        out-of-tile bytes select the host path / executed binary
        (probe_fw_exfil_af3e leg 3; BK-43's RUN smuggle is the same
        channel). Walk the decode EXACTLY as _read_path will (same
        FS-pixel alias arm, same past-RAM break) and require every
        decoded byte to come from inside the fence term: the first
        out-of-box word — or an unterminated decode that crosses the
        tile boundary — refuses the WHOLE syscall via the E-K1 tail
        (reason tag `path_decode_fence`). A path fully staged in-tile
        with an in-tile NUL walks clean. Same term set as every landed
        consult. Returns the vector target or None (see
        _bk42_source_fault).

        POSTURE: the consult bounds the decode at 4096 words like the
        handler does, but the fence term fires at the tile boundary long
        before that ceiling matters for a confined task. Out-of-RAM
        break is mirrored from _read_path so the consult never refuses a
        path the handler itself would terminate early.
        """
        if not self._iso_enabled or self.mode != MODE_USER:
            return None
        if not self._tile_confinement:
            return None
        for i in range(4096):
            a = path_addr + i
            if self.fs_pix_enabled and self._FS_PIX_LO_WORD <= a < self._FS_PIX_HI_WORD:
                # FS-pixel aliased bytes: the handler reads them through
                # _fs_pix_read; image-plane terms are outside this
                # consult's RAM-fence scope (the BK-40 posture for 0x11's
                # image class judged word-wise on the dest; here the PATH
                # alias arm is admitted, matching the handler's read).
                return None
            if not (0 <= a < len(self.memory)):
                # Past RAM: _read_path treats this as terminator — the
                # decode never crossed the fence beyond RAM.
                return None
            if not self._addr_in_box(a << 2):
                return self._stack_fence_fault(a, self.pc[0], self.pc[1],
                                               tag)
            if (self.memory[a] & 0xFF) == 0:
                return None  # NUL inside the fence: clean decode
        # 4096 non-NUL words: _read_path would truncate here too — but
        # the walk crossed the fence to get there if we're still in it;
        # if the whole walk stayed in-box, admit (handler truncates the
        # same way).
        return None

    def _bk43_argv_fault(self, arg_addr: int):
        """BK-43: fence a 0x12 RUN2 ARGV-argument decode window.

        RUN2's argv args are documented "data, not targets"
        (glyph_isa_v2 RUN2 arm) — but "data" still crosses execve() to a
        HOST process: probe_run_arg_af3e measured an out-of-tile argv
        window landing verbatim in the child's argv (marker ARG1=[SRC5],
        md5 e238a3ab) — out-of-tile RAM exfiltrated through the process
        boundary with no consult. The PATH target (r1) is already fenced
        by _bk42_path_fault (0x07/0x12 in _BK42_PATH_SYSCALLS), so the
        smuggle channel is dead; this consult owns the ARGV windows.

        Walk the decode EXACTLY as _read_path will (same FS-pixel alias
        arm admitted, same past-RAM break, same 4096 ceiling) and require
        every decoded byte to come from inside the fence term: the first
        out-of-fence word refuses the WHOLE syscall via the E-K1 tail
        (reason tag `argv_decode_fence`). addr == 0 ("no argument") is
        admitted — RUN2's documented none-sentinel. Same term set as
        every landed consult: USER + _tile_confinement + _iso_enabled;
        SUPER (E-K2 dispatch) and unfenced tasks untouched. Returns the
        vector target or None (see _bk42_source_fault).
        """
        if arg_addr == 0:
            return None
        return self._bk42_path_fault(arg_addr, tag="argv_decode_fence")

    def step(self, image: np.ndarray) -> bool:
        was_user = (self.mode == MODE_USER)
        # BK-76: the ever-user latch. Every measured :968 exemption attack
        # shape requires the engine to have executed USER instructions
        # after tile arming (SYSCALL into SUPER, or a tick preemption).
        # Boot/config-phase vector writes all happen pre-first-USER, so
        # latching here keeps them lawful while post-USER vector stores
        # become refuse-able. One-way; cheap; reset only by a fresh engine.
        if was_user and self._tile_confinement:
            self._bk76_ever_user = True
        x, y = self.pc
        self._check_alignment(x)
        height, width, _ = image.shape
        if y >= height or x >= width:
            self.halt_reason = f"walk-off: PC ({x},{y}) is outside the {width}x{height} image"
            self.running = False
            return False

        opcode_px = tuple(image[y, x])
        reg_px = tuple(image[y, x + 1])
        low_px = tuple(image[y, x + 2])
        high_px = tuple(image[y, x + 3])

        opcode = self.opcode_map.rgb_to_opcode(opcode_px)
        if opcode is None:
            self.halt_reason = f"opcode-None pixel at ({x},{y}): rgb={opcode_px} is not a known opcode color"
            self.running = False
            return False

        rs1, rs2, rd = reg_px
        imm = _unpack_immediate(low_px, high_px)
        self.current_imm = imm  # Store for syscalls that need it

        # Fall-through PC advance wraps to the next row at the instruction-row
        # width, mirroring GlyphAssemblerV2's row-major layout. Only explicit
        # JMP/JZ/CALL carry an absolute (col,row) target; without this wrap,
        # straight-line code that crosses a row boundary walks off the array.
        row_width_px = self.cols_instrs * INSTR_WIDTH
        next_x = x + INSTR_WIDTH
        if next_x >= row_width_px:
            next_pc = (0, y + 1)
        else:
            next_pc = (next_x, y)

        if opcode == 'LDI':
            self.registers[rd] = imm & 0xFFFFFFFF
        elif opcode == 'ADD':
            self.registers[rd] = (self.registers[rd] + self.registers[rs2]) & 0xFFFFFFFF
        elif opcode == 'SUB':
            self.registers[rd] = (self.registers[rd] - self.registers[rs2]) & 0xFFFFFFFF
        elif opcode == 'MUL':
            # SE023: 32-bit wrapped multiply, matching ADD/SUB wrap semantics.
            self.registers[rd] = (self.registers[rd] * self.registers[rs2]) & 0xFFFFFFFF
        elif opcode == 'AND':
            self.registers[rd] &= self.registers[rs2]
        elif opcode == 'OR':
            self.registers[rd] |= self.registers[rs2]
        elif opcode == 'XOR':
            self.registers[rd] ^= self.registers[rs2]
        elif opcode == 'SHL':
            # RISC-V-faithful: shift amount is taken mod 32 (sll/srl/sra use
            # rs2[4:0]); results wrap at 32 bits. Without the mod, Python's
            # unbounded ints make 1 << N a multi-million-digit bomb.
            self.registers[rd] = (self.registers[rd] << (self.registers[rs2] & 31)) & 0xFFFFFFFF
        elif opcode == 'SHR':
            self.registers[rd] = (self.registers[rd] & 0xFFFFFFFF) >> (self.registers[rs2] & 31)
        elif opcode == 'ROTR':
            # 32-bit rotate-right: rd = rotr32(rd, rs2 & 31)
            n = self.registers[rs2] & 31
            v = self.registers[rd] & 0xFFFFFFFF
            self.registers[rd] = ((v >> n) | (v << (32 - n))) & 0xFFFFFFFF if n else v
        elif opcode == 'CMP':
            self.registers[0] = 1 if self.registers[rd] == self.registers[rs2] else 0
        elif opcode == 'CMP3':
            # SE025: tri-state compare — r0 = 0 (rd < rs2, SIGNED) / 1 (equal)
            # / 2 (rd > rs2). Signed to be blt-faithful; the 32-bit wrap first
            # matches the engine's other arithmetic (SHL/SHR wrap at
            # 0xFFFFFFFF), so 0xFFFFFFFF compares as -1. CMP itself is
            # untouched: legacy JZ/JNZ/JNE keep pure-boolean semantics.
            a = self.registers[rd] & 0xFFFFFFFF
            b = self.registers[rs2] & 0xFFFFFFFF
            sa = a - (1 << 32) if a & 0x80000000 else a
            sb = b - (1 << 32) if b & 0x80000000 else b
            self.registers[0] = 1 if sa == sb else (0 if sa < sb else 2)
        elif opcode == 'LD':
            # LD/ST address the 32-bit word-array RAM (self.memory) — the
            # storage the SHA-256 kernel seeds K/W tables into. The pixel
            # image is program ROM; PUSH/POP/CALL/RET stack via _mem_*.
            # GH-8b: FS-window words (780..1023) alias image pixels instead,
            # so kernel FS stores mutate the saved ndarray (image = disk).
            # GH-17: Spatial Paging translations when PAGE_TABLE_ADDR != 0.
            addr = self.registers[rs2]
            pt_base = self.memory[PAGE_TABLE_ADDR >> 2] if len(self.memory) > (PAGE_TABLE_ADDR >> 2) else 0
            if pt_base != 0 and not (self.mode == MODE_SUPER and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256):
                vaddr = addr
                vpn = (vaddr >> 8) & 0xFF
                offset = vaddr & 0xFF
                pte_idx = pt_base + vpn
                tag_ok, tag_val, tag_reason = check_pt_tag(self, image, pt_base)
                if not tag_ok:
                    self.fault_addr = (vaddr << 2) & 0xFFFFFFFF
                    self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                    self.faulted = True
                    self.fault_reason = tag_reason
                    if len(self.memory) > (FAULT_PC_ADDR >> 2):
                        self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                        self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                    self.mode = MODE_SUPER
                    kf = self.memory[KFAULT_PC_ADDR >> 2] if len(self.memory) > (KFAULT_PC_ADDR >> 2) else 0
                    if kf != 0:
                        tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
                        target_x = tx * INSTR_WIDTH
                        self._check_alignment(target_x)
                        next_pc = (target_x, ty)
                    else:
                        self.running = False
                        return False
                else:
                    # GH-25 (RCA systems/GH25_WIP_PTE_FETCH_RCA.md): RAM is the
                    # LIVE table; image is fallback when RAM PTE == 0 (the GH-25
                    # harness stamps its Hilbert PTE into image pixels only).
                    # RAM-first ordering keeps bake-time text garbage under the
                    # PT window from shadowing valid RAM PTEs.
                    pte = 0
                    if 0 <= vaddr < 65536 and pte_idx < len(self.memory):
                        pte = self.memory[pte_idx]
                        if pte == 0:
                            h_img, w_img, _ = image.shape
                            if pte_idx < w_img * h_img:
                                pte = self._mem_read(image, pte_idx)
                    if (not (pte & PTE_V)) or (self.mode == MODE_USER and not (pte & PTE_U)):
                        self.fault_addr = (vaddr << 2) & 0xFFFFFFFF
                        self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                        self.faulted = True
                        # 5-site classification pass: this branch used to
                        # leave fault_reason None despite faulted=True (only
                        # the tag-mismatch sibling above named itself) -
                        # naming it the same way, not changing when it fires.
                        self.fault_reason = (
                            f"pte_invalid pte={pte:#x} vaddr={vaddr<<2:#x} "
                            f"mode={'USER' if self.mode == MODE_USER else 'SUPER'} "
                            f"op=LD site=glyph_isa_v2"
                        )
                        if len(self.memory) > (FAULT_PC_ADDR >> 2):
                            self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                            self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                        self.mode = MODE_SUPER
                        kf = self.memory[KFAULT_PC_ADDR >> 2] if len(self.memory) > (KFAULT_PC_ADDR >> 2) else 0
                        if kf != 0:
                            tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
                            target_x = tx * INSTR_WIDTH
                            self._check_alignment(target_x)
                            next_pc = (target_x, ty)
                        else:
                            self.running = False
                            return False
                    else:
                        pfn = pte >> 8
                        if pte & PTE_HILB:
                            # GH-25: pfn field = packed 2D frame origin (row<<8|col)
                            # on a HILB_SIDE x HILB_SIDE frame grid; the frame word
                            # is xy2d(col,row)*PAGE_WORDS + offset (intra-frame
                            # offset stays LINEAR). Bit-exact with the WGSL twin.
                            pix_word = self._hilb_frame_pix_word(pfn, offset)
                            # BK-66 paddr fence (DESIGN RULING 9714a363): consult
                            # runs POST-TRANSLATION on the decoded frame word —
                            # never the vaddr (attacker-owned page table).
                            if (self.mode == MODE_USER and self._tile_confinement
                                    and not self._physical_in_tile(pix_word)):
                                vec = self._paged_paddr_fence_fault(
                                    pix_word, vaddr, "LD", x, y)
                                if vec is None:
                                    return False
                                next_pc = vec
                            else:
                                self.registers[rd] = self._mem_read(image, pix_word)
                        elif pte & PTE_PIX:
                            pix_word = pfn * PAGE_WORDS + offset
                            # BK-66 paddr fence: same post-translation consult.
                            if (self.mode == MODE_USER and self._tile_confinement
                                    and not self._physical_in_tile(pix_word)):
                                vec = self._paged_paddr_fence_fault(
                                    pix_word, vaddr, "LD", x, y)
                                if vec is None:
                                    return False
                                next_pc = vec
                            else:
                                self.registers[rd] = self._mem_read(image, pix_word)
                        else:
                            paddr = pfn * PAGE_WORDS + offset
                            # BK-66 paddr fence: plain-RAM arm.
                            if (self.mode == MODE_USER and self._tile_confinement
                                    and not self._physical_in_tile(paddr)
                                    and paddr < len(self.memory)):
                                vec = self._paged_paddr_fence_fault(
                                    paddr, vaddr, "LD", x, y)
                                if vec is None:
                                    return False
                                next_pc = vec
                            elif paddr < len(self.memory):
                                self.registers[rd] = self.memory[paddr] & 0xFFFFFFFF
                            else:
                                self.registers[rd] = 0
            elif self._iso_enabled and self.mode == MODE_USER and (
                    (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256
                    and addr in self._BK41_LOCKED_WORDS):
                # BK-56: the CONFIG-block READ posture, oracle arm (directive
                # §2 L4: research D3 showed oracle parity on the LEAK; the
                # gated posture was decided, so the oracle gains the symmetric
                # read gate — refusal-parity, not documented-leak parity).
                # USER LD of a BK-41 locked config word: rd NOT written,
                # fault_reason mmio_config_read_refused, fault_addr = word<<2,
                # mode -> SUPER, stop, NO vector (BK-75 KFC-L6 — the read
                # channel has no fault path to ride; vectoring would itself
                # leak the fault PC, research finding 6). Scope = the SAME
                # _BK41_LOCKED_WORDS set as the write lock (MODE_LATCH and
                # TILE words stay OUT by BK-41's measured scope amendment);
                # SYS_A0/A1 + INPUT ring keep the silent-0 posture below
                # (BK-76 §0 boundary — data words stay guest-readable).
                # Order matters: this elif sits BEFORE the tile-confinement
                # arm so a locked word inside an armed tile still refuses as
                # a CONFIG read (the write side's BK-41 consult is likewise
                # fence-armed, not tile-only — BK-77's box_confirmed parity).
                self.fault_addr = (addr << 2) & 0xFFFFFFFF
                self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                self.faulted = True
                self.fault_reason = (
                    f"mmio_config_read_refused word={addr} "
                    f"addr={self.fault_addr:#x} mode=USER site=glyph_isa_v2")
                self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                self.mode = MODE_SUPER
                self.running = False  # NO vector (BK-75 KFC-L6)
                return False
            elif self.mode == MODE_USER and self._tile_confinement:
                # GO-2 tile confinement on the LD side (RULING_BK38_READ_POSTURE Option 2):
                # When a 2D tile is armed via spawn(tile=...), out-of-tile reads trap with E-K1.
                # In the cooperative single-address-space kernel (xv6-nano), TILE_H == 0 or
                # general USER LD remains unfenced (reads are intentionally shared).
                h = self.memory[TILE_H_ADDR >> 2]
                w = self.memory[TILE_W_ADDR >> 2]
                trow = self.memory[TILE_ROW_ADDR >> 2]
                tcol = self.memory[TILE_COL_ADDR >> 2]
                row = addr // W_MEM
                col = addr % W_MEM
                in_tile = (trow <= row < trow + h) and (tcol <= col < tcol + w)
                if not in_tile:
                    self.fault_addr = (addr << 2) & 0xFFFFFFFF
                    self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                    self.faulted = True
                    self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                    self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                    self.mode = MODE_SUPER
                    kf = self.memory[KFAULT_PC_ADDR >> 2]
                    tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
                    target_x = tx * INSTR_WIDTH
                    self._check_alignment(target_x)
                    next_pc = (target_x, ty)
                else:
                    if 0 <= addr < len(self.memory):
                        self.registers[rd] = self.memory[addr] & 0xFFFFFFFF
                    elif addr >= 0:
                        self.registers[rd] = self._mem_read(image, addr)
            elif self.mode == MODE_USER and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256:
                # BK-56 / RULING_BK38_READ_POSTURE: MMIO config block is kernel/SUPER-only.
                # USER reads return 0 (oracle parity with WGSL walk_ld: returns 0u).
                self.registers[rd] = 0
            elif self.fs_pix_enabled and self._FS_PIX_LO_WORD <= addr < self._FS_PIX_HI_WORD:
                self.registers[rd] = self._fs_pix_read(image, addr)
            elif 0 <= addr < len(self.memory):
                self.registers[rd] = self.memory[addr] & 0xFFFFFFFF
            elif addr >= 0:
                # ENG-3 (BK-6 receipt): out-of-RAM unpaged LD previously fell
                # through SILENTLY (rd kept its stale value) — the ENG-1
                # silent-no-op class. _addr_to_xy documents linear-wrap
                # semantics and the paged PTE_PIX fallback already reads
                # through _mem_read, so wrap onto image pixels instead.
                self.registers[rd] = self._mem_read(image, addr)
        elif opcode == 'ST':
            # ST <addr_reg> <value_reg>: address in rs1, matching the
            # assembler's rs1/rs2 packing for ST. `addr` is a word index --
            # the byte_to_word_mem transpiler lowering already did `>>2`.
            addr = self.registers[rs1]
            val = self.registers[rs2]
            pt_base = self.memory[PAGE_TABLE_ADDR >> 2] if len(self.memory) > (PAGE_TABLE_ADDR >> 2) else 0
            # BK-76 Option A (RULING_BK76_EXEMPTION_POSTURE.md): the :968
            # SUPER MMIO-window exemption path. SUPER stores are never
            # box-checked (the E-K1 fence arms are USER-only) and the tile
            # consults are USER-only, so a post-USER SUPER store to a
            # dispatch vector word lands unconditionally — the exemption
            # hole measured in ticks 19-21. Scope: tile-confined engines,
            # after the engine has executed USER instructions post-arm
            # (boot-phase config untouched), window addresses, vector
            # words only. Refuse: no vector (tick-19 restart loop), stop.
            if (self._bk76_ever_user
                    and self.mode == MODE_SUPER and self._tile_confinement
                    and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256
                    and (addr in self._BK76_LOCKED_WORDS
                         or addr in self._BK41_LOCKED_WORDS)):
                self._bk76_exemption_refuse(addr, val, x, y)
                return False
            if pt_base != 0 and not (self.mode == MODE_SUPER and (BOX_MMIO_BASE >> 2) <= addr < (BOX_MMIO_BASE >> 2) + 256):
                vaddr = addr
                vpn = (vaddr >> 8) & 0xFF
                offset = vaddr & 0xFF
                pte_idx = pt_base + vpn
                tag_ok, tag_val, tag_reason = check_pt_tag(self, image, pt_base)
                if not tag_ok:
                    self.fault_addr = (vaddr << 2) & 0xFFFFFFFF
                    self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                    self.faulted = True
                    self.fault_reason = tag_reason
                    if len(self.memory) > (FAULT_PC_ADDR >> 2):
                        self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                        self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                    self.mode = MODE_SUPER
                    kf = self.memory[KFAULT_PC_ADDR >> 2] if len(self.memory) > (KFAULT_PC_ADDR >> 2) else 0
                    if kf != 0:
                        tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
                        target_x = tx * INSTR_WIDTH
                        self._check_alignment(target_x)
                        next_pc = (target_x, ty)
                    else:
                        self.running = False
                        return False
                else:
                    # GH-25: RAM-first, image-fallback (see the LD twin above).
                    pte = 0
                    if 0 <= vaddr < 65536 and pte_idx < len(self.memory):
                        pte = self.memory[pte_idx]
                        if pte == 0:
                            h_img, w_img, _ = image.shape
                            if pte_idx < w_img * h_img:
                                pte = self._mem_read(image, pte_idx)
                    if (not (pte & PTE_V)) or (not (pte & PTE_W)) or (self.mode == MODE_USER and not (pte & PTE_U)):
                        self.fault_addr = (vaddr << 2) & 0xFFFFFFFF
                        self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                        self.faulted = True
                        # 5-site classification pass: ST's twin of the LD
                        # pte_invalid fix above - same pre-existing gap.
                        self.fault_reason = (
                            f"pte_invalid pte={pte:#x} vaddr={vaddr<<2:#x} "
                            f"mode={'USER' if self.mode == MODE_USER else 'SUPER'} "
                            f"op=ST site=glyph_isa_v2"
                        )
                        if len(self.memory) > (FAULT_PC_ADDR >> 2):
                            self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                            self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                        self.mode = MODE_SUPER
                        kf = self.memory[KFAULT_PC_ADDR >> 2] if len(self.memory) > (KFAULT_PC_ADDR >> 2) else 0
                        if kf != 0:
                            tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
                            target_x = tx * INSTR_WIDTH
                            self._check_alignment(target_x)
                            next_pc = (target_x, ty)
                        else:
                            self.running = False
                            return False
                    else:
                        pfn = pte >> 8
                        if pte & PTE_HILB:
                            # GH-25: pfn field = packed 2D frame origin (row<<8|col);
                            # the frame word is xy2d(col,row)*PAGE_WORDS + offset
                            # (intra-frame offset stays LINEAR). Bit-exact with the
                            # WGSL twin.
                            pix_word = self._hilb_frame_pix_word(pfn, offset)
                            # BK-66 paddr fence (DESIGN RULING 9714a363): consult
                            # runs POST-TRANSLATION on the decoded frame word —
                            # never the vaddr (attacker-owned page table).
                            if (self.mode == MODE_USER and self._tile_confinement
                                    and not self._physical_in_tile(pix_word)):
                                vec = self._paged_paddr_fence_fault(
                                    pix_word, vaddr, "ST", x, y)
                                if vec is None:
                                    return False
                                next_pc = vec
                            else:
                                self._mem_write(image, pix_word, val)
                        elif pte & PTE_PIX:
                            pix_word = pfn * PAGE_WORDS + offset
                            # BK-66 paddr fence: same post-translation consult.
                            if (self.mode == MODE_USER and self._tile_confinement
                                    and not self._physical_in_tile(pix_word)):
                                vec = self._paged_paddr_fence_fault(
                                    pix_word, vaddr, "ST", x, y)
                                if vec is None:
                                    return False
                                next_pc = vec
                            else:
                                self._mem_write(image, pix_word, val)
                        else:
                            paddr = pfn * PAGE_WORDS + offset
                            do_store = True
                            # BK-66 paddr fence: plain-RAM arm — checked BEFORE
                            # the DEFECT-23 ceiling arm so a fenced out-of-tile
                            # store is refused as a FENCE fault (E-K1 family),
                            # not silently absorbed by ceiling/extend logic.
                            if (self.mode == MODE_USER and self._tile_confinement
                                    and not self._physical_in_tile(paddr)):
                                vec = self._paged_paddr_fence_fault(
                                    paddr, vaddr, "ST", x, y)
                                if vec is None:
                                    return False
                                next_pc = vec
                                do_store = False
                            elif paddr >= len(self.memory):
                                # DEFECT-23 containment (RULING_defect23_pfn_ceiling.md;
                                # ceiling value seat-confirmed by Jericho, f217992): an
                                # accidental PTE decode must not materialise unbounded RAM.
                                # 65536 pfn = 64 MiB — 2.6x below the smallest observed bad
                                # decode (pfn 67,593) and 34x below the 2295 MB runaway.
                                # Reuses the EXISTING fault path/semantics (no new fault
                                # vocabulary); evidence carried in fault_reason. Containment
                                # only — the low-byte PTE misread (root cause) is untouched.
                                if pfn > 65536:
                                    self.fault_addr = (vaddr << 2) & 0xFFFFFFFF
                                    self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                                    self.faulted = True
                                    self.fault_reason = (
                                        f"pfn={pfn} ceiling=65536 pte={pte:#x} "
                                        f"addr={self.fault_addr:#x} site=glyph_isa_v2:764"
                                    )
                                    if len(self.memory) > (FAULT_PC_ADDR >> 2):
                                        self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                                        self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                                    self.mode = MODE_SUPER
                                    kf = self.memory[KFAULT_PC_ADDR >> 2] if len(self.memory) > (KFAULT_PC_ADDR >> 2) else 0
                                    if kf != 0:
                                        tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
                                        target_x = tx * INSTR_WIDTH
                                        self._check_alignment(target_x)
                                        next_pc = (target_x, ty)
                                    else:
                                        self.running = False
                                        return False
                                    do_store = False  # the faulting store is abandoned (mirrors the PTE-fault path above)
                                else:
                                    self.memory.extend([0] * (paddr + PAGE_WORDS - len(self.memory)))
                            if do_store:
                                self.memory[paddr] = val & 0xFFFFFFFF
            elif self.mode == MODE_USER and not self._addr_in_box(addr << 2):
                # E-K1 trap: an out-of-box user store. Record the fault, do
                # NOT perform the store, drop to SUPER and vector to the
                # kernel fault handler (KFAULT_PC, packed pixel PC). Stepping
                # continues -- the kernel reaps the offending proc.
                self.fault_addr = (addr << 2) & 0xFFFFFFFF
                self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                self.faulted = True
                self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                self.mode = MODE_SUPER
                kf = self.memory[KFAULT_PC_ADDR >> 2]
                if kf != 0:
                    # BK-52: guard parity with the WGSL twin (walk_st's E-K1
                    # arm). kf == 0 means NO handler installed: stop loudly
                    # instead of vectoring to pixel (0,0) and replaying the
                    # program from entry in SUPER (the replay-and-land bug —
                    # the "refused" store lands on the SUPER replay).
                    tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
                    target_x = tx * INSTR_WIDTH
                    self._check_alignment(target_x)
                    next_pc = (target_x, ty)
                else:
                    self.running = False
            elif self.fs_pix_enabled and self._FS_PIX_LO_WORD <= addr < self._FS_PIX_HI_WORD:
                # GH-8b: kernel (SUPER-mode) FS stores land in image pixels.
                self._fs_pix_write(image, addr, self.registers[rs2])
            elif 0 <= addr < len(self.memory):
                self.memory[addr] = self.registers[rs2] & 0xFFFFFFFF
            else:
                # Lever #2: out-of-bounds store -- addr < 0 or
                # addr >= len(self.memory). Previously silent-dropped, which
                # let a bad pointer / buffer overrun report "clean execution
                # to HALT" while leaving state unwritten. Now an explicit
                # fault, bounds checked against the *actual* RAM size (not a
                # hardcoded ceiling), so the isolation harness's 16384-word
                # image and the 1024-word unit fixtures are each judged
                # against their own len(self.memory).
                self.fault_addr = (addr << 2) & 0xFFFFFFFF
                self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)  # BUG A: col units
                self.faulted = True
                if self.mode == MODE_USER and self._iso_enabled:
                    # In USER mode an in-box address that still lands past RAM
                    # is a misconfigured box: reuse the E-K1 kernel vector so
                    # the kernel reaps the offending proc and stepping goes on.
                    self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                    self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                    self.mode = MODE_SUPER
                    kf = self.memory[KFAULT_PC_ADDR >> 2]
                    if kf != 0:
                        # BK-52: sibling vector site — same no-handler guard
                        # as the E-K1 ST arm above (kf==0 must stop, not
                        # vector to (0,0) and replay in SUPER).
                        tx, ty = kf & 0xFFFF, (kf >> 16) & 0xFFFF
                        target_x = tx * INSTR_WIDTH
                        self._check_alignment(target_x)
                        next_pc = (target_x, ty)
                    else:
                        # Standalone / kernel mode: stop immediately and loudly.
                        # Callers must treat `faulted` as distinct from a clean
                        # HALT (see run_generated).
                        self.running = False
        elif opcode == 'PUSH':
            # BK-39: consult BEFORE the pre-decrement — a refused op
            # mutates nothing (twin posture, wgsl_glyph_isa_v2.py:607-628).
            vec = self._stack_fence_fault(
                self.registers[31] - 1, x, y, "PUSH")
            if vec is not None:
                next_pc = vec
            elif not self.running:
                return False  # kf==0 stop: halt loudly, no mutation
            else:
                self.registers[31] -= 1
                self._mem_write(image, self.registers[31], self.registers[rd])
        elif opcode == 'POP':
            vec = self._stack_fence_fault(self.registers[31], x, y, "POP")
            if vec is not None:
                next_pc = vec
            elif not self.running:
                return False
            else:
                self.registers[rd] = self._mem_read(image, self.registers[31])
                self.registers[31] += 1
        elif opcode == 'PRT':
            val = self.registers[rd]
            self.output.append(val)
            print(f"OUTPUT: r{rd} = {val}")
        elif opcode == 'CALL':
            # BK-39: consult the return-address stack word BEFORE the
            # pre-decrement (refused call mutates nothing).
            vec = self._stack_fence_fault(
                self.registers[31] - 1, x, y, "CALL")
            if vec is not None:
                next_pc = vec
            elif not self.running:
                return False
            else:
                self.registers[31] -= 1
                packed_pc = (next_pc[1] << 16) | (next_pc[0] & 0xFFFF)
                self._mem_write(image, self.registers[31], packed_pc)

                tx, ty = imm & 0xFFFF, (imm >> 16) & 0xFFFF
                target_x = tx * INSTR_WIDTH
                self._check_alignment(target_x)
                next_pc = (target_x, ty)
        elif opcode == 'RET':
            # Pop packed_pc from stack and jump. A zero return address means
            # "return from the outermost _start": halt instead of wrapping to
            # glyph address 0 and re-running the program forever. (Caught by
            # the rv64i_to_glyph negative-offset differential test: GCC's
            # _start tail-calls ret with an empty call stack.)
            # BK-39: consult BEFORE the read and post-increment.
            vec = self._stack_fence_fault(self.registers[31], x, y, "RET")
            if vec is not None:
                next_pc = vec
            elif not self.running:
                return False
            else:
                packed_pc = self._mem_read(image, self.registers[31])
                if packed_pc == 0:
                    self.running = False
                    next_pc = self.pc
                else:
                    self.registers[31] += 1
                    tx, ty = packed_pc & 0xFFFF, (packed_pc >> 16) & 0xFFFF
                    next_pc = (tx, ty)
        elif opcode == 'SYSCALL':
            # Invoke hypervisor syscall - number in immediate, result in rd.
            # syscall_num IS imm (that's how SYSCALL is encoded), so it's not
            # passed again separately - self.current_imm (set above) already
            # gives handlers access to it without changing this call's arity,
            # which would break every existing bridge_handle(syscall_num, image)
            # monkey-patch in spatial_hypervisor_bridge.py.
            ksys = self.memory[KSYS_PC_ADDR >> 2] if self._iso_enabled else 0
            if ksys:
                # E-K2: trap to the kernel's SUPER-mode syscall dispatcher.
                # Marshal a7/a0/a1 (RV -> glyph regs r17/r10/r11) into the
                # reserved words the C dispatcher reads; save the resume PC;
                # drop to SUPER; jump KSYS_PC (loader-seeded, packed pixel
                # PC). SYSRET (mret) returns. See XV6_NANO_ISOLATION_ROADMAP.
                # The dispatcher is a plain C function -- it clobbers
                # caller-saved regs the task expects to survive the (inlined)
                # `ebreak`. A real trap saves the register file; so do we.
                self._syscall_regs = self.registers[:]
                self.memory[SYS_N_ADDR >> 2] = self.registers[17] & 0xFFFFFFFF
                self.memory[SYS_A0_ADDR >> 2] = self.registers[10] & 0xFFFFFFFF
                self.memory[SYS_A1_ADDR >> 2] = self.registers[11] & 0xFFFFFFFF
                # Save the resume point as (row << 16) | col -- the same
                # packing KJMP/JMPR targets use, so SYSRET recovers it with
                # `col * INSTR_WIDTH`.
                self.memory[SYSCALL_PC_ADDR >> 2] = (
                    (next_pc[1] << 16) | ((next_pc[0] // INSTR_WIDTH) & 0xFFFF))
                self.mode = MODE_SUPER
                tx, ty = ksys & 0xFFFF, (ksys >> 16) & 0xFFFF
                target_x = tx * INSTR_WIDTH
                self._check_alignment(target_x)
                next_pc = (target_x, ty)
            else:
                syscall_num = imm
                # BK-40: fence the DATA handlers' dest windows BEFORE the
                # handler runs. All four handlers write WORD-granular
                # (self.memory[dest+i] — one byte per word), so dest/count
                # are WORD units everywhere (read at consult time from the
                # register file): 0x02 r1=dest, r2=count; 0x04 r2=dest,
                # r3=max; 0x13 r2=dest, r3=max; 0x11 r1=dest, r3=count
                # (image plane). Any out-of-fence word in the window
                # refuses the WHOLE syscall (E-K1 tail via
                # _stack_fence_fault: handler never runs, nothing lands).
                # Path/arg decode (r1 for 0x03/0x04/0x07/0x12/0x13) is the
                # BK-42/43 shared-decoder consult — separate row, NOT
                # fenced here. Source windows (0x01 WRITE, 0x03 data) are
                # reads, out of BK-40's write-arm scope.
                if self._tile_confinement and self._iso_enabled \
                        and self.mode == MODE_USER:
                    # BK-40: fence the DATA handlers' dest windows BEFORE the
                    # handler runs. All four handlers write WORD-granular
                    # (self.memory[dest+i] — one byte per word), so dest/count
                    # are WORD units everywhere (read at consult time from the
                    # register file): 0x02 r1=dest, r2=count; 0x04 r2=dest,
                    # r3=max; 0x13 r2=dest, r3=max; 0x11 r1=dest, r3=count
                    # (image plane). Any out-of-fence word in the window
                    # refuses the WHOLE syscall (E-K1 tail via
                    # _stack_fence_fault: handler never runs, nothing lands).
                    # BK-42: fence the PATH argument decode for every
                    # path-taking syscall (0x03/0x04/0x07/0x08/0x09/0x12/0x13
                    # — _read_path is shared and fence-blind, the filename is
                    # a cross-fence read channel), plus 0x03 FILE_WRITE's
                    # DATA SOURCE window (the handler reads guest RAM and
                    # sinks it to the HOST). Same refusal tail: handler never
                    # runs, nothing lands host-side or guest-side.
                    vec = None
                    dest_specs = {
                        0x02: (self.registers[1], self.registers[2], "read"),
                        0x04: (self.registers[2], self.registers[3], "file_read"),
                        0x13: (self.registers[2], self.registers[3], "file_list"),
                        0x11: (self.registers[1], self.registers[3],
                               "store_code"),
                    }
                    spec = dest_specs.get(syscall_num)
                    if spec is not None:
                        vec = self._bk40_dest_fault(spec[0], spec[1], spec[2])
                    if vec is None and syscall_num in _BK42_PATH_SYSCALLS:
                        vec = self._bk42_path_fault(self.registers[1])
                    if vec is None and syscall_num == 0x03:
                        vec = self._bk42_source_fault(
                            self.registers[2], self.registers[3], "file_write")
                    # BK-43: 0x12 RUN2's ARGV windows (r2=arg1_addr,
                    # r3=arg2_addr) are _read_path decodes too — "data,
                    # not targets" still crosses execve() host-side
                    # (probe_run_arg_af3e: out-of-tile ARG1 landed in the
                    # child's argv). Same walk, same refusal tail.
                    if vec is None and syscall_num == 0x12:
                        vec = self._bk43_argv_fault(self.registers[2])
                        if vec is None:
                            vec = self._bk43_argv_fault(self.registers[3])
                    if vec is not None:
                        next_pc = vec
                        self.registers[rd] = 0
                    elif not self.running:
                        return False  # kf==0 stop: halt loudly, no handler
                    else:
                        self.registers[rd] = self._handle_syscall(
                            syscall_num, image)
                else:
                    self.registers[rd] = self._handle_syscall(syscall_num, image)
        elif opcode == 'SYSRET':
            # E-K2: return from the syscall dispatcher (lowered from RV `mret`).
            # Restore the pre-trap register file, then deliver the
            # dispatcher's result (it wrote SYS_A0) into a0 = r10; re-enter
            # USER; resume at the saved post-SYSCALL PC.
            if self._syscall_regs is not None:
                self.registers[:] = self._syscall_regs
                self._syscall_regs = None
            self.registers[10] = self.memory[SYS_A0_ADDR >> 2] & 0xFFFFFFFF
            self.mode = MODE_USER
            sp = self.memory[SYSCALL_PC_ADDR >> 2]
            tx, ty = sp & 0xFFFF, (sp >> 16) & 0xFFFF
            target_x = tx * INSTR_WIDTH
            self._check_alignment(target_x)
            next_pc = (target_x, ty)
        elif opcode == 'JMP':
            tx, ty = imm & 0xFFFF, (imm >> 16) & 0xFFFF
            target_x = tx * INSTR_WIDTH
            self._check_alignment(target_x)
            next_pc = (target_x, ty)
        elif opcode == 'JZ':
            # CMP sets r0=1 on equality; JZ jumps when that flag is set.
            if self.registers[0] != 0:
                tx, ty = imm & 0xFFFF, (imm >> 16) & 0xFFFF
                target_x = tx * INSTR_WIDTH
                self._check_alignment(target_x)
                next_pc = (target_x, ty)
        elif opcode in ('JNZ', 'JNE'):
            # SE024: exact boolean complement of JZ — jump when the CMP
            # flag r0 is CLEAR (r0 == 0). JNE is an alias of JNZ; the
            # redundancy is deliberate so programs read naturally after
            # CMP ("jump if not equal") without a new name for JZ.
            if self.registers[0] == 0:
                tx, ty = imm & 0xFFFF, (imm >> 16) & 0xFFFF
                target_x = tx * INSTR_WIDTH
                self._check_alignment(target_x)
                next_pc = (target_x, ty)
        elif opcode == 'JLT':
            # SE025: jump when the CMP3 flag r0 == 0 (rd was SIGNED less-than).
            if self.registers[0] == 0:
                tx, ty = imm & 0xFFFF, (imm >> 16) & 0xFFFF
                target_x = tx * INSTR_WIDTH
                self._check_alignment(target_x)
                next_pc = (target_x, ty)
        elif opcode == 'JGT':
            # SE025: jump when the CMP3 flag r0 == 2 (rd was SIGNED
            # greater-than). Equal (r0 == 1) falls through.
            if self.registers[0] == 2:
                tx, ty = imm & 0xFFFF, (imm >> 16) & 0xFFFF
                target_x = tx * INSTR_WIDTH
                self._check_alignment(target_x)
                next_pc = (target_x, ty)
        elif opcode == 'JMPR':
            packed = self.registers[rd]
            tx, ty = packed & 0xFFFF, (packed >> 16) & 0xFFFF
            target_x = tx * INSTR_WIDTH
            self._check_alignment(target_x)
            next_pc = (target_x, ty)
            # DEFECT-18 (ruling 2026-09-12 option (a)): when returning from a tick
            # handler to the interrupted USER PC via JMPR, restore the pre-tick
            # USER register file byte-for-byte, re-enter MODE_USER, and clear the snapshot.
            if self._tick_regs is not None and (target_x, ty) == self._tick_pc:
                self.registers[:] = self._tick_regs
                self._tick_regs = None
                self._tick_pc = None
                self.mode = MODE_USER
        elif opcode == 'KJMP':
            # switch_to's terminal, data-sourced `ret` -- the privilege
            # boundary. Behaves like JMPR, then: drop to SUPER (returning to
            # the scheduler/kernel), and if the kernel armed MODE_LATCH just
            # before this switch, re-enter USER for the task we're jumping
            # into. E-K1; see systems/XV6_NANO_ISOLATION_ROADMAP.md.
            packed = self.registers[rd]
            tx, ty = packed & 0xFFFF, (packed >> 16) & 0xFFFF
            target_x = tx * INSTR_WIDTH
            self._check_alignment(target_x)
            next_pc = (target_x, ty)
            if self._iso_enabled:
                self.mode = MODE_SUPER
                if self.memory[MODE_LATCH_ADDR >> 2] == MODE_USER:
                    self.mode = MODE_USER
                    self.memory[MODE_LATCH_ADDR >> 2] = 0
        elif opcode == 'CALLR':
            # BK-39: consult BEFORE the pre-decrement.
            vec = self._stack_fence_fault(
                self.registers[31] - 1, x, y, "CALLR")
            if vec is not None:
                next_pc = vec
            elif not self.running:
                return False
            else:
                self.registers[31] -= 1
                packed_pc = (next_pc[1] << 16) | (next_pc[0] & 0xFFFF)
                self._mem_write(image, self.registers[31], packed_pc)
                packed = self.registers[rd]
                tx, ty = packed & 0xFFFF, (packed >> 16) & 0xFFFF
                target_x = tx * INSTR_WIDTH
                self._check_alignment(target_x)
                next_pc = (target_x, ty)
        elif opcode == 'PARALLEL_LD':
            # PARALLEL_LD rd addr count - load count values starting at addr into rd
            # Word-RAM addressing (matches scalar LD/ST and the WGSL twin's
            # cpus[...].memory): SpaDSL regions are initialized with scalar ST
            # into self.memory, so the parallel path MUST read the same store.
            # Previously this read image pixels, so region data written by ST
            # was invisible here (stale pixel garbage -> wrong reduce results).
            addr = imm & 0xFFFFFF  # low 24 bits = base address
            count = rs2 if rs2 > 0 else (imm >> 24)  # count in rs2 or high bits of imm
            # BK-56: the CONFIG-block READ posture extends to the parallel
            # arm (directive §2 "every read arm"): a window whose first
            # in-RAM word is a BK-41 locked config word, read by USER code,
            # refuses the WHOLE op with the same no-vector semantics as the
            # scalar LD consult. SUPER exempt (mode-scoped, not a blanket).
            bk56_refuse = False
            if self._iso_enabled and self.mode == MODE_USER:
                for i in range(count):
                    a = addr + i
                    if not (0 <= a < len(self.memory)):
                        continue
                    if ((BOX_MMIO_BASE >> 2) <= a < (BOX_MMIO_BASE >> 2) + 256
                            and (a in self._BK41_LOCKED_WORDS)):
                        bk56_refuse = True
                        break
            if bk56_refuse:
                self.fault_addr = (addr << 2) & 0xFFFFFFFF
                self.fault_pc = (y << 16) | ((x // INSTR_WIDTH) & 0xFFFF)
                self.faulted = True
                self.fault_reason = (
                    f"mmio_config_read_refused op=PARALLEL_LD word={addr} "
                    f"addr={self.fault_addr:#x} mode=USER site=glyph_isa_v2")
                if len(self.memory) > (FAULT_PC_ADDR >> 2):
                    self.memory[FAULT_ADDR_ADDR >> 2] = self.fault_addr
                    self.memory[FAULT_PC_ADDR >> 2] = self.fault_pc
                self.mode = MODE_SUPER
                self.running = False  # NO vector (BK-75 KFC-L6)
                return False
            # BK-39: read-side parity with the scalar-LD tile confinement
            # (RULING_BK38_READ_POSTURE clause 3): a tile-confined USER
            # PARALLEL_LD whose first offending word is out-of-fence
            # refuses the whole op.
            vec = None
            for i in range(count):
                a = addr + i
                if not (0 <= a < len(self.memory)):
                    continue
                if self._addr_in_box(a << 2):
                    continue
                if (self._iso_enabled and self.mode == MODE_USER
                        and self._tile_confinement):
                    vec = self._stack_fence_fault(a, x, y, "PARALLEL_LD")
                break  # judge only the first out-of-fence word in range
            if vec is not None:
                next_pc = vec
            elif not self.running:
                pass  # kf==0 stop: step returns False, nothing read
            else:
                for i in range(count):
                    val = self.memory[addr + i] if 0 <= addr + i < len(self.memory) else 0
                    # Store in consecutive registers starting at rd
                    if rd + i < 32:  # Register bounds check
                        self.registers[rd + i] = val
        elif opcode == 'PARALLEL_ST':
            # PARALLEL_ST addr_reg rs count - store count values from rs starting at address in addr_reg
            # Word-RAM addressing (see PARALLEL_LD note).
            # rs1 contains the address register, rd contains the source register, imm contains count
            addr = self.registers[rs1]  # Get address from register
            count = imm if imm > 0 else rs2  # count in immediate or rs2
            rs_base = rd  # Source register base
            # BK-39: the fence-blind write arm. Consult the FIRST offending
            # word and refuse the whole op (nothing lands — E-K1's
            # "the store is abandoned" discipline). BOX0 self-grant dies
            # here too: words 8195/8196 are out-of-tile USER stores.
            vec = None
            for i in range(count):
                a = addr + i
                if not (0 <= a < len(self.memory)):
                    continue  # OOB legs keep the landed bounds-only shape
                if self._addr_in_box(a << 2):
                    continue
                # BK-41: SUPER post-USER stores to the kernel-write-only
                # CONFIG block refuse here too — the box consult is
                # USER-only, so an in-window SUPER PARALLEL_ST rode the
                # same :968 exemption hole the scalar ST arm needed
                # BK-76/BK-41's explicit lock for (probe A1: sentinel
                # 4242 landed at TIMER_COUNT clean, exit 0). Same
                # refusal semantics per arm: Option A, no vector, stop.
                if (self.mode == MODE_SUPER and self._bk76_ever_user
                        and self._tile_confinement
                        and a in self._BK41_LOCKED_WORDS):
                    self._bk76_exemption_refuse(a, self.registers[rs_base + i]
                                                if rs_base + i < 32 else 0,
                                                x, y)
                    return False
                if (self._iso_enabled and self.mode == MODE_USER
                        and self._tile_confinement):
                    vec = self._stack_fence_fault(a, x, y, "PARALLEL_ST")
                break  # judge only the first out-of-fence word in range
            if vec is not None:
                next_pc = vec
            elif not self.running:
                pass  # kf==0 stop: step returns False, nothing lands
            else:
                for i in range(count):
                    a = addr + i
                    if 0 <= a < len(self.memory):
                        self.memory[a] = self.registers[rs_base + i] & 0xFFFFFFFF if rs_base + i < 32 else 0
                    # GH-8b write-through pixel mirror (RCA GH9LOADER_PATCH_
                    # IMAGE_MIRROR, 2026-09-10): the Python engine FETCHES
                    # instructions from IMAGE pixels (step(): image[y,x]) --
                    # pixels are the persisted instruction truth. The GH-9
                    # loader kernel patches its exec window with this opcode;
                    # 087f29b moved PARALLEL_ST to RAM-only, so the patch
                    # landed in RAM the fetch never sees (window stayed HALT
                    # padding -> every injected program died on instr 0,
                    # result 0: test_gh9_loader / GH-11 / GH-15-step3 e2e
                    # / test_gh11_drives_gh9 reds). Mirror the store into
                    # the image at the same linear pixel index when in
                    # bounds -- identical to _fs_pix_write's write-through
                    # mirror (memory[] coherent, pixels the truth). SpaDSL
                    # region reads (PARALLEL_LD) still hit RAM, so 087f29b's
                    # region fix is preserved; addresses beyond the image
                    # simply skip the mirror.
                    ih, iw, _ = image.shape
                    if 0 <= a < ih * iw:
                        v = self.memory[a]
                        image[a // iw, a % iw] = (
                            (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
        elif opcode == 'PARALLEL_ADD':
            # PARALLEL_ADD rd rs1 rs2 count - elementwise add of count values
            # r[rd + i] = r[rs1 + i] + r[rs2 + i] for i in 0..count-1
            count = imm if imm > 0 else 1  # count in immediate
            for i in range(count):
                src1_idx = rs1 + i
                src2_idx = rs2 + i
                dst_idx = rd + i
                if dst_idx < 32 and src1_idx < 32 and src2_idx < 32:  # Register bounds check
                    self.registers[dst_idx] = self.registers[src1_idx] + self.registers[src2_idx]
        elif opcode == 'PARALLEL_SUB':
            # PARALLEL_SUB rd rs1 rs2 count - elementwise sub of count values  
            count = imm if imm > 0 else 1  # count in immediate
            for i in range(count):
                if rd + i < 32 and rs1 + i < 32 and rs2 + i < 32:  # Register bounds check
                    self.registers[rd + i] = self.registers[rs1 + i] - self.registers[rs2 + i]
        elif opcode == 'PARALLEL_REDUCE_SUM':
            # PARALLEL_REDUCE_SUM rd addr count - sum count values starting at addr into rd
            # Word-RAM addressing (see PARALLEL_LD note): must read the same
            # store scalar ST wrote region data into.
            addr = imm & 0xFFFFFF  # low 24 bits = base address
            count = rs2 if rs2 > 0 else (imm >> 24)  # count in rs2 or high bits of imm
            total = 0
            for i in range(count):
                a = addr + i
                if 0 <= a < len(self.memory):
                    total += self.memory[a]
            self.registers[rd] = total & 0xFFFFFFFF
        elif opcode == 'HALT':
            self.running = False
            return False

        # GH-16: Preemptive scheduling timer tick
        if self._iso_enabled and was_user and self.mode == MODE_USER and self.running and not self.faulted:
            ktick = self.memory[KTICK_PC_ADDR >> 2]
            if ktick != 0:
                tcount = self.memory[TIMER_COUNT_ADDR >> 2]
                if tcount > 0:
                    tcount -= 1
                    self.memory[TIMER_COUNT_ADDR >> 2] = tcount
                    if tcount == 0:
                        reload_val = self.memory[TIMER_RELOAD_ADDR >> 2]
                        self.memory[TIMER_COUNT_ADDR >> 2] = reload_val
                        interrupted_col = (next_pc[0] // INSTR_WIDTH) & 0xFFFF
                        interrupted_row = next_pc[1] & 0xFFFF
                        self.memory[TICK_PC_ADDR >> 2] = (interrupted_row << 16) | interrupted_col
                        # DEFECT-18 (ruling 2026-09-12 option (a)): the engine owns CPU state
                        # across preemptive ticks. Snapshot the USER register file and interrupted
                        # PC; JMPR restores them when the handler returns.
                        self._tick_regs = self.registers[:]
                        self._tick_pc = (interrupted_col * INSTR_WIDTH, interrupted_row)
                        self.mode = MODE_SUPER
                        tx, ty = ktick & 0xFFFF, (ktick >> 16) & 0xFFFF
                        target_x = tx * INSTR_WIDTH
                        self._check_alignment(target_x)
                        next_pc = (target_x, ty)

        self.pc = next_pc
        return True

    def _handle_syscall(self, syscall_num: int, image: np.ndarray, imm: int = 0) -> int:
        """
        Handle hypervisor syscalls from spatial programs.

        Syscall interface compatible with GeOS hypervisor:
        - 0x01: SYSCALL_WRITE - Write to output buffer (arg1=r1=addr, arg2=r2=len)
        - 0x02: SYSCALL_READ  - Read from input buffer (arg1=r1=addr, arg2=r2=len)
        - 0x03: SYSCALL_FILE_WRITE - Write to file (arg1=r1=path_addr, arg2=r2=data_addr, arg3=r3=len)
        - 0x04: SYSCALL_FILE_READ  - Read from file (arg1=r1=path_addr, arg2=r2=data_addr, arg3=r3=len)
        - 0x05: SYSCALL_EXIT   - Exit with status (arg1=r1=status)
        - 0x06: SYSCALL_DEBUG  - Debug print (arg1=r1=value)
        - 0x07: SYSCALL_RUN    - Run executable (arg1=r1=path_addr)
        - 0x08: SYSCALL_AUDIO_OUT - Write audio (arg1=r1=path_addr, arg2=r2=data_addr, arg3=r3=len)
        - 0x09: SYSCALL_AUDIO_IN  - Read audio (arg1=r1=path_addr, arg2=r2=dest_addr, arg3=r3=max_len)
        - 0x10: SYSCALL_BOOT_LINUX - Recognize Linux boot container (arg1=r1=container_addr, arg2=r2=flags)
        - 0x11: SYSCALL_STORE_CODE - Copy code/payload words in pixel space (arg1=r1=dest_addr, arg2=r2=src_addr, arg3=r3=len)
        - 0x13: SYSCALL_FILE_LIST - List host files (arg1=r1=dir_path_addr, arg2=r2=dest_addr, arg3=r3=max_bytes)
        - 0x12-0xFF: Reserved for Geometry OS spatial services

        Returns: syscall result (0=success, -1=error, or byte count / exit code)
        """
        # Map syscall numbers to hypervisor service addresses
        # These match the GeOS hypervisor bridge constants
        SPATIAL_REGISTRY_BASE = 0x8009_0000

        def _read_path(path_addr: int) -> str:
            # SINGLE-VIEW path read (SE021 view-merge retirement, 2026-09-22,
            # claim-queue item 2 step 2): path strings live in the data view
            # the same way LD sees them — RAM array, FS-pixel aliasing inside
            # the window. The 09-17 image-fallback view-merge is RETIRED:
            # "PATH addresses point into image/pixel space" was the
            # pre-DEFECT-23-ROOT convention; SYSCALL_ABI_SPEC.md now says
            # HOST paths are "decoded from RAM (see _read_path)". An
            # all-zero data view decodes as the empty string and the handler
            # refuses — it no longer rescues image-seeded bytes, which under
            # RAM/aliasing divergence is exactly the dual-view SE021 defect
            # shape this retirement closes. NUL terminates.
            buf = bytearray()
            for i in range(4096):
                a = path_addr + i
                if self.fs_pix_enabled and self._FS_PIX_LO_WORD <= a < self._FS_PIX_HI_WORD:
                    v = self._fs_pix_read(image, a) & 0xFF
                elif 0 <= a < len(self.memory):
                    v = self.memory[a] & 0xFF
                else:
                    # Past RAM: the data view ends. Treat as terminator —
                    # the string was never fully materialized in RAM.
                    break
                if v == 0:
                    break
                buf.append(v)
            import os
            return os.fsdecode(bytes(buf))

        if syscall_num == 0x01:  # SYSCALL_WRITE
            # Write r2 bytes from address r1 to output buffer.
            # DEFECT-D/backlog(d): migrated from image space to RAM
            # (self.memory) 2026-09-16 - (A) scoped to handlers, per the
            # SYSCALL_READ (0x02) precedent. Out-of-range addr reads as 0
            # rather than IndexError-ing (same no-crash default 0x02 uses,
            # here for reads instead of the growth guard writes need).
            addr = self.registers[1]
            length = self.registers[2]
            for i in range(length):
                a = addr + i
                val = self.memory[a] if 0 <= a < len(self.memory) else 0
                self.output.append(val)
            print(f"[SYSCALL] WRITE: {length} bytes from addr {addr}")
            return 0

        elif syscall_num == 0x02:  # SYSCALL_READ
            # Read up to r2 bytes into RAM word address r1 (self.memory,
            # LD-readable - NOT image/pixel space: input is DATA, and the
            # DEFECT-23-ROOT convention is LD/ST=RAM for data, image=code.
            # An earlier draft wrote to image space via _mem_write, which
            # would have made the bytes unreachable by any LD - caught
            # before this landed anywhere, not after.
            # Source: the harness-seeded input ring (INPUT_LEN/CURSOR/DATA,
            # one byte per self.memory word, reserved at module top for
            # GO-3's scripted host input). Returns the number of bytes
            # ACTUALLY read (0 when the ring is exhausted), so a caller can
            # tell "no more input yet" from "input was zero bytes" - the
            # previous stub always wrote zeros and returned 0, which made
            # the two indistinguishable.
            addr = self.registers[1]
            want = self.registers[2]
            total = (self.memory[INPUT_LEN_ADDR >> 2]
                     if len(self.memory) > (INPUT_LEN_ADDR >> 2) else 0)
            cursor = (self.memory[INPUT_CURSOR_ADDR >> 2]
                      if len(self.memory) > (INPUT_CURSOR_ADDR >> 2) else 0)
            avail = max(0, min(total, INPUT_DATA_CAP) - cursor)
            n = max(0, min(want, avail))
            # No unbounded self.memory growth on a model-controlled addr -
            # same defect class as DEFECT-23's paged_dispatch arming loop.
            # Truncate the read short rather than extend RAM.
            n = max(0, min(n, len(self.memory) - addr)) if addr < len(self.memory) else 0
            for i in range(n):
                src_idx = (INPUT_DATA_ADDR >> 2) + cursor + i
                byte_val = self.memory[src_idx] if len(self.memory) > src_idx else 0
                self.memory[addr + i] = byte_val & 0xFF
            if len(self.memory) > (INPUT_CURSOR_ADDR >> 2):
                self.memory[INPUT_CURSOR_ADDR >> 2] = cursor + n
            print(f"[SYSCALL] READ: {n}/{want} bytes to addr {addr} "
                  f"(ring cursor {cursor}->{cursor + n} of {total})")
            return n

        elif syscall_num == 0x03:  # SYSCALL_FILE_WRITE
            # Write file: r1=path_addr, r2=data_addr, r3=len
            path_addr = self.registers[1]
            data_addr = self.registers[2]
            length = self.registers[3]
            if length < 0:
                print(f"[SYSCALL] FILE_WRITE: invalid length {length}")
                return -1
            try:
                path = _read_path(path_addr)
                # item-25 VFS-2: attached VFS re-route — the write lands in
                # the VFS staging overlay (ext2 image behind it), rc 0/-1.
                vfs = getattr(self, "vfs", None)
                if vfs is not None:
                    data = bytes((self.memory[data_addr + i] & 0xFF)
                                 if 0 <= data_addr + i < len(self.memory) else 0
                                 for i in range(length))
                    rc = vfs.vfs_write(path, data)
                    if rc == 0:
                        print(f"[SYSCALL] FILE_WRITE(vfs): {length} bytes from addr {data_addr} path {path!r}")
                    else:
                        print(f"[SYSCALL] FILE_WRITE(vfs) refused: {path!r}")
                    return rc
                # backlog(d)/DEFECT-D (2026-09-16, handler 3/5): the data
                # arg (r2) migrated from image space to RAM (self.memory),
                # matching 0x01/0x02/0x04's precedent - file payloads are
                # DATA, and the DEFECT-23-ROOT convention is RAM for data.
                # path_addr (r1) is untouched - _read_path's own
                # view-merge (RUN2/GH-9 in-flight work) is a separate
                # concern, not part of this migration. Out-of-range source
                # bytes read as 0 rather than raising (same no-crash
                # convention 0x01's RAM read uses); FILE_WRITE's return
                # value is unaffected either way.
                # BK-44: host arm requires the realpath under a
                # GLYPH_FS_ALLOW root — SAME check/model/rationale as the
                # 0x13 arm below (BK-15): deny-by-default, the host-FS
                # write primitive must not be cheaper to reach than the
                # listing primitive. VFS-attached writes (the reroute
                # above) are NOT host-FS and stay on the VFS's own
                # containment (item-25).
                import os as _os
                _resolved = _os.path.realpath(path)
                _roots = _get_fs_allow_roots()
                if not any(_resolved == r or _resolved.startswith(r + _os.sep)
                           for r in _roots):
                    print(f"[SYSCALL] FILE_WRITE denied: {path} not under GLYPH_FS_ALLOW")
                    return -1
                data = bytes((self.memory[data_addr + i] & 0xFF)
                             if 0 <= data_addr + i < len(self.memory) else 0
                             for i in range(length))
                with open(path, "wb") as f:
                    f.write(data)
                print(f"[SYSCALL] FILE_WRITE: {length} bytes from addr {data_addr} to path at {path_addr}")
                return 0
            except (OSError, Exception) as e:
                print(f"[SYSCALL] FILE_WRITE failed: {e}")
                return -1

        elif syscall_num == 0x04:  # SYSCALL_FILE_READ
            # Read file: r1=path_addr, r2=data_addr, r3=len
            path_addr = self.registers[1]
            data_addr = self.registers[2]
            max_len = self.registers[3]
            if max_len < 0:
                print(f"[SYSCALL] FILE_READ: invalid max_len {max_len}")
                return -1
            try:
                import os
                path = _read_path(path_addr)
                # item-25 VFS-2: attached VFS re-route — staged overlay
                # first, then the image as of last sync. Same RAM-dest
                # convention as the host arm below.
                vfs = getattr(self, "vfs", None)
                if vfs is not None:
                    data = vfs.vfs_read(path, max_len)
                    if data is None:
                        print(f"[SYSCALL] FILE_READ(vfs): file not found: {path!r}")
                        return -1
                    for i, byte_val in enumerate(data):
                        a = data_addr + i
                        if 0 <= a < len(self.memory):
                            self.memory[a] = byte_val
                    print(f"[SYSCALL] FILE_READ(vfs): {len(data)} bytes from {path!r} to addr {data_addr}")
                    return len(data)
                if not os.path.isfile(path):
                    print(f"[SYSCALL] FILE_READ: file not found at path at {path_addr}")
                    return -1
                # BK-44: host arm requires the realpath under a
                # GLYPH_FS_ALLOW root — same check/model as 0x03 above and
                # the 0x13 arm (BK-15): host file CONTENT must not be
                # exfiltratable by a task that could not even LIST the
                # directory it sits in. VFS-attached reads stay on the
                # VFS's own containment (item-25).
                resolved = os.path.realpath(path)
                roots = _get_fs_allow_roots()
                if not any(resolved == r or resolved.startswith(r + os.sep)
                           for r in roots):
                    print(f"[SYSCALL] FILE_READ denied: {path} not under GLYPH_FS_ALLOW")
                    return -1
                with open(path, "rb") as f:
                    data = f.read(max_len)
                # backlog(d)/DEFECT-D (2026-09-16): dest migrated from
                # image space to RAM (self.memory), (A) scoped to
                # handlers. path_addr is untouched - _read_path's
                # view-merge (RUN2/GH-9 in-flight work) is a separate
                # concern, not part of this migration. Out-of-range dest
                # bytes are dropped rather than growing RAM, same
                # no-crash convention as 0x01/0x02.
                for i, byte_val in enumerate(data):
                    a = data_addr + i
                    if 0 <= a < len(self.memory):
                        self.memory[a] = byte_val
                print(f"[SYSCALL] FILE_READ: {len(data)} bytes from path at {path_addr} to addr {data_addr}")
                return len(data)
            except (OSError, Exception) as e:
                print(f"[SYSCALL] FILE_READ failed: {e}")
                return -1

        elif syscall_num == 0x05:  # SYSCALL_EXIT
            # Exit with status in r1
            status = self.registers[1]
            print(f"[SYSCALL] EXIT: status={status}")
            self.running = False
            return status

        elif syscall_num == 0x06:  # SYSCALL_DEBUG
            # Debug print: r1=value
            value = self.registers[1]
            print(f"[SYSCALL] DEBUG: r1={value}")
            return 0

        elif syscall_num == 0x07:  # SYSCALL_RUN
            # Execute file: r1=path_addr
            path_addr = self.registers[1]
            try:
                import os
                path = _read_path(path_addr)
                if not os.path.isfile(path):
                    print(f"[SYSCALL] RUN: not a regular file at path at {path_addr}")
                    return -1
                resolved = os.path.realpath(path)
                if resolved not in _get_run_allowlist():
                    print(f"[SYSCALL] RUN denied: {path} not in GLYPH_RUN_ALLOW")
                    return -1
                parent_dir = os.path.dirname(os.path.abspath(path))
                res = _spawn([path], cwd=parent_dir, timeout=30)
                print(f"[SYSCALL] RUN: executed {path}, exit code {res.returncode}")
                return res.returncode
            except (OSError, subprocess.SubprocessError, Exception) as e:
                print(f"[SYSCALL] RUN failed: {e}")
                return -1

        elif syscall_num == 0x08:  # SYSCALL_AUDIO_OUT
            # Write audio: r1=path_addr, r2=data_addr, r3=len
            path_addr = self.registers[1]
            data_addr = self.registers[2]
            length = self.registers[3]
            if length < 0:
                print(f"[SYSCALL] AUDIO_OUT: invalid length {length}")
                return -1
            try:
                import scipy.io.wavfile as wavfile
                from src.codec.phy import Phy16Tone
                path = _read_path(path_addr)
                # backlog(d)/DEFECT-D (2026-09-16, handler 4/5): the data
                # arg (r2) migrated from image space to RAM (self.memory),
                # matching 0x01/0x02/0x03/0x04's precedent - audio payloads
                # are DATA, and the DEFECT-23-ROOT convention is RAM for
                # data. path_addr (r1) is untouched - _read_path's own
                # view-merge (RUN2/GH-9 in-flight work) is a separate
                # concern, not part of this migration. Out-of-range source
                # bytes read as 0 rather than raising (same no-crash
                # convention 0x01's RAM read uses); AUDIO_OUT's return
                # value is unaffected either way.
                data = bytes((self.memory[data_addr + i] & 0xFF)
                             if 0 <= data_addr + i < len(self.memory) else 0
                             for i in range(length))
                audio = Phy16Tone.encode(data)
                int16_samples = (audio * 32767).astype(np.int16)
                wavfile.write(path, Phy16Tone.SAMPLE_RATE, int16_samples)
                print(f"[SYSCALL] AUDIO_OUT: {length} bytes encoded to {path}")
                return 0
            except (OSError, Exception) as e:
                print(f"[SYSCALL] AUDIO_OUT failed: {e}")
                return -1

        elif syscall_num == 0x09:  # SYSCALL_AUDIO_IN
            # Read audio: r1=path_addr, r2=dest_addr, r3=max_len
            path_addr = self.registers[1]
            dest_addr = self.registers[2]
            max_len = self.registers[3]
            if max_len < 0:
                print(f"[SYSCALL] AUDIO_IN: invalid max_len {max_len}")
                return -1
            try:
                import os
                import scipy.io.wavfile as wavfile
                from src.codec.phy import Phy16Tone
                path = _read_path(path_addr)
                if not os.path.isfile(path):
                    print(f"[SYSCALL] AUDIO_IN: file not found at path at {path_addr}")
                    return -1
                sr, audio_samples = wavfile.read(path)
                if audio_samples.ndim > 1:
                    audio_samples = audio_samples[:, 0]
                decoded = Phy16Tone.decode(audio_samples)
                if max_len < len(decoded):
                    decoded = decoded[:max_len]
                # backlog(d)/DEFECT-D (2026-09-16, handler 5/5): dest
                # migrated from image space to RAM (self.memory), matching
                # 0x02/0x04's write-side precedent - decoded bytes are
                # DATA, and the DEFECT-23-ROOT convention is RAM for data.
                # path_addr (r1) is untouched - _read_path's view-merge
                # (RUN2/GH-9 in-flight work) is a separate concern, not
                # part of this migration. Out-of-range dest bytes are
                # dropped rather than growing RAM, same no-crash
                # convention as 0x01/0x02/0x04.
                for i, byte_val in enumerate(decoded):
                    a = dest_addr + i
                    if 0 <= a < len(self.memory):
                        self.memory[a] = byte_val
                print(f"[SYSCALL] AUDIO_IN: {len(decoded)} bytes decoded from {path} to addr {dest_addr}")
                return len(decoded)
            except (OSError, Exception) as e:
                print(f"[SYSCALL] AUDIO_IN failed: {e}")
                return -1

        elif syscall_num == 0x10:  # SYSCALL_BOOT_LINUX
            # Container header signature: bytes packed one byte per word,
            # LOW byte first: bytes [w0, w1, w2, w3] == b"VAC2" with the
            # words holding the bytes at [addr, addr+1, addr+2, addr+3].
            # backlog(d)/DEFECT-D residual (2026-09-22, finishing the
            # (A)-scoped-to-handlers sweep): the header read migrated from
            # image space (_mem_read) to RAM (self.memory), matching the
            # 0x01/0x02/0x03/0x04/0x08/0x09 precedent - a container
            # descriptor is DATA, and the DEFECT-23-ROOT convention is RAM
            # for data. Out-of-range words read as 0 (no-crash convention),
            # which fails the signature check (-1) rather than raising.
            # Recognition only: this validates and accepts the container
            # descriptor; no boot is performed by the engine.
            container_addr = self.registers[1]
            flags = self.registers[2]
            p0 = (self.memory[container_addr] if 0 <= container_addr < len(self.memory) else 0)
            p1 = (self.memory[container_addr + 1] if 0 <= container_addr + 1 < len(self.memory) else 0)
            p2 = (self.memory[container_addr + 2] if 0 <= container_addr + 2 < len(self.memory) else 0)
            p3 = (self.memory[container_addr + 3] if 0 <= container_addr + 3 < len(self.memory) else 0)
            sig = bytes((p0 & 0xFF, p1 & 0xFF, p2 & 0xFF, p3 & 0xFF))
            if sig != b"VAC2":
                print(f"[SYSCALL] BOOT_LINUX: invalid container signature {sig!r} at 0x{container_addr:08X}")
                return -1
            print(f"[SYSCALL] BOOT_LINUX: recognized VAC2 container at 0x{container_addr:08X}, flags=0x{flags:02X}")
            return 0

        elif syscall_num == 0x11:  # SYSCALL_STORE_CODE
            dest_addr = self.registers[1]
            src_addr = self.registers[2]
            length = self.registers[3]
            if length <= 0:
                print(f"[SYSCALL] STORE_CODE: invalid length {length}")
                return -1
            for i in range(length):
                val = self._mem_read(image, src_addr + i)
                self._mem_write(image, dest_addr + i, val)
            print(f"[SYSCALL] STORE_CODE: copied {length} words from 0x{src_addr:08X} to 0x{dest_addr:08X}")
            return 0

        elif syscall_num == 0x12:  # SYSCALL_RUN2 — RUN with two path arguments
            # r1=path_addr, r2=arg1_addr (0 = none), r3=arg2_addr (0 = none).
            # SE021: glyph-on-glyph needs to hand a child image + out path to
            # the runner; 0x07 spawns [path] only and reusing r2/r3 there
            # would change semantics for existing RUN programs (their r2/r3
            # hold stale garbage). Same containment as 0x07: realpath of the
            # TARGET must be in GLYPH_RUN_ALLOW; args are data, not targets.
            path_addr = self.registers[1]
            arg1_addr = self.registers[2]
            arg2_addr = self.registers[3]
            try:
                import os
                path = _read_path(path_addr)
                argv = [path]
                if arg1_addr:
                    argv.append(_read_path(arg1_addr))
                if arg2_addr:
                    argv.append(_read_path(arg2_addr))
                if not os.path.isfile(path):
                    print(f"[SYSCALL] RUN2: not a regular file at path at {path_addr}")
                    return -1
                resolved = os.path.realpath(path)
                if resolved not in _get_run_allowlist():
                    print(f"[SYSCALL] RUN2 denied: {path} not in GLYPH_RUN_ALLOW")
                    return -1
                parent_dir = os.path.dirname(resolved)
                # Spawn against ABSOLUTE paths: a relative `path` would be
                # resolved by the child against cwd=parent_dir, which breaks
                # when the shell's own cwd differs from the runner's dir
                # (measured 2026-09-16: relative runner name + cwd=parent_dir
                # -> ENOENT in the child). realpath() normalizes both.
                res = _spawn([resolved] + argv[1:], cwd=parent_dir, timeout=30)
                print(f"[SYSCALL] RUN2: executed {path} ({len(argv)-1} args), exit code {res.returncode}")
                return res.returncode
            except (OSError, subprocess.SubprocessError, Exception) as e:
                print(f"[SYSCALL] RUN2 failed: {e}")
                return -1

        elif syscall_num == 0x13:  # SYSCALL_FILE_LIST (BK-15, landed 2026-09-24)
            # List host files: r1=dir_path_addr, r2=dest_addr, r3=max_bytes.
            # Containment: realpath of the directory must be under one of
            # the GLYPH_FS_ALLOW roots (same model as 0x07/0x12's
            # GLYPH_RUN_ALLOW; deny-by-default when the env is unset —
            # enumeration is the more invasive primitive, it must not be
            # cheaper to reach than RUN). Names are returned NUL-separated
            # in the RAM dest buffer (truncated to r3 bytes, last name cut
            # whole: a partial name is never emitted); the return value is
            # the ENTRY COUNT (rd), 0 for an empty dir, -1 on refusal.
            # NUL separation keeps names binary-safe for the in-image
            # consumer; sizes/mtimes are L2's ls -l upgrade, not this arm.
            dir_addr = self.registers[1]
            dest_addr = self.registers[2]
            max_bytes = self.registers[3]
            if max_bytes < 0:
                print(f"[SYSCALL] FILE_LIST: invalid max_bytes {max_bytes}")
                return -1
            try:
                import os
                dir_path = _read_path(dir_addr)
                # item-25 VFS-2: attached VFS re-route — listing served from
                # the staging ∪ image view (same rc contract: count, 0 for
                # empty, -1 refusal; whole-name truncation to max_bytes).
                vfs = getattr(self, "vfs", None)
                if vfs is not None:
                    names = vfs.vfs_list(dir_path, max_bytes)
                    if names is None:
                        print(f"[SYSCALL] FILE_LIST(vfs) refused: {dir_path!r}")
                        return -1
                    for i, byte_val in enumerate(b"".join(
                            n.encode() + b"\0" for n in names)):
                        a = dest_addr + i
                        if 0 <= a < len(self.memory):
                            self.memory[a] = byte_val
                    print(f"[SYSCALL] FILE_LIST(vfs): {len(names)} entries from {dir_path!r} to addr {dest_addr}")
                    return len(names)
                if not os.path.isdir(dir_path):
                    print(f"[SYSCALL] FILE_LIST: not a directory at path at {dir_addr}")
                    return -1
                resolved = os.path.realpath(dir_path)
                roots = _get_fs_allow_roots()
                if not any(resolved == r or resolved.startswith(r + os.sep)
                           for r in roots):
                    print(f"[SYSCALL] FILE_LIST denied: {dir_path} not under GLYPH_FS_ALLOW")
                    return -1
                names = sorted(os.listdir(resolved))
                blob = bytearray()
                count = 0
                for name in names:
                    piece = name.encode() + b"\0"
                    if len(blob) + len(piece) > max_bytes:
                        break  # whole-name truncation, never a partial name
                    blob += piece
                    count += 1
                # Dest is RAM (DEFECT-23-ROOT convention: listings are
                # DATA); out-of-range dest bytes drop, RAM never grows.
                for i, byte_val in enumerate(blob):
                    a = dest_addr + i
                    if 0 <= a < len(self.memory):
                        self.memory[a] = byte_val
                print(f"[SYSCALL] FILE_LIST: {count} entries from {dir_path} to addr {dest_addr}")
                return count
            except (OSError, Exception) as e:
                print(f"[SYSCALL] FILE_LIST failed: {e}")
                return -1

        elif 0x10 <= syscall_num <= 0xFF:
            # Reserved for GeOS spatial services - bridge to hypervisor
            print(f"[SYSCALL] GEOS_SERVICE 0x{syscall_num:02X}: dispatched to MMIO 0x{SPATIAL_REGISTRY_BASE:08X}")
            return 0

        else:
            print(f"[SYSCALL] UNKNOWN: syscall_num=0x{syscall_num:02X}")
            return -1

    def run(self, image: np.ndarray, max_instructions: int = 1000):
        self.running = True
        n = 0
        while self.running and n < max_instructions:
            self.step(image)
            n += 1
        return n


def demo():
    opcode_map = OpcodeMapV2()
    print("Opcode -> RGB (collision-safe):")
    for op in OpcodeMapV2.OPCODES:
        print(f"  {op:4} -> {opcode_map.opcode_to_rgb(op)}")

    # NOTE: CMP writes its result to r0 (the flag register), so the loop
    # counter must live elsewhere (r5) to avoid clobbering it.
    program = [
        "LDI r5 0",       # 0: counter = 0
        "LDI r1 5",       # 1: limit = 5
        "CMP r5 r1",      # 2: r0 = (counter == limit)
        "JZ 0,1",         # 3: if equal, jump to HALT (instr 8 -> row1,col0)
        "PRT r5",         # 4: print counter
        "LDI r2 1",       # 5: r2 = 1
        "ADD r5 r2",      # 6: counter += 1
        "JMP 2,0",        # 7: jump back to CMP (instr 2 -> row0,col2)
        "HALT",           # 8
    ]

    assembler = GlyphAssemblerV2(opcode_map)
    image = assembler.assemble(program, width_instrs=8)
    print(f"Assembled: {len(program)} instrs -> image {image.shape}")

    cpu = GlyphCPUv2(opcode_map, cols_instrs=8)
    n = cpu.run(image)
    print(f"Halted after {n} steps. Final registers[0:3]={cpu.registers[:3]}")
    print(f"Output: {cpu.output}")

    opcode_map.close()


if __name__ == '__main__':
    demo()

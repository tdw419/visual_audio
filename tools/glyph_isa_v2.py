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

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from tools.wordbase import WordbaseManager

INSTR_WIDTH = 4
RESERVED_MAX = 4  # (0,0,0)..(4,4,4) reserved
UNUSED_REGISTER = 0xFF


class SpatialMisalignmentFault(Exception):
    pass


class OpcodeMapV2:
    """Opcode <-> RGB mapping with reserved-palette collision avoidance."""

    OPCODES = {
        'HALT': 'stop',
        'LDI': 'load',
        'ADD': 'add',
        'SUB': 'subtract',
        'CMP': 'compare',
        'JMP': 'jump',
        'JZ': 'jump_if',
        'PRT': 'print',
        'LD': 'load',
        'ST': 'store',
        'AND': 'intersect',
        'OR': 'union',
        'XOR': 'exclusive',
        'SHL': 'shift_left',
        'SHR': 'shift_right',
        'PUSH': 'push',
        'POP': 'pop',
        'CALL': 'call',
        'RET': 'return',
        'SYSCALL': 'system_call',
    }

    # Fixed literal colors for the opcodes added in the Turing-complete
    # expansion (AND/OR/XOR/SHL/SHR/PUSH/POP/CALL/RET/SYSCALL). Unlike the original
    # 10 opcodes (which derive their color from a wordbase.db lookup and
    # therefore shift if the wordbase changes), these are pinned so the
    # WGSL GPU port never has to be regenerated to match a live database -
    # a real requirement once a decoder is hardcoding color literals.
    FIXED_COLORS: Dict[str, Tuple[int, int, int]] = {
        'AND':  (100, 149, 237),
        'OR':   (255, 165, 0),
        'XOR':  (238, 130, 238),
        'SHL':  (0, 206, 209),
        'SHR':  (218, 112, 214),
        'PUSH': (34, 139, 34),
        'POP':  (139, 69, 19),
        'CALL': (75, 0, 130),
        'RET':  (255, 215, 0),
        'SYSCALL': (255, 69, 0),
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
        instrs = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            instrs.append(parts)

        n = len(instrs)
        cols = width_instrs
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
            elif opcode in ('ADD', 'SUB', 'CMP', 'LD', 'ST', 'AND', 'OR', 'XOR', 'SHL', 'SHR'):
                rd = int(args[0][1:])
                rs2 = int(args[1][1:])
            elif opcode in ('PRT', 'PUSH', 'POP', 'SYSCALL'):
                rd = int(args[0][1:])
                # Parse immediate for SYSCALL
                if opcode == 'SYSCALL' and len(args) > 1:
                    imm_str = args[1]
                    if imm_str.startswith('0x') or imm_str.startswith('0X'):
                        imm = int(imm_str, 16)
                    else:
                        imm = int(imm_str)
            elif opcode in ('JMP', 'JZ', 'CALL'):
                x, y = args[0].split(',')
                imm = (int(y) << 16) | int(x)  # pack coord into imm
            elif opcode in ('HALT', 'RET'):
                pass

            image[row, base_x + 1] = (rs1, rs2, rd)
            low_px, high_px = _pack_immediate(imm)
            image[row, base_x + 2] = low_px
            image[row, base_x + 3] = high_px

        return image


class GlyphCPUv2:
    """Fixed-width spatial CPU: PC.x always a multiple of INSTR_WIDTH."""

    def __init__(self, opcode_map: OpcodeMapV2, cols_instrs: int):
        self.opcode_map = opcode_map
        self.cols_instrs = cols_instrs
        self.registers = [0] * 32
        self.pc = (0, 0)
        self.running = False
        self.output = []
        self.current_imm = 0  # Current instruction's immediate value (for syscalls)

    def _check_alignment(self, x: int):
        if x % INSTR_WIDTH != 0:
            raise SpatialMisalignmentFault(f"PC.x={x} is not aligned to {INSTR_WIDTH}")

    def _addr_to_xy(self, image: np.ndarray, addr: int) -> Tuple[int, int]:
        """Linear-wrap: scalar address -> pixel coordinate (scanline order)."""
        height, width, _ = image.shape
        addr %= width * height
        return addr % width, addr // width

    def _mem_read(self, image: np.ndarray, addr: int) -> int:
        x, y = self._addr_to_xy(image, addr)
        r, g, b = image[y, x]
        return (int(r) << 16) | (int(g) << 8) | int(b)

    def _mem_write(self, image: np.ndarray, addr: int, value: int):
        x, y = self._addr_to_xy(image, addr)
        value &= 0xFFFFFF
        image[y, x] = ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)

    def step(self, image: np.ndarray) -> bool:
        x, y = self.pc
        self._check_alignment(x)
        height, width, _ = image.shape
        if y >= height or x >= width:
            self.running = False
            return False

        opcode_px = tuple(image[y, x])
        reg_px = tuple(image[y, x + 1])
        low_px = tuple(image[y, x + 2])
        high_px = tuple(image[y, x + 3])

        opcode = self.opcode_map.rgb_to_opcode(opcode_px)
        if opcode is None:
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
            self.registers[rd] = imm
        elif opcode == 'ADD':
            self.registers[rd] += self.registers[rs2]
        elif opcode == 'SUB':
            self.registers[rd] -= self.registers[rs2]
        elif opcode == 'AND':
            self.registers[rd] &= self.registers[rs2]
        elif opcode == 'OR':
            self.registers[rd] |= self.registers[rs2]
        elif opcode == 'XOR':
            self.registers[rd] ^= self.registers[rs2]
        elif opcode == 'SHL':
            self.registers[rd] <<= self.registers[rs2]
        elif opcode == 'SHR':
            self.registers[rd] >>= self.registers[rs2]
        elif opcode == 'CMP':
            self.registers[0] = 1 if self.registers[rd] == self.registers[rs2] else 0
        elif opcode == 'LD':
            addr = self.registers[rs2]
            self.registers[rd] = self._mem_read(image, addr)
        elif opcode == 'ST':
            # ST rd rs2 -> store rs2 into the pixel at address rd
            addr = self.registers[rd]
            self._mem_write(image, addr, self.registers[rs2])
        elif opcode == 'PUSH':
            self.registers[31] -= 1
            self._mem_write(image, self.registers[31], self.registers[rd])
        elif opcode == 'POP':
            self.registers[rd] = self._mem_read(image, self.registers[31])
            self.registers[31] += 1
        elif opcode == 'PRT':
            val = self.registers[rd]
            self.output.append(val)
            print(f"OUTPUT: r{rd} = {val}")
        elif opcode == 'CALL':
            # Save next_pc (packed) to stack and jump
            self.registers[31] -= 1
            packed_pc = (next_pc[1] << 16) | (next_pc[0] & 0xFFFF)
            self._mem_write(image, self.registers[31], packed_pc)
            
            tx, ty = imm & 0xFFFF, (imm >> 16) & 0xFFFF
            target_x = tx * INSTR_WIDTH
            self._check_alignment(target_x)
            next_pc = (target_x, ty)
        elif opcode == 'RET':
            # Pop packed_pc from stack and jump
            packed_pc = self._mem_read(image, self.registers[31])
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
            syscall_num = imm
            self.registers[rd] = self._handle_syscall(syscall_num, image)
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
        elif opcode == 'HALT':
            self.running = False
            return False

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
        - 0x10-0xFF: Reserved for Geometry OS spatial services

        Returns: syscall result (0=success, -1=error)
        """
        # Map syscall numbers to hypervisor service addresses
        # These match the GeOS hypervisor bridge constants
        SPATIAL_REGISTRY_BASE = 0x8009_0000

        if syscall_num == 0x01:  # SYSCALL_WRITE
            # Write r2 bytes from address r1 to output buffer
            addr = self.registers[1]
            length = self.registers[2]
            for i in range(length):
                val = self._mem_read(image, addr + i)
                self.output.append(val)
            print(f"[SYSCALL] WRITE: {length} bytes from addr {addr}")
            return 0

        elif syscall_num == 0x02:  # SYSCALL_READ
            # Read r2 bytes from input to address r1 (stub - returns zeros)
            addr = self.registers[1]
            length = self.registers[2]
            for i in range(length):
                self._mem_write(image, addr + i, 0)
            print(f"[SYSCALL] READ: {length} bytes to addr {addr} (stub)")
            return 0

        elif syscall_num == 0x03:  # SYSCALL_FILE_WRITE
            # Write file: r1=path_addr, r2=data_addr, r3=len (stub)
            path_addr = self.registers[1]
            data_addr = self.registers[2]
            length = self.registers[3]
            print(f"[SYSCALL] FILE_WRITE: {length} bytes from addr {data_addr} to path at {path_addr} (stub)")
            return 0

        elif syscall_num == 0x04:  # SYSCALL_FILE_READ
            # Read file: r1=path_addr, r2=data_addr, r3=len (stub)
            path_addr = self.registers[1]
            data_addr = self.registers[2]
            length = self.registers[3]
            print(f"[SYSCALL] FILE_READ: {length} bytes from path at {path_addr} to addr {data_addr} (stub)")
            return 0

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

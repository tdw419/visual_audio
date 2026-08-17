#!/usr/bin/env python3
"""CPU-side emulator of pixel-interpreter WGSL microcode. Identical semantics & memory layout."""

from pathlib import Path
import argparse
import numpy as np
from PIL import Image

# Identical to microcode.wgsl
OP_NOP   = 0
OP_SET   = 1  # Dst = Imm
OP_ADD   = 2  # Dst = SrcA + SrcB
OP_SUB   = 3  # Dst = SrcA - SrcB
OP_MUL   = 14 # Dst = SrcA * SrcB
OP_LOAD  = 4  # Dst = Memory[SrcA_coord]
OP_STORE = 5  # Memory[Dst_coord] = SrcA
OP_JMP   = 6  # PC = Imm
OP_JZ    = 7  # If Flag == 0 then PC = Imm
OP_INDIRECT_LOAD = 8  # Dst = Memory[Acc_coord] where Acc = (x << 8) | y
OP_INDIRECT_STORE = 9  # Memory[Acc_coord] = SrcA where Acc = (x << 8) | y
OP_SET_ADDR_HIGH = 10  # Acc = (imm << 8)
OP_SET_ADDR_LOW = 11   # Acc = (Acc & 0xFF00) | imm
OP_ADD_COORD = 12  # Add to y-coordinate: Acc = (x, y + imm)
OP_LOAD_COORD = 13 # Acc = (memory[G], memory[B]) - loads x,y from memory cells
OP_CALL  = 15 # Stack[SP] = PC; SP++; PC = Imm
OP_RET   = 16 # SP--; PC = Stack[SP]
OP_SEI   = 17 # Set interrupt enable flag = 1
OP_CLI   = 18 # Set interrupt enable flag = 0
OP_CTX_SAVE = 19
OP_CTX_LOAD = 20
OP_JMP_PC_IMM = 21  # Jump to packed PC in accumulator
OP_STORE_XY = 22    # Store (src_a, src_b) as RGBA at (x, y) where x=dst, y=implied
OP_POP   = 23 # SP-- (discard top of stack)
OP_DIR_RIGHT = 24
OP_DIR_DOWN = 25
OP_DIR_LEFT = 26
OP_DIR_UP = 27
OP_CH_READ = 28
OP_CH_WRITE = 29
OP_AND = 30      # Acc = Acc & imm
OP_OR  = 31      # Acc = Acc | imm
OP_XOR = 32      # Acc = Acc ^ imm
OP_SHL = 33      # Acc = Acc << imm
OP_SHR = 34      # Acc = Acc >> imm (logical, unsigned)
OP_ADD_MEM = 35  # Acc += Memory[(x,y)] -- register-to-register style ALU
OP_SUB_MEM = 36  # Acc -= Memory[(x,y)]
OP_INDIRECT_STORE_MEM = 37  # Memory[Acc_coord] = Memory[(x,y)].R -- runtime
                             # value to runtime address (Acc holds the
                             # target coord, so the value must come from a
                             # separate cell, not Acc itself)
OP_HALT  = 255

# Interrupt line: memory[0, 4].R = pending irq_num (0 = none)
# Payload cells (readable via plain LOAD, unlike G/B channels): (5,0)=x, (6,0)=y
# Vector table: memory[254, irq_num] = (handler_x, handler_y, _, _)
IRQ_CELL = (4, 0)
IRQ_PAYLOAD_X = (5, 0)
IRQ_PAYLOAD_Y = (6, 0)
IVT_ROW = 254

class PixelCPU:
    """Emulates the WGSL microcode interpreter state machine."""
    
    def __init__(self, width: int, height: int, trace: bool = False):
        self.width = width
        self.height = height
        self.memory = np.zeros((height, width, 4), dtype=np.uint32)
        self.trace = trace
        self.cycle = 0
        self.last_reads = []
        self.last_writes = []
        
        # Initialize state at row 0
        # (0,0): PC (x=0, y=1 to start in code space)
        # (1,0): Accumulator
        # (2,0): Flags (zero flag in R channel)
        # (3,0): Halt flag
        self.pc = (0, 1)
        self.accumulator = 0
        self.zero_flag = 0
        self.halt_flag = 0
        self.halt_flag = 0
        self.direction = 0  # 0=Right, 1=Down, 2=Left, 3=Up
        self.interrupts_enabled = False
        self.sp = 0
        self._write_state()
    
    def _write_state(self):
        """Write CPU state to row 0 of memory (matches WGSL layout)."""
        # (0,0): PC packed as R=x, G=y, B=halt, A=direction
        self.memory[0, 0] = [self.pc[0], self.pc[1], self.halt_flag, self.direction]
        # (1,0): Accumulator
        self.memory[0, 1] = [self.accumulator & 0xFFFFFFFF, 0, 0, 0]
        # (2,0): Flags
        self.memory[0, 2] = [self.zero_flag, 0, 0, 0]
        # (3,0): Stack Pointer
        self.memory[0, 3] = [self.sp, 0, 0, 0]
    
    def _read_state(self):
        """Read CPU state from row 0 (for verification)."""
        pc_state = self.memory[0, 0]
        self.pc = (int(pc_state[0]), int(pc_state[1]))
        self.accumulator = int(self.memory[0, 1, 0])
        self.zero_flag = int(self.memory[0, 2, 0])
        self.halt_flag = int(pc_state[2])
        self.direction = int(pc_state[3])
    
    def _fetch(self):
        """Fetch instruction at current PC."""
        if self.pc[1] >= self.height or self.pc[0] >= self.width:
            raise ValueError(f"PC out of bounds: {self.pc}")
        self.last_reads.append((self.pc[0], self.pc[1]))
        return self.memory[self.pc[1], self.pc[0]]
    
    def _log(self, msg: str):
        if self.trace:
            print(f"[Cycle {self.cycle}] {msg}")
    
    def raise_interrupt(self, irq_num: int, payload_x: int = 0, payload_y: int = 0):
        """External injection point (e.g. mouse/keyboard events from the visual shell)."""
        self.memory[IRQ_CELL[1], IRQ_CELL[0]] = np.array([irq_num, 0, 0, 0], dtype=np.uint32)
        self.memory[IRQ_PAYLOAD_X[1], IRQ_PAYLOAD_X[0]] = np.array([payload_x, 0, 0, 0], dtype=np.uint32)
        self.memory[IRQ_PAYLOAD_Y[1], IRQ_PAYLOAD_Y[0]] = np.array([payload_y, 0, 0, 0], dtype=np.uint32)

    def _check_interrupt(self):
        """Vector to the registered handler if an interrupt is pending and enabled."""
        if not self.interrupts_enabled:
            return
        irq_cell = self.memory[IRQ_CELL[1], IRQ_CELL[0]]
        irq_num = int(irq_cell[0])
        if irq_num == 0:
            return
        handler = self.memory[IVT_ROW, irq_num]
        if handler[0] == 0 and handler[1] == 0:
            return  # no handler registered for this IRQ, drop it
        # Clear the pending flag before vectoring so the handler can re-arm it.
        self.memory[IRQ_CELL[1], IRQ_CELL[0]] = np.array([0, 0, 0, 0], dtype=np.uint32)
        self.memory[255, self.sp] = np.array([self.pc[0], self.pc[1], 0, 255], dtype=np.uint32)
        self.last_writes.append((self.sp, 255))
        self.sp = (self.sp + 1) % self.width
        self.pc = (int(handler[0]), int(handler[1]))
        self._log(f"IRQ {irq_num} -> handler {self.pc}, saved return")

    def step(self) -> bool:
        """Execute one cycle. Returns True if halted."""
        self.last_reads = []
        self.last_writes = []

        if self.halt_flag:
            return True

        self._check_interrupt()

        inst = self._fetch()
        # Cast to plain Python ints: numpy uint32 arithmetic wraps silently
        # (and warns) on subtraction: keep arithmetic in unbounded Python
        # ints and only mask back to uint32 range when writing to memory.
        opcode = int(inst[0])
        src_a = int(inst[1])
        src_b = int(inst[2])
        dst = int(inst[3])

        # Calculate "true next PC" BEFORE any opcode can modify it
        # This is what CTX_SAVE should save - the address of the instruction after current
        if self.direction == 0:
            true_next_pc = ((self.pc[0] + 1) % self.width, self.pc[1])
        elif self.direction == 1:
            true_next_pc = (self.pc[0], (self.pc[1] + 1) % self.height)
        elif self.direction == 2:
            true_next_pc = ((self.pc[0] - 1) % self.width, self.pc[1])
        elif self.direction == 3:
            true_next_pc = (self.pc[0], (self.pc[1] - 1) % self.height)

        # Initialize next_pc to true_next_pc (opcodes like JMP will override this)
        next_pc = true_next_pc

        write_addr = None
        write_val = None
        
        self._log(f"PC={self.pc} OP={opcode} A={src_a} B={src_b} Dst={dst} Acc={self.accumulator}")
        if self.cycle == 99 or self.cycle == 100:
            self._log(f"DEBUG mem[1, 0] = {self.memory[1, 0]}")
        
        if opcode == OP_NOP:
            pass
        
        elif opcode == OP_SET:
            self.accumulator = dst
            self._log(f"SET {dst} -> Acc = {self.accumulator}")
        
        elif opcode == OP_ADD:
            self.accumulator = self.accumulator + src_b
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"ADD {src_b} -> Acc = {self.accumulator}, ZF={self.zero_flag}")
        
        elif opcode == OP_MUL:
            self.accumulator = self.accumulator * src_b
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"MUL {src_b} -> Acc = {self.accumulator}, ZF={self.zero_flag}")
        
        elif opcode == OP_SUB:
            self.accumulator = self.accumulator - src_b
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"SUB {src_b} -> Acc = {self.accumulator}, ZF={self.zero_flag}")

        elif opcode == OP_AND:
            self.accumulator = (self.accumulator & 0xFFFFFFFF) & src_b
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"AND {src_b} -> Acc = {self.accumulator}, ZF={self.zero_flag}")

        elif opcode == OP_OR:
            self.accumulator = (self.accumulator & 0xFFFFFFFF) | src_b
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"OR {src_b} -> Acc = {self.accumulator}, ZF={self.zero_flag}")

        elif opcode == OP_XOR:
            self.accumulator = (self.accumulator & 0xFFFFFFFF) ^ src_b
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"XOR {src_b} -> Acc = {self.accumulator}, ZF={self.zero_flag}")

        elif opcode == OP_SHL:
            self.accumulator = (self.accumulator & 0xFFFFFFFF) << src_b
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"SHL {src_b} -> Acc = {self.accumulator}, ZF={self.zero_flag}")

        elif opcode == OP_SHR:
            self.accumulator = (self.accumulator & 0xFFFFFFFF) >> src_b
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"SHR {src_b} -> Acc = {self.accumulator}, ZF={self.zero_flag}")

        elif opcode == OP_ADD_MEM:
            # Register-to-register style ALU: Acc += Memory[(x,y)].R
            x = int(src_a) % self.width
            y = int(src_b) % self.height
            cell = self.memory[y, x]
            self.last_reads.append((x, y))
            self.accumulator = self.accumulator + int(cell[0])
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"ADD_MEM ({x},{y}) -> Acc = {self.accumulator}, ZF={self.zero_flag}")

        elif opcode == OP_SUB_MEM:
            x = int(src_a) % self.width
            y = int(src_b) % self.height
            cell = self.memory[y, x]
            self.last_reads.append((x, y))
            self.accumulator = self.accumulator - int(cell[0])
            self.zero_flag = 1 if self.accumulator == 0 else 0
            self._log(f"SUB_MEM ({x},{y}) -> Acc = {self.accumulator}, ZF={self.zero_flag}")

        elif opcode == OP_STORE:
            # Unpack coordinate: G=src_a=x, B=src_b=y
            x = int(src_a) % self.width
            y = int(src_b) % self.height
            write_addr = (x, y)
            write_val = np.array([self.accumulator & 0xFFFFFFFF, 0, 0, 255], dtype=np.uint32)
            self._log(f"STORE {self.accumulator} to {write_addr}")
        
        elif opcode == OP_LOAD:
            # Unpack coordinate: G=src_a=x, B=src_b=y
            coord = (int(src_a) % self.width, int(src_b) % self.height)
            cell = self.memory[coord[1], coord[0]]
            self.last_reads.append((coord[0], coord[1]))
            self.accumulator = int(cell[0])
            self._log(f"LOAD from {coord} -> Acc = {self.accumulator}")
        
        elif opcode == OP_JMP:
            # Unpack coordinate: G=src_a=x, B=src_b=y
            x = int(src_a) % self.width
            y = int(src_b) % self.height
            next_pc = (x, y)
            self._log(f"JMP to {next_pc}")
        
        elif opcode == OP_JZ:
            # Unpack coordinate: G=src_a=x, B=src_b=y
            if self.zero_flag == 1:
                x = int(src_a) % self.width
                y = int(src_b) % self.height
                next_pc = (x, y)
                self._log(f"JZ taken to {next_pc}")
            else:
                self._log(f"JZ not taken (ZF={self.zero_flag})")
        
        elif opcode == OP_INDIRECT_LOAD:
            # Accumulator holds packed coordinate: high 8 bits = x, low 8 bits = y
            x = (self.accumulator >> 8) & 0xFF
            y = self.accumulator & 0xFF
            x = x % self.width
            y = y % self.height
            cell = self.memory[y, x]
            self.last_reads.append((x, y))
            self.accumulator = int(cell[0])
            self._log(f"INDIRECT_LOAD from ({x}, {y}) -> Acc = {self.accumulator}")
        
        elif opcode == OP_INDIRECT_STORE:
            # Accumulator holds packed coordinate: high 8 bits = x, low 8 bits = y
            x = (self.accumulator >> 8) & 0xFF
            y = self.accumulator & 0xFF
            x = x % self.width
            y = y % self.height
            # dst (A channel) holds the value to store
            write_addr = (x, y)
            write_val = np.array([dst, 0, 0, 255], dtype=np.uint32)
            self._log(f"INDIRECT_STORE {dst} to ({x}, {y})")

        elif opcode == OP_INDIRECT_STORE_MEM:
            # Acc holds packed target coord; value comes from Memory[(src_a,src_b)].R
            x = (self.accumulator >> 8) & 0xFF
            y = self.accumulator & 0xFF
            x = x % self.width
            y = y % self.height
            val_x = int(src_a) % self.width
            val_y = int(src_b) % self.height
            val_cell = self.memory[val_y, val_x]
            self.last_reads.append((val_x, val_y))
            write_addr = (x, y)
            write_val = np.array([int(val_cell[0]) & 0xFFFFFFFF, 0, 0, 255], dtype=np.uint32)
            self._log(f"INDIRECT_STORE_MEM ({val_x},{val_y})={val_cell[0]} to ({x}, {y})")
        
        elif opcode == OP_CH_READ:
            # dst is channel (0-3)
            x = (self.accumulator >> 8) & 0xFF
            y = self.accumulator & 0xFF
            x = x % self.width
            y = y % self.height
            cell = self.memory[y, x]
            self.last_reads.append((x, y))
            channel = dst % 4
            self.accumulator = int(cell[channel])
            self._log(f"CH_READ ch {channel} from ({x}, {y}) -> Acc = {self.accumulator}")
            
        elif opcode == OP_CH_WRITE:
            # dst is channel (0-3), src_a/src_b is memory coordinate of value
            x = (self.accumulator >> 8) & 0xFF
            y = self.accumulator & 0xFF
            x = x % self.width
            y = y % self.height
            channel = dst % 4
            
            val_x = int(src_a) % self.width
            val_y = int(src_b) % self.height
            val = int(self.memory[val_y, val_x][0])  # Read from R channel of source
            
            write_addr = (x, y)
            current_pixel = self.memory[y, x].copy()
            current_pixel[channel] = val
            write_val = current_pixel
            self._log(f"CH_WRITE_MEM val={val} from ({val_x}, {val_y}) to ch {channel} at ({x}, {y})")

        elif opcode == OP_SET_ADDR_HIGH:
            # Set high byte of accumulator (x coordinate)
            self.accumulator = (dst << 8) | (self.accumulator & 0xFF)
            self._log(f"SET_ADDR_HIGH {dst} -> Acc = {self.accumulator}")
        
        elif opcode == OP_SET_ADDR_LOW:
            # Set low byte of accumulator (y coordinate)
            self.accumulator = (self.accumulator & 0xFF00) | dst
            self._log(f"SET_ADDR_LOW {dst} -> Acc = {self.accumulator}")
        
        elif opcode == OP_ADD_COORD:
            # Add to y-coordinate: Acc = (x, y + imm)
            y = (self.accumulator & 0xFF) + dst
            x = (self.accumulator >> 8) & 0xFF
            self.accumulator = (x << 8) | y
            self._log(f"ADD_COORD {dst} -> Acc = {self.accumulator}")
        
        elif opcode == OP_LOAD_COORD:
            # Load x from (src_a, 0) and y from (src_b, 0)
            x = int(self.memory[0, src_a][0])
            y = int(self.memory[0, src_b][0])
            self.last_reads.extend([(src_a, 0), (src_b, 0)])
            self.accumulator = (x << 8) | y
            self._log(f"LOAD_COORD from ({src_a}, 0)=x={x}, ({src_b}, 0)=y={y} -> Acc = {self.accumulator}")
        
        elif opcode == OP_CALL:
            stack_addr = (self.sp, 255)
            self.memory[255, self.sp] = np.array([next_pc[0], next_pc[1], 0, 255], dtype=np.uint32)
            self.last_writes.append(stack_addr)
            self.sp = (self.sp + 1) % self.width
            x = int(src_a) % self.width
            y = int(src_b) % self.height
            next_pc = (x, y)
            self._log(f"CALL to {next_pc}, saving return {stack_addr}")
            
        elif opcode == OP_RET:
            self.sp = (self.sp - 1) % self.width
            stack_addr = (self.sp, 255)
            ret_val = self.memory[255, self.sp]
            self.last_reads.append(stack_addr)
            next_pc = (int(ret_val[0]), int(ret_val[1]))
            self._log(f"RET to {next_pc} from {stack_addr}")

        elif opcode == OP_POP:
            # Discard top of stack: SP--
            self.sp = (self.sp - 1) % self.width
            self._log(f"POP -> SP = {self.sp}")

        elif opcode == OP_SEI:
            self.interrupts_enabled = True
            self._log("SEI -> interrupts enabled")

        elif opcode == OP_CLI:
            self.interrupts_enabled = False
            self._log("CLI -> interrupts disabled")

        elif opcode == OP_CTX_SAVE:
            # DO NOT change this to save true_next_pc / next_pc. See the
            # note in memory: pixel-interpreter-call-ret-verified.md --
            # this has regressed scheduler.glyph three times now. CTX_SAVE
            # pops the row-255 hardware stack (matching what
            # _check_interrupt / CALL already pushed there), it does not
            # capture "the next instruction after CTX_SAVE itself".
            self.sp = (self.sp - 1) % self.width
            pop_stack_addr = (self.sp, 255)
            ret_val = self.memory[255, self.sp]
            pc_x, pc_y = int(ret_val[0]), int(ret_val[1])
            x = int(src_a) % self.width
            y = int(src_b) % self.height
            self.memory[y, x] = [pc_x, pc_y, 0, 255]
            self.memory[(y+1)%self.height, x] = [self.accumulator & 0xFFFFFFFF, 0, 0, 255]
            self.memory[(y+2)%self.height, x] = [self.sp, 0, 0, 255]
            self.memory[(y+3)%self.height, x] = [self.zero_flag, 0, 0, 255]
            self.last_reads.append(pop_stack_addr)
            self.last_writes.extend([(x, y), (x, (y+1)%self.height), (x, (y+2)%self.height), (x, (y+3)%self.height)])
            self._log(f"CTX_SAVE to PCB at ({x}, {y}), saved PC=({pc_x}, {pc_y})")
            
        elif opcode == OP_CTX_LOAD:
            x = int(src_a) % self.width
            y = int(src_b) % self.height
            # Read PCB
            pc_val = self.memory[y, x]
            pc_x = int(pc_val[0])
            pc_y = int(pc_val[1])
            new_acc = int(self.memory[(y+1)%self.height, x][0])
            new_sp = int(self.memory[(y+2)%self.height, x][0])
            new_zf = int(self.memory[(y+3)%self.height, x][0])
            # Restore registers
            self.accumulator = new_acc
            self.sp = new_sp
            self.zero_flag = new_zf
            # Push the saved PC onto stack for RET to use later
            stack_addr = (self.sp, 255)
            self.memory[255, self.sp] = [pc_x, pc_y, 0, 255]
            self.sp = (self.sp + 1) % self.width
            self.last_reads.extend([(x, y), (x, (y+1)%self.height), (x, (y+2)%self.height), (x, (y+3)%self.height)])
            self.last_writes.append(stack_addr)
            self._log(f"CTX_LOAD from PCB at ({x}, {y}) -> restored Acc/SP/ZF, pushed PC to stack")

        elif opcode == OP_JMP_PC_IMM:
            # Jump to packed PC in accumulator: high byte = x, low byte = y
            pc_x = (self.accumulator >> 8) & 0xFF
            pc_y = self.accumulator & 0xFF
            next_pc = (pc_x, pc_y)
            self._log(f"JMP_PC_IMM to {next_pc}")

        elif opcode == OP_STORE_XY:
            # Takes immediate: STORE_XY x_coord y_coord (packed in G and B)
            # Used for initializing PCB PC values
            dst_x = int(src_a) % self.width
            dst_y = int(src_b) % self.height
            self.memory[dst_y, dst_x] = [src_a, src_b, 0, 255]
            self.last_writes.append((dst_x, dst_y))
            self._log(f"STORE_XY to ({dst_x}, {dst_y}) = ({src_a}, {src_b})")

        elif opcode == OP_HALT:
            self.halt_flag = 1
            self._log("HALT")
        
        elif opcode == OP_DIR_RIGHT:
            self.direction = 0
            next_pc = ((self.pc[0] + 1) % self.width, self.pc[1])
            self._log("DIR_RIGHT")
        elif opcode == OP_DIR_DOWN:
            self.direction = 1
            next_pc = (self.pc[0], (self.pc[1] + 1) % self.height)
            self._log("DIR_DOWN")
        elif opcode == OP_DIR_LEFT:
            self.direction = 2
            next_pc = ((self.pc[0] - 1) % self.width, self.pc[1])
            self._log("DIR_LEFT")
        elif opcode == OP_DIR_UP:
            self.direction = 3
            next_pc = (self.pc[0], (self.pc[1] - 1) % self.height)
            self._log("DIR_UP")
        
        else:
            self._log(f"Unknown opcode {opcode} - treating as NOP")
        
        # Apply state changes
        self.pc = next_pc
        if write_addr is not None:
            self.memory[write_addr[1], write_addr[0]] = write_val
            self.last_writes.append((write_addr[0], write_addr[1]))
        
        self._write_state()
        self.cycle += 1
        return self.halt_flag == 1
    
    def load_program(self, img_path: Path):
        """Load program image (PNG) into memory."""
        img = Image.open(img_path).convert("RGBA")
        img = img.resize((self.width, self.height), Image.Resampling.NEAREST)
        prog = np.asarray(img, dtype=np.uint32)
        
        # Preserve state row (y=0) if program doesn't set it
        state_row = self.memory[0].copy()
        self.memory = prog.reshape(self.height, self.width, 4).copy()
        self.memory[0] = state_row

    def mount_vfs(self, img_path: Path, x_offset: int, y_offset: int):
        """Mount a read-only texture sub-rectangle into memory."""
        img = Image.open(img_path).convert("RGBA")
        prog = np.asarray(img, dtype=np.uint32)
        h, w, _ = prog.shape
        
        # Clip to bounds
        max_h = min(h, self.height - y_offset)
        max_w = min(w, self.width - x_offset)
        
        if max_h > 0 and max_w > 0:
            self.memory[y_offset:y_offset+max_h, x_offset:x_offset+max_w] = prog[:max_h, :max_w]
            self._log(f"Mounted VFS '{img_path}' at ({x_offset}, {y_offset}) size {max_w}x{max_h}")
        
        # Re-sync state from memory in case program set it
        self._read_state()
        self._write_state()
        self._log(f"Loaded program from {img_path}")
    
    def run(self, max_cycles: int = 1000) -> dict:
        """Run until halt or max_cycles. Returns execution stats."""
        if self.trace:
            print(f"=== Starting execution (max {max_cycles} cycles) ===")
        
        halted = False
        for _ in range(max_cycles):
            if self.step():
                halted = True
                break
        
        return {
            "halted": halted,
            "cycles": self.cycle,
            "pc": self.pc,
            "accumulator": self.accumulator,
            "zero_flag": self.zero_flag,
            "halt_flag": self.halt_flag,
        }
    
    def save_state_image(self, out_path: Path):
        """Save current memory state as PNG for inspection or WGSL input."""
        img = Image.fromarray(self.memory.astype(np.uint8))
        img.save(out_path)
        self._log(f"Saved state image to {out_path}")
    
    def dump_state(self):
        """Print current CPU state (row 0 of memory)."""
        print(f"=== CPU State (Cycle {self.cycle}) ===")
        print(f"PC: ({self.pc[0]}, {self.pc[1]})")
        print(f"Accumulator: {self.accumulator}")
        print(f"Zero Flag: {self.zero_flag}")
        print(f"Halt Flag: {self.halt_flag}")
        print(f"Memory[{self.height}x{self.width}]")

def create_test_program_png(out_path: Path, width: int = 256, height: int = 256):
    """Create a test program: SET 5; ADD 3; SUB 8; HALT."""
    mem = np.zeros((height, width, 4), dtype=np.uint8)
    
    # State row (y=0) - CPU will initialize this
    mem[0, 0] = [0, 1, 0, 0]  # PC at (0, 1)
    mem[0, 1] = [0, 0, 0, 0]  # Acc = 0
    mem[0, 2] = [0, 0, 0, 0]  # ZF = 0
    
    # Code space starts at y=1
    # Instruction encoding: R=opcode, G=src_a, B=src_b, A=dst/imm
    
    # (0, 1): OP_SET | (0 << 8) | (0 << 16) | (5 << 24)
    mem[1, 0] = [OP_SET, 0, 0, 5]
    
    # (1, 1): OP_ADD | (0 << 8) | (3 << 16) | (0 << 24)  -- Acc += 3
    mem[1, 1] = [OP_ADD, 0, 3, 0]
    
    # (2, 1): OP_SUB | (0 << 8) | (8 << 16) | (0 << 24)  -- Acc -= 8
    mem[1, 2] = [OP_SUB, 0, 8, 0]
    
    # (3, 1): OP_HALT
    mem[1, 3] = [OP_HALT, 0, 0, 0]
    
    img = Image.fromarray(mem)
    img.save(out_path)
    print(f"Created test program at {out_path}")
    return mem

def main():
    parser = argparse.ArgumentParser(description="CPU emulator for pixel-interpreter ISA")
    parser.add_argument("program", type=Path, nargs="?", help="Program PNG (default: create test program)")
    parser.add_argument("-w", "--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("-c", "--cycles", type=int, default=1000, help="Max cycles")
    parser.add_argument("-t", "--trace", action="store_true", help="Trace execution")
    parser.add_argument("-o", "--output", type=Path, help="Save final state as PNG")
    args = parser.parse_args()
    
    # Create test program if none provided
    if args.program is None:
        args.program = Path("/tmp/pixel_test_set5.png")
        create_test_program_png(args.program, args.width, args.height)
    
    # Initialize CPU
    cpu = PixelCPU(args.width, args.height, trace=args.trace)
    cpu.load_program(args.program)
    cpu.dump_state()
    
    # Run
    stats = cpu.run(args.cycles)
    
    print("\n=== Execution Complete ===")
    print(f"Halted: {stats['halted']}")
    print(f"Cycles: {stats['cycles']}")
    print(f"Final PC: {stats['pc']}")
    print(f"Final Accumulator: {stats['accumulator']}")
    print(f"Final Zero Flag: {stats['zero_flag']}")
    
    if args.program == Path("/tmp/pixel_test_set5.png"):
        # Built-in default test program: 5 + 3 - 8 = 0, so ZF=1
        expected_acc, expected_zf = 0, 1
        if stats['accumulator'] == expected_acc and stats['zero_flag'] == expected_zf:
            print(f"✓ PASS: Acc={stats['accumulator']} (expected {expected_acc}), ZF={stats['zero_flag']} (expected {expected_zf})")
            exit_code = 0
        else:
            print(f"✗ FAIL: Acc={stats['accumulator']} (expected {expected_acc}), ZF={stats['zero_flag']} (expected {expected_zf})")
            exit_code = 1
    else:
        exit_code = 0
    
    # Save final state if requested
    if args.output:
        cpu.save_state_image(args.output)
    
    sys.exit(exit_code)

if __name__ == "__main__":
    import sys
    main()
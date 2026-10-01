#!/usr/bin/env python3
"""CuPy-based pixel interpreter using CUDA kernels on RTX 5090."""

from pathlib import Path
import argparse
import numpy as np

try:
    import cupy as cp
    HAS_CUPY = True
except ImportError:
    print("CuPy not available. Install with: pip install cupy-cuda12x")
    HAS_CUPY = False
    exit(1)

# Opcodes match cpu_emulator.py
OP_NOP   = 0
OP_SET   = 1
OP_ADD   = 2
OP_SUB   = 3
OP_LOAD  = 4
OP_STORE = 5
OP_JMP   = 6
OP_JZ    = 7
OP_HALT  = 255

# CUDA kernel implementing the microcode interpreter
CUDA_KERNEL = r"""
extern "C" __global__
void pixel_interpreter_step(
    unsigned int* memory,
    int width,
    int height
) {
    int global_x = blockIdx.x * blockDim.x + threadIdx.x;
    int global_y = blockIdx.y * blockDim.y + threadIdx.y;
    
    if (global_x >= width || global_y >= height) {
        return;
    }
    
    // State row at y = 0: (0,0)=PC, (1,0)=Acc, (2,0)=Flags
    unsigned int pc_state  = memory[0 * width + 0];  // R:pc_x, G:pc_y, B:halt, A:reserved
    unsigned int pc_x      = pc_state & 0xFF;
    unsigned int pc_y      = (pc_state >> 8) & 0xFF;
    unsigned int halt_flag = (pc_state >> 16) & 0xFF;
    
    if (halt_flag == 1) {
        return;  // Halted
    }
    
    unsigned int reg_acc  = memory[0 * width + 1];  // R:accumulator
    unsigned int reg_flag = memory[0 * width + 2];  // R:zero_flag
    
    // Instruction fetch at PC
    unsigned int inst = memory[pc_y * width + pc_x];
    unsigned int opcode = inst & 0xFF;
    unsigned int src_a  = (inst >> 8) & 0xFF;
    unsigned int src_b  = (inst >> 16) & 0xFF;
    unsigned int dst    = (inst >> 24) & 0xFF;
    
    unsigned int next_pc_x = pc_x + 1;
    unsigned int next_pc_y = pc_y;
    
    int write_x = -1;
    int write_y = -1;
    unsigned int write_val = 0;
    
    switch (opcode) {
        case 0:  // NOP
            break;
            
        case 1:  // SET
            reg_acc = dst;
            break;
            
        case 2:  // ADD
            reg_acc = reg_acc + src_b;
            reg_flag = (reg_acc == 0) ? 1 : 0;
            break;
            
        case 3:  // SUB
            reg_acc = reg_acc - src_b;
            reg_flag = (reg_acc == 0) ? 1 : 0;
            break;
            
        case 4:  // LOAD
        {
            int coord_x = src_a % width;
            int coord_y = src_b % height;
            unsigned int cell = memory[coord_y * width + coord_x];
            reg_acc = cell & 0xFF;
            break;
        }
        
        case 5:  // STORE
        {
            write_x = src_a % width;
            write_y = src_b % height;
            write_val = (reg_acc & 0xFF) | (255 << 24);  // R=acc, A=255
            break;
        }
        
        case 6:  // JMP
            next_pc_x = src_a % width;
            next_pc_y = src_b % height;
            break;
            
        case 7:  // JZ
            if (reg_flag == 1) {
                next_pc_x = src_a % width;
                next_pc_y = src_b % height;
            }
            break;
            
        case 255:  // HALT
            halt_flag = 1;
            break;
            
        default:
            break;
    }
    
    // Write back state (only first thread does this)
    if (threadIdx.x == 0 && threadIdx.y == 0 && blockIdx.x == 0 && blockIdx.y == 0) {
        pc_state = pc_x | (pc_y << 8) | (halt_flag << 16);
        memory[0 * width + 0] = pc_state;
        memory[0 * width + 1] = reg_acc;
        memory[0 * width + 2] = reg_flag;
    }
    
    // Handle store (atomic to avoid conflicts)
    if (write_x >= 0) {
        atomicAdd(&memory[write_y * width + write_x], write_val);
    }
}
"""

class CupyPixelCPU:
    """CUDA-based pixel interpreter using CuPy."""
    
    def __init__(self, width: int = 256, height: int = 256):
        self.width = width
        self.height = height
        self.kernel = cp.RawKernel(CUDA_KERNEL, "pixel_interpreter_step")
        
        # Initialize GPU memory
        self.memory_gpu = cp.zeros((height, width, 4), dtype=cp.uint8)
        self._init_state()
    
    def _init_state(self):
        """Initialize state row at y=0."""
        # PC starts at (0, 1)
        self.memory_gpu[0, 0] = [0, 1, 0, 0]  # PC=(0,1), halt=0
        self.memory_gpu[0, 1] = [0, 0, 0, 0]  # Acc=0
        self.memory_gpu[0, 2] = [0, 0, 0, 0]  # ZF=0
    
    def load_program(self, img_path: Path):
        """Load program PNG to GPU memory."""
        from PIL import Image
        img = Image.open(img_path).convert("RGBA")
        img = img.resize((self.width, self.height), Image.Resampling.NEAREST)
        prog = np.asarray(img, dtype=np.uint8)
        
        # Preserve state row
        state_row = self.memory_gpu[0].copy()
        self.memory_gpu[:] = cp.asarray(prog.reshape(self.height, self.width, 4))
        self.memory_gpu[0] = state_row
    
    def step(self) -> bool:
        """Execute one GPU cycle. Returns True if halted."""
        # Check if halted
        halt_flag = self.memory_gpu[0, 0, 2]
        if halt_flag == 1:
            return True
        
        # Launch kernel
        block_size = (16, 16, 1)
        grid_size = ((self.width + 15) // 16, (self.height + 15) // 16, 1)
        
        # Flatten memory for CUDA kernel
        mem_flat = self.memory_gpu.flatten()
        self.kernel(
            grid_size,
            block_size,
            (mem_flat, self.width, self.height)
        )
        
        return False
    
    def run(self, max_cycles: int = 1000, trace: bool = False) -> dict:
        """Run until halt or max_cycles."""
        for cycle in range(max_cycles):
            halted = self.step()
            if trace and cycle % 10 == 0:
                pc = (int(self.memory_gpu[0, 0, 0]), int(self.memory_gpu[0, 0, 1]))
                acc = int(self.memory_gpu[0, 1, 0])
                zf = int(self.memory_gpu[0, 2, 0])
                print(f"Cycle {cycle}: PC={pc}, Acc={acc}, ZF={zf}")
            
            if halted:
                return {
                    "halted": True,
                    "cycles": cycle + 1,
                    "pc": (int(self.memory_gpu[0, 0, 0]), int(self.memory_gpu[0, 0, 1])),
                    "accumulator": int(self.memory_gpu[0, 1, 0]),
                    "zero_flag": int(self.memory_gpu[0, 2, 0]),
                    "halt_flag": int(self.memory_gpu[0, 0, 2]),
                }
        
        return {
            "halted": False,
            "cycles": max_cycles,
            "pc": (int(self.memory_gpu[0, 0, 0]), int(self.memory_gpu[0, 0, 1])),
            "accumulator": int(self.memory_gpu[0, 1, 0]),
            "zero_flag": int(self.memory_gpu[0, 2, 0]),
            "halt_flag": int(self.memory_gpu[0, 0, 2]),
        }
    
    def save_state_image(self, out_path: Path):
        """Save GPU memory state as PNG."""
        from PIL import Image
        img = Image.fromarray(cp.asnumpy(self.memory_gpu).astype(np.uint8))
        img.save(out_path)

def main():
    parser = argparse.ArgumentParser(description="CUDA pixel interpreter using RTX 5090")
    parser.add_argument("program", type=Path, nargs="?", help="Program PNG")
    parser.add_argument("--width", type=int, default=256)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("-c", "--cycles", type=int, default=1000)
    parser.add_argument("-t", "--trace", action="store_true")
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    
    # Create test program if none provided
    if args.program is None:
        args.program = Path("/tmp/pixel_test_cuda.png")
        prog = np.zeros((16, 16, 4), dtype=np.uint8)
        prog[1, 0] = [OP_SET, 0, 0, 5]
        prog[1, 1] = [OP_ADD, 0, 3, 0]
        prog[1, 2] = [OP_SUB, 0, 8, 0]
        prog[1, 3] = [OP_HALT, 0, 0, 0]
        from PIL import Image
        Image.fromarray(prog).save(args.program)
        print(f"Created test program: {args.program}")
    
    # Run on CUDA
    cpu = CupyPixelCPU(args.width, args.height)
    cpu.load_program(args.program)
    
    print(f"GPU: {cp.cuda.Device()}")
    print(f"Memory: {cp.cuda.Device().mem_info[0] / 1024**3:.1f}GB free")
    print()
    
    stats = cpu.run(args.cycles, trace=args.trace)
    
    print("\n=== Execution Complete ===")
    print(f"Halted: {stats['halted']}")
    print(f"Cycles: {stats['cycles']}")
    print(f"Final PC: {stats['pc']}")
    print(f"Accumulator: {stats['accumulator']}")
    print(f"Zero Flag: {stats['zero_flag']}")
    
    # Verify
    expected_acc = 0
    expected_zf = 1
    if stats['accumulator'] == expected_acc and stats['zero_flag'] == expected_zf:
        print(f"\n✓ CUDA GPU EXECUTION PASSED on RTX 5090")
        exit_code = 0
    else:
        print(f"\n✗ CUDA GPU EXECUTION FAILED")
        exit_code = 1
    
    if args.output:
        cpu.save_state_image(args.output)
        print(f"Saved state: {args.output}")
    
    exit(exit_code)

if __name__ == "__main__":
    main()
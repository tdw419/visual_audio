import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from rv64i_checkpoint import load_checkpoint

CSR_MCAUSE = 0x342
CSR_SCAUSE = 0x142
CSR_STVAL = 0x143
CSR_SEPC = 0x141
CSR_SATP = 0x180

def trace():
    print("Loading checkpoint...")
    core = load_checkpoint("/tmp/init_run.rv64ckpt")
    
    state = core.get_state()
    print(f"Initial: PC=0xffffffff{state['pc_low']:08x}, satp={hex(core.read_csr(CSR_SATP))}")
    
    # Step in 100k-step chunks to find where PC becomes 0xffffffff8008ede4
    steps_total = 0
    for chunk_idx in range(120):
        core.step(100000)
        steps_total += 100000
        state = core.get_state()
        pc = (state['pc_high'] << 32) | state['pc_low']
        scause = core.read_csr(CSR_SCAUSE)
        sepc = core.read_csr(CSR_SEPC)
        stval = core.read_csr(CSR_STVAL)
        uart = core.read_uart_output()
        if uart:
            print(f"[{steps_total:,} steps] UART: {uart!r}")
        
        print(f"[{steps_total:,} steps] PC=0x{pc:016x} scause=0x{scause:016x} sepc=0x{sepc:016x} stval=0x{stval:016x}")
        if pc == 0xffffffff8008ede4 or state['halted']:
            print("Reached target or halted.")
            # Print general purpose registers
            reg_bytes = core.queue.read_buffer(core.registers.buffer)
            regs = np.frombuffer(reg_bytes, dtype=np.uint64)
            REG_NAMES = [
                "zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2",
                "fp", "s1", "a0", "a1", "a2", "a3", "a4", "a5",
                "a6", "a7", "s2", "s3", "s4", "s5", "s6", "s7",
                "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"
            ]
            for i, val in enumerate(regs):
                print(f"  {REG_NAMES[i]:>4} (x{i:02d}): 0x{val:016x}")
            break

if __name__ == "__main__":
    trace()

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'tools')))
from spatial_rv64i_cpu import SpatialRV64ICore
import numpy as np

core = SpatialRV64ICore(1024 * 1024)

instr_lui = (0x80000 << 12) | (2 << 7) | 0x37
instr_addi = (99 << 20) | (0 << 15) | (0 << 12) | (3 << 7) | 0x13
instr_sw = (0 << 25) | (2 << 20) | (3 << 15) | (2 << 12) | (0 << 7) | 0x23
instr_lw = (0 << 20) | (2 << 15) | (2 << 12) | (4 << 7) | 0x03

core.write_mem_word(0, instr_lui)
core.write_mem_word(4, instr_addi)
core.write_mem_word(8, instr_sw)
core.write_mem_word(12, instr_lw)

core.write_mem_word(0x1000, 0xF)          # VA 0 -> PA 0
core.write_mem_word(0x1000 + 0x1FE * 8, (2 << 10) | 0xF)  # VA 0xFFFFFFFF80000000 -> PA 0x2000

satp_val = (8 << 60) | 1
core.write_csr(0x180, satp_val)
core.set_mode(1)

core.queue.write_buffer(core.state_buffer, 0, np.array([0, 0], dtype=np.uint32).tobytes())

for i in range(4):
    core.step()
    state = core.get_state()
    cause = core.read_csr(0x342)
    print(f"Step {i}: pc={state['pc_low']:x} halted={state['halted']} cause={cause:x} x4={state['regs'][4]}")

print(f"PA 0x2000 = {core.read_mem_word(0x2000)}")

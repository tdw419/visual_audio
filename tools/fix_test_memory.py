import re

with open('tools/test_mmu_gpu.py', 'r') as f:
    code = f.read()

# Replace memory allocation to use shape (N, 4)
code = re.sub(
    r'memory = np.zeros\(mem_size, dtype=np.uint32\)',
    'memory = np.zeros((mem_size, 4), dtype=np.uint32)',
    code, flags=re.DOTALL
)

# Helper to write to memory
code = code.replace(
    'memory[ROOT_PT_ADDR//4 + 1] = (L2_PT_PPN << 10) | PTE_V',
    '''val = (L2_PT_PPN << 10) | PTE_V
    memory[ROOT_PT_ADDR//4 + 1] = [val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >> 24) & 0xFF]'''
)

code = code.replace(
    'memory[L2_PT_ADDR//4 + 0] = (L3_PT_PPN << 10) | PTE_V',
    '''val = (L3_PT_PPN << 10) | PTE_V
    memory[L2_PT_ADDR//4 + 0] = [val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >> 24) & 0xFF]'''
)

code = code.replace(
    'memory[L3_PT_ADDR//4 + 0] = (TARGET_PPN << 10) | PTE_V | PTE_R | PTE_W | PTE_X',
    '''val = (TARGET_PPN << 10) | PTE_V | PTE_R | PTE_W | PTE_X
    memory[L3_PT_ADDR//4 + 0] = [val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >> 24) & 0xFF]'''
)

code = code.replace(
    'memory[TARGET_ADDR//4 + i] = inst',
    'memory[TARGET_ADDR//4 + i] = [inst & 0xFF, (inst >> 8) & 0xFF, (inst >> 16) & 0xFF, (inst >> 24) & 0xFF]'
)

with open('tools/test_mmu_gpu.py', 'w') as f:
    f.write(code)


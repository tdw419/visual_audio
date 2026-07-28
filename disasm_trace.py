import json
import capstone
from tools.hybrid_kernel_loader import HybridKernelLoader

loader, fmt = HybridKernelLoader.load('boot_images/alpine_Image')
seg = loader.get_loadable_segments()[0]
data = loader.get_segment_data(seg)

md = capstone.Cs(capstone.CS_ARCH_RISCV, capstone.CS_MODE_RISCV64 | capstone.CS_MODE_RISCVC)

with open('trace.jsonl') as f:
    for line in f:
        if not line.startswith('{'): continue
        try:
            entry = json.loads(line)
        except:
            continue
        pc = entry['pc']
        if pc < 0x80200000:
            print(f"PC {hex(pc)} is outside image!")
            continue
        
        offset = pc - 0x80200000
        rva = offset # virtual_address is 0
        
        # actually for alpine, seg['virtual_address'] is 0x200000?
        # let's just find the offset by subtracting seg['virtual_address']?
        # earlier I used: offset_in_seg = pc - 0x80200000 - seg['virtual_address']
        offset_in_seg = offset - seg['virtual_address']
        
        if 0 <= offset_in_seg < len(data):
            instr_bytes = data[offset_in_seg:offset_in_seg+4]
            disasm = list(md.disasm(instr_bytes, pc))
            if disasm:
                i = disasm[0]
                print(f"[{entry['instr_count']:>2}] 0x{pc:x}: {i.mnemonic:10} {i.op_str}")
                
            else:
                print(f"[{entry['instr_count']:>2}] 0x{pc:x}: Failed to disasm {instr_bytes.hex()}")
        else:
            print(f"[{entry['instr_count']:>2}] 0x{pc:x}: Out of bounds")

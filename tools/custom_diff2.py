import json
import re

qemu = []
with open('/tmp/qemu_exec_trace2.log') as f:
    for line in f:
        # Trace 0: 0x7d38d4000100 [00000000/0000000000001000/0b024003/ff020201] 
        m = re.search(r'\[00000000/([0-9a-f]+)/', line)
        if m:
            qemu.append(int(m.group(1), 16))

gpu = []
with open('/tmp/gpu_trace.jsonl') as f:
    for line in f:
        # GPU trace records the PC of the NEXT instruction (after executing 'instr')
        gpu.append(json.loads(line)['pc'])

# Find PC 0x80000004 in QEMU
q_start = 0
for i, pc in enumerate(qemu):
    if pc == 0x80000004:
        q_start = i
        break

print(f"Aligned: QEMU start={q_start}, GPU start=0")

for i in range(min(len(gpu), len(qemu) - q_start)):
    q_pc = qemu[q_start + i]
    g_pc = gpu[i]
    
    if q_pc != g_pc:
        print(f"Divergence at step {i}:")
        print(f"  QEMU PC: {hex(q_pc)}")
        print(f"  GPU PC:  {hex(g_pc)}")
        break
else:
    print(f"Traces match for {len(gpu)} instructions!")


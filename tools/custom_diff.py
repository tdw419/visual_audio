import json

qemu = []
with open('/tmp/qemu_trace.jsonl') as f:
    for line in f:
        qemu.append(json.loads(line))

gpu = []
with open('/tmp/gpu_trace.jsonl') as f:
    for line in f:
        gpu.append(json.loads(line))

# Find PC 0x80000000 in QEMU
q_start = 0
for i, e in enumerate(qemu):
    if e['pc'] == 0x80000000:
        q_start = i
        break

# In GPU, the first entry is after executing 0x80000000.
# So gpu[0] state corresponds to QEMU state after executing 0x80000000, 
# which is QEMU state BEFORE executing qemu[q_start+1].

print(f"Aligned: QEMU start={q_start}, GPU start=0")

for i in range(min(len(gpu), len(qemu) - q_start - 1)):
    q_entry = qemu[q_start + i + 1] # State BEFORE next instruction
    g_entry = gpu[i] # State AFTER this instruction
    
    q_pc = q_entry['pc']
    g_pc = g_entry['pc']
    
    if q_pc != g_pc:
        print(f"Divergence at step {i}:")
        print(f"  QEMU Next PC: {hex(q_pc)}")
        print(f"  GPU Next PC:  {hex(g_pc)}")
        print(f"  GPU just executed: {g_entry.get('instr', 'N/A')}")
        break


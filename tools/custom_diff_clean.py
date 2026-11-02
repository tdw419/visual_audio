import json, re

qemu = []
with open('/tmp/qemu_exec_trace2.log') as f:
    for line in f:
        m = re.search(r'\[00000000/([0-9a-f]+)/', line)
        if m:
            pc = int(m.group(1), 16)
            if not qemu or qemu[-1] != pc:  # Ignore consecutive duplicates
                qemu.append(pc)

gpu = []
with open('/tmp/gpu_trace.jsonl') as f:
    for line in f:
        gpu.append(json.loads(line)['pc'])

q_start = qemu.index(0x80000004)
print(f"Aligned: QEMU start={q_start}, GPU start=0")

for i in range(min(len(gpu), len(qemu) - q_start)):
    q_pc = qemu[q_start + i]
    g_pc = gpu[i]
    
    if q_pc != g_pc:
        # Check if the difference is just a different number of UART spins
        # QEMU's UART might return ready sooner than GPU's UART
        if q_pc in (0x80000c80, 0x80000c78) and g_pc in (0x80000c80, 0x80000c78):
            pass # We could try to sync them up, but let's just print where they diverge
        
        print(f"Divergence at step {i}:")
        print(f"  QEMU PC: {hex(q_pc)}")
        print(f"  GPU PC:  {hex(g_pc)}")
        # Print a few instructions before and after
        print("QEMU Context:")
        for j in range(max(0, i - 3), i + 3):
            print(f"  {j}: {hex(qemu[q_start + j])}")
        print("GPU Context:")
        for j in range(max(0, i - 3), i + 3):
            print(f"  {j}: {hex(gpu[j])}")
        break
else:
    print(f"Traces match for {len(gpu)} instructions!")


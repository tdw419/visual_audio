import json, sys
def load(f):
    out = []
    with open(f) as file:
        for line in file:
            data = json.loads(line)
            pc = data['pc']
            if not out or out[-1] != pc:
                out.append(pc)
    return out

g = load('/tmp/gpu_1000.jsonl')
q = load('/tmp/qemu_1000.jsonl')
start = 0
for i in range(100):
    if q[i] == g[0]:
        start = i
        break
q = q[start:]
for i in range(min(len(q), len(g))):
    if q[i] != g[i]:
        print(f"Mismatch at step {i}: QEMU={hex(q[i])}, GPU={hex(g[i])}")
        print(f"Context GPU: {[hex(x) for x in g[i-5:i+5]]}")
        print(f"Context QEMU: {[hex(x) for x in q[i-5:i+5]]}")
        sys.exit(1)
print("MATCH!")

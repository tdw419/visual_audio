import sys, json
from qemu_cpu_trace import parse_qemu_trace

if len(sys.argv) != 3:
    print("Usage: python3 convert_qemu_to_jsonl.py <input> <output>")
    sys.exit(1)

entries, _ = parse_qemu_trace(sys.argv[1])
with open(sys.argv[2], 'w') as f:
    for e in entries:
        json.dump({'pc': e['pc'], 'opcode': e.get('opcode', ''), 'mnemonic': e.get('mnemonic', ''), 'operands': e.get('operands', '')}, f)
        f.write('\n')

import json
with open('trace.jsonl') as f:
    for line in f:
        if not line.startswith('{'): continue
        try:
            entry = json.loads(line)
        except:
            continue
        pc = entry['pc']
        print(f"[{entry['instr_count']:>2}] PC: {hex(pc)}")

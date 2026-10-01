import json
with open('/tmp/qemu_1000.jsonl') as f:
    for line in f:
        data = json.loads(line)
        print(f"{hex(data['pc'])}")

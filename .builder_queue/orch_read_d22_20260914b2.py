"""Orchestrator read of DEFECT-22 ticket non-ledger fields (compact digest)."""
import json

d = json.load(open('.builder_queue/DEFECT-22_arc_legA_instability.json'))
skip_prefix = ('ledger_',)
for k, v in d.items():
    if k.startswith(skip_prefix):
        continue
    s = str(v)
    print('##', k, '->', s[:400].replace('\n', ' | '))

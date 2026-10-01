import json
d = json.load(open('.builder_queue/DEFECT-22_arc_legA_instability.json'))
for k in d:
    if k in ('found', 'found_by', 'severity', 'measured'):
        continue
    print('##', k)
    v = d[k]
    s = v if isinstance(v, str) else json.dumps(v, indent=1)
    print(s[:1800])
print('=== capture series commits:')
import subprocess
out = subprocess.run(['git', 'log', '--format=%h %s', '--grep=capture-series'], capture_output=True, text=True).stdout
print(len(out.strip().splitlines()), 'runs')
print(out[:400])

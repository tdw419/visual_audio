import json, re, subprocess, sys

out = subprocess.run(
    ['python3', '.builder_queue/probe_ek1_vector_hijack_wgsl_af3e.py'],
    capture_output=True, text=True, timeout=400,
)
txt = out.stdout + out.stderr
open('/tmp/bk55_recheck.txt', 'w').write(txt)
# Print the JSON-ish block for D legs
m = re.search(r'\{.*D1.*', txt, re.S)
if m:
    print(txt[m.start():m.start()+3000])
else:
    print(txt[-4000:])

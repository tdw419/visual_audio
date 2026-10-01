import subprocess
r = subprocess.run(
    ['bash', 'run_gate5_persist_probe.sh'],
    capture_output=True, text=True)
print(r.stdout, r.stderr)

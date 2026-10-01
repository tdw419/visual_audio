"""Measure the import floor of tests/test_gh18_syscall_abi.py in a fresh
process. Prints VmHWM after import. One-shot probe, not a gate."""
import os
import subprocess
import sys
import tempfile

CODE = """
import sys
sys.path.insert(0, ".")
import time
t0 = time.time()
import tests.test_gh18_syscall_abi  # noqa
with open("/proc/self/status") as f:
    hwm = [l for l in f if l.startswith("VmHWM")][0].split()[1]
print("VmHWM_KB", hwm, "secs", round(time.time() - t0, 2))
"""

p = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False)
p.write(CODE)
p.close()
env = dict(os.environ)
env["PATH"] = "/usr/bin:" + env.get("PATH", "")
r = subprocess.run(["/usr/bin/python3", p.name], capture_output=True,
                   text=True, env=env, cwd=os.path.dirname(p.name) or ".")
# run from repo root
r2 = subprocess.run(["/usr/bin/python3", p.name], capture_output=True,
                    text=True, env=env, cwd=os.getcwd())
print("cwd=repo:", r2.stdout.strip() or r2.stderr.strip()[-400:])
os.unlink(p.name)

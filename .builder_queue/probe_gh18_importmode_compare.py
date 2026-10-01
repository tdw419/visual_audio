"""Compare leg-A-shaped single-file run peak RSS: --import-mode vs default.
Writes output/probe_gh18_importmode_compare.txt. Not a gate."""
import os
import subprocess

env = dict(os.environ)
env["PATH"] = "/usr/bin:" + env.get("PATH", "")
env.pop("PYTHONPATH", None)

target = "tests/test_gh18_syscall_abi.py"
base = ["/usr/bin/python3", "-m", "pytest", target,
        "-p", "no:cacheprovider", "-p", "no:randomly",
        "-m", "not live_smoke", "-q", "--tb=no"]

lines = []
for label, extra in (("default", []),
                     ("importmode-importlib", ["--import-mode=importlib"])):
    # wrap with /usr/bin/time -v for peak RSS
    cmd = ["/usr/bin/time", "-f", "PEAK_RSS_KB %M"] + base + extra
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    peak = [l for l in r.stderr.splitlines() if "PEAK_RSS_KB" in l]
    summary = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "<none>"
    lines.append(f"{label}: {summary} | {peak[-1] if peak else 'no-peak'}")

with open("output/probe_gh18_importmode_compare.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))

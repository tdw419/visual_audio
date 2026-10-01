"""Measure the dogfood coreutils case: HEAD (item-20 native swap ON) vs
pre-item-20 (7b861bcc~1, host shims). Two-process comparison per rule 1.
Companion to RESEARCH_shellnative_turn_budget.md. 2026-09-25.
"""
import subprocess, sys, os, time

os.chdir(os.path.expanduser("~/projects/zion/projects/visual_audio"))

def run(cmd, env=None):
    t0 = time.perf_counter()
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                       timeout=280, env=env)
    dt = (time.perf_counter() - t0) * 1000
    return dt, r.returncode, r.stdout.strip().splitlines()[-3:] if r.stdout else []

# HEAD: full dogfood, 3 repeats of the suite
for i in range(2):
    dt, rc, tail = run("python3 tools/dogfood_gpu_os.py 2>/dev/null | grep coreutils")
    print(f"HEAD coreutils case: {dt:.0f}ms rc={rc} {tail}")

# pre-item-20: extract the old tree to a scratch dir, run the same case
os.makedirs("/tmp/pre20_va", exist_ok=True)
with open("/tmp/pre20_dogfood.py", "w") as f:
    f.write(subprocess.run(
        "git show 7b861bcc~1:tools/dogfood_gpu_os.py",
        shell=True, capture_output=True, text=True).stdout)
for p in ("experiments/glyph_l1_shell.py",):
    with open(f"/tmp/pre20_va/{os.path.basename(p)}", "w") as f:
        f.write(subprocess.run(
            f"git show 7b861bcc~1:{p}", shell=True, capture_output=True,
            text=True).stdout)
dt, rc, tail = run(
    "cd /tmp/pre20_va && python3 - <<'PY' 2>/dev/null\n"
    "import sys, time\n"
    "sys.path.insert(0, '.')\n"
    "from glyph_l1_shell import GlyphL1Shell\n"
    "sh = GlyphL1Shell()\n"
    "t0=time.perf_counter()\n"
    "sh.turn('write sample.txt hello world record2 payload')\n"
    "g1 = sh.turn('grep record2 sample.txt')\n"
    "wc = sh.turn('wc sample.txt')\n"
    "t1=time.perf_counter()\n"
    "print(f'pre-item-20 grep+wc turns: {(t1-t0)*1000:.1f}ms hit={g1!r}')\n"
    "PY")
print(f"pre-item-20 turn: {dt:.0f}ms rc={rc} {tail}")

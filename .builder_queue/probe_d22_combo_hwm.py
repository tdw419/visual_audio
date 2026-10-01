import resource, subprocess, sys, os
# Measure combined file under /usr/bin/time in-process is not possible; use time -v wrapper.
p = subprocess.run(["/usr/bin/time", "-v", sys.executable, "-m", "pytest",
                    "tests/test_gh18_syscall_abi.py", "tests/test_gh20_fs_v2.py",
                    "-q", "--no-header", "--tb=no", "-p", "no:cacheprovider"],
                   capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tail = p.stderr.strip().splitlines()
for ln in tail:
    if "Maximum resident" in ln:
        print(ln)
out = p.stdout.strip().splitlines()
print(out[-1] if out else "no stdout")

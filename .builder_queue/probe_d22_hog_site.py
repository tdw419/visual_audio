"""DEFECT-22 next_step (a): name the ~1.9 GB allocation site inside tests/test_gh18_syscall_abi.py.

Runs the file under tracemalloc (depth 25, top-25 by traced size at end), plus a
/proc/self/status VmHWM reading before/after. Foreground on purpose (uncapped scope).
Probe only — no test file, no engine file touched.
"""
import os
import tracemalloc

NFRAMES = 25
OUT = os.environ.get("D22H_OUT", "output/d22_hog_tracemalloc.txt")


def vm_hwm_kb():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmHWM:"):
                return int(line.split()[1])
    return -1


def main():
    hwm0 = vm_hwm_kb()
    tracemalloc.start(NFRAMES)
    import pytest

    rc = pytest.main(["tests/test_gh18_syscall_abi.py", "-q", "--no-header", "-x", "--tb=no"])
    snap = tracemalloc.take_snapshot()
    tracemalloc.stop()
    hwm1 = vm_hwm_kb()
    lines = []
    lines.append(f"pytest rc={rc}")
    lines.append(f"VmHWM before={hwm0} kB ({hwm0/1024:.1f} MiB)  after={hwm1} kB ({hwm1/1024:.1f} MiB)")
    lines.append("top 25 by traced size:")
    for stat in snap.statistics("lineno")[:25]:
        frames = stat.traceback or []
        first = frames[0]
        tb = first.filename if frames else "?"
        lines.append(f"{stat.size/1048576:12.1f} MiB  count={stat.count:8d}  {first.filename}:{first.lineno}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

"""pytest plugin: per-test VmRSS/VmHWM timeline + large /proc maps dump.
Not a committed gate; DEFECT-22 next_step(a) probe instrument.
Run: PATH=/usr/bin:$PATH PYTHONPATH=.builder_queue /usr/bin/python3 \
     -m pytest tests/test_gh18_syscall_abi.py -q -p rss_timeline_plugin
"""
import time
from pathlib import Path

OUT = Path("output/probe_gh18_rss_timeline.txt")
MAPS = Path("output/probe_gh18_maps_at_end.txt")
_rows = []
_cur = {"test": "SESSION_START", "rss0": None, "hwm0": None, "t0": None}


def _vm(key):
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith(key + ":"):
                return int(line.split()[1])
    return -1


def _top_maps(n=12):
    rows = []
    with open("/proc/self/maps") as f:
        start = None
        prev_end = 0
        prev_path = ""
        for line in f:
            parts = line.split()
            rng = parts[0]
            path = parts[5] if len(parts) > 5 else "[anon]"
            a, b = rng.split("-")
            size = int(b, 16) - int(a, 16)
            rows.append((size, path, rng))
    rows.sort(reverse=True)
    return [f"{s/1048576:8.1f}MB {p} {r}" for s, p, r in rows[:n]]


def pytest_runtest_protocol(item, nextitem):
    global _cur
    _cur = {"test": item.nodeid, "rss0": _vm("VmRSS"), "hwm0": _vm("VmHWM"),
            "t0": time.time()}
    # delegate to the default protocol (mirrors _pytest.runner impl)
    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid,
                                       location=item.location)
    from _pytest.runner import runtestprotocol
    runtestprotocol(item, nextitem=nextitem)
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid,
                                        location=item.location)
    rss1, hwm1 = _vm("VmRSS"), _vm("VmHWM")
    _rows.append(f"{(_cur['rss0'] or 0)/1024:7.1f}->{rss1/1024:7.1f}MB rss "
                 f"hwm={hwm1/1024:7.1f}MB d={hwm1-(_cur['hwm0'] or 0):+8d}kB "
                 f"t={time.time()-_cur['t0']:6.1f}s  {item.name}")


def pytest_sessionfinish(session, exitstatus):
    lines = [f"# exitstatus={exitstatus} final_hwm={_vm('VmHWM')/1024:.1f}MB "
             f"final_rss={_vm('VmRSS')/1024:.1f}MB"]
    lines += _rows
    lines.append("# top address-space mappings at exit:")
    lines += _top_maps()
    OUT.write_text("\n".join(lines) + "\n")

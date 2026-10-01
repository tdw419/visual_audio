"""pytest plugin: start tracemalloc, dump top allocation traces at exit.
Used only by the DEFECT-22 next_step probe (not committed as a test gate).
Run: /usr/bin/python3 -m pytest tests/test_gh18_syscall_abi.py -q \
      -p tracemalloc_dump_plugin --python? (no) ...
with PYTHONPATH=.builder_queue
"""
import tracemalloc
import time
from pathlib import Path

OUT = Path("output/probe_gh18_tracemalloc_pytest.txt")


def pytest_configure(config):
    tracemalloc.start(30)
    config._t0 = time.time()


def pytest_sessionfinish(session, exitstatus):
    snap = tracemalloc.take_snapshot()
    stats = snap.statistics("lineno")
    total = sum(s.size for s in stats)
    lines = [f"# tracemalloc total={total/1048576:.1f}MB n_traces={len(stats)} "
             f"exitstatus={exitstatus} secs={time.time()-session.config._t0:.1f}"]
    for s in stats[:20]:
        tb = s.traceback[-1]
        lines.append(f"{s.size/1048576:9.1f}MB count={s.count:8d} {tb}")
    # peak: python 3.9+ has tracemalloc get_traced_memory
    cur, peak = tracemalloc.get_traced_memory()
    lines.append(f"# traced_current={cur/1048576:.1f}MB traced_peak={peak/1048576:.1f}MB")
    OUT.write_text("\n".join(lines) + "\n")
    tracemalloc.stop()

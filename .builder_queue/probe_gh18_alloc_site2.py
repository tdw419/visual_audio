#!/usr/bin/env python3
"""DEFECT-22 follow-on, stage 2: name the *structure* behind the paged_dispatch run's
+2.0 GB (stage 1: `.builder_queue/probe_gh18_alloc_site.py`, artifact
`output/probe_gh18_alloc_site_2026091314.json` -- the jump is `GlyphRunner.run()` on the
`paged_dispatch` image, not the bake, not the trace).

Two independent readings, same process:
  A. engine-side accounting: `len(cpu.memory)` + `sys.getsizeof(cpu.memory)` after the run
     (glyph_isa_v2.py:742 extends `self.memory` toward `paddr + PAGE_WORDS` -- a list of
     N pointers costs ~8N bytes, so a big paddr shows up here directly).
  B. tracemalloc top-N allocation sites by size (Python-level; the honest caveat is that
     numpy buffers may not appear -- reported as such, not assumed).

Writes output/probe_gh18_alloc_site2_<seed>.json.
"""
from __future__ import annotations

import json
import sys
import tempfile
import tracemalloc
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SEED = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 0


def status_mb(key: str) -> float:
    with open("/proc/self/status") as fh:
        for ln in fh:
            p = ln.split()
            if len(p) >= 2 and p[0] == key + ":":
                return int(p[1]) / 1024.0
    return -1.0


def main() -> int:
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.baker import syscall_abi_kernel_image
    from tools.glyph_gpt.runner import GlyphRunner

    tmp = Path(tempfile.mkdtemp(prefix="gh18_alloc2_"))
    out = tmp / "paged.glyph.npy"
    syscall_abi_kernel_image(build_default_atlas(), mode="paged_dispatch",
                             timer_quantum=35, out_path=out)
    print(f"hwm after bake            = {status_mb('VmHWM'):8.1f} MB")
    runner = GlyphRunner(out, ram_words=16384)
    cpu0 = getattr(runner, "cpu", None)
    print(f"cpu.memory after ctor     = {len(cpu0.memory) if cpu0 is not None else 'n/a'}")
    print(f"image shape               = {getattr(runner.image, 'shape', None)}")

    tracemalloc.start(25)
    trace = runner.run(max_instructions=60000, trace=True)
    snap = tracemalloc.take_snapshot()
    print(f"hwm after run             = {status_mb('VmHWM'):8.1f} MB")
    print(f"rss after run             = {status_mb('VmRSS'):8.1f} MB  (retained)")
    cpu = getattr(runner, "cpu", None)
    mem_len = len(cpu.memory) if cpu is not None else None
    print(f"cpu.memory after run      = {mem_len} words")
    if mem_len is not None:
        print(f"  sizeof(list)            = {sys.getsizeof(cpu.memory) / 1e6:.1f} MB")
    print(f"trace entries             = {len(trace) if hasattr(trace, '__len__') else None}")

    print("\ntracemalloc top 8 by size (Python-level allocations only):")
    top = snap.statistics("lineno")[:8]
    for st in top:
        fr = st.traceback[0]
        print(f"  {st.size / 1e6:9.1f} MB  {fr.filename}:{fr.lineno}  n={st.count}")

    payload = {
        "seed": SEED,
        "hwm_after_run_mb": status_mb("VmHWM"),
        "rss_after_run_mb": status_mb("VmRSS"),
        "cpu_memory_words": mem_len,
        "cpu_memory_list_mb": (sys.getsizeof(cpu.memory) / 1e6) if mem_len is not None else None,
        "tracemalloc_top": [
            {"size_mb": round(st.size / 1e6, 2), "file": st.traceback[0].filename,
             "line": st.traceback[0].lineno, "count": st.count} for st in top
        ],
        "argv": " ".join(sys.argv),
    }
    art = REPO / "output" / f"probe_gh18_alloc_site2_{SEED}.json"
    art.write_text(json.dumps(payload, indent=1))
    print(f"\nartifact: {art}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

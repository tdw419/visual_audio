#!/usr/bin/env python3
"""DEFECT-22 follow-on: NAME the allocation that sets the ~1.9 GB transient of
`tests/test_gh18_syscall_abi.py` (leg A's single jump, receipt
`systems/RECEIPT_DEFECT22_LEGA_CAPTURE_FOOTPRINT.md`).

Method (no interpretation; every number is the kernel's own `/proc/self/status`):

  * Run, in ONE process, the same operations the file's heaviest test performs
    (`test_gh18_syscall_table_window_reserved`: 3 modes x bake + `_run`), marking
    `VmHWM` after each stage. `VmHWM` is monotonic, so the delta between consecutive
    marks attributes the increase to the stage that ran in between -- this is exactly
    the leg-A attribution method, one level down.
  * A 20 ms sampler thread records peak `VmRSS` *inside* each stage, so a transient
    that is freed before the stage ends is still caught (the leg-A spike was a
    transient: RSS fell back to 758-1065 MB while HWM stayed high).

Legs:
  L1 stage attribution (imports / atlas / bake / runner / run) per mode.
  L2 `trace=True` vs `trace=False` on the same program, all else equal: is the jump
     the step trace? If yes, the delta is the trace's own retained bytes.
  L3 falsifier/non-vacuity: the same measurement on a program the file does NOT run
     heavy (`examples/01_hello.glyph`-class trivial bake) must NOT show the jump --
     i.e. the method discriminates a heavy stage from a light one.

Usage: python3 .builder_queue/probe_gh18_alloc_site.py [--seed N]
Writes output/probe_gh18_alloc_site_<seed>.json and prints a stage table.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SEED = 0
for i, a in enumerate(sys.argv):
    if a == "--seed":
        SEED = int(sys.argv[i + 1])

STAGES: list[dict] = []
_sampler_stop = threading.Event()
_sampler_live = [False]
_sampler_peak = [0.0]


def _status() -> dict:
    """Parse /proc/self/status by whitespace (never by ': ' -- the real separator is ':\\t')."""
    out = {}
    with open("/proc/self/status") as fh:
        for ln in fh:
            parts = ln.split()
            if len(parts) >= 2 and parts[0].endswith(":"):
                try:
                    out[parts[0][:-1]] = int(parts[1]) / 1024.0  # kB -> MB
                except ValueError:
                    pass
    return out


def _sampler() -> None:
    while not _sampler_stop.is_set():
        try:
            _sampler_peak[0] = max(_sampler_peak[0], _status().get("VmRSS", 0.0))
        except OSError:
            pass
        time.sleep(0.02)


def mark(label: str) -> None:
    s = _status()
    peak_in_stage = _sampler_peak[0]
    _sampler_peak[0] = 0.0
    rec = {
        "stage": label,
        "vmhwm_mb": round(s.get("VmHWM", -1), 1),
        "vmrss_mb": round(s.get("VmRSS", -1), 1),
        "peak_rss_in_stage_mb": round(peak_in_stage, 1),
    }
    prev = STAGES[-1]["vmhwm_mb"] if STAGES else 0.0
    rec["hwm_delta_mb"] = round(rec["vmhwm_mb"] - prev, 1)
    STAGES.append(rec)
    print(f"  {label:38s} HWM={rec['vmhwm_mb']:9.1f} MB  Δ={rec['hwm_delta_mb']:+9.1f} MB  "
          f"RSS={rec['vmrss_mb']:9.1f}  peak_in_stage={rec['peak_rss_in_stage_mb']:9.1f}", flush=True)


def main() -> int:
    t = threading.Thread(target=_sampler, daemon=True)
    t.start()
    tmp = Path(tempfile.mkdtemp(prefix="gh18_alloc_"))

    mark("start")
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.baker import syscall_abi_kernel_image
    from tools.glyph_gpt.runner import GlyphRunner
    mark("imports (atlas+baker+runner)")

    atlas = build_default_atlas()
    mark("build_default_atlas()")

    results = {}
    for mode in ("baseline", "admit", "paged_dispatch"):
        out = tmp / f"{mode}.glyph.npy"
        t0 = time.time()
        syscall_abi_kernel_image(atlas, mode=mode, timer_quantum=35, out_path=out)
        mark(f"bake {mode}")
        runner = GlyphRunner(out, ram_words=16384)
        mark(f"GlyphRunner {mode}")
        trace = runner.run(max_instructions=60000, trace=True)
        mark(f"run {mode} (trace=True, 60k cap)")
        results[mode] = {
            "run_s": round(time.time() - t0, 2),
            "trace_entries": len(trace) if hasattr(trace, "__len__") else None,
            "trace_retained_mb": round(sys.getsizeof(trace) / 1e6, 2),
        }
        # L2: same program, no trace -- isolates the trace's own cost
        runner2 = GlyphRunner(out, ram_words=16384)
        runner2.run(max_instructions=60000, trace=False)
        mark(f"run {mode} (trace=False, 60k cap)")
        results[mode]["image_path"] = str(out)

    # L3 non-vacuity: a light bake must NOT move HWM
    light = tmp / "light.npy"
    syscall_abi_kernel_image(atlas, mode="baseline", timer_quantum=0, out_path=light)
    mark("L3 light bake (quantum=0)")

    _sampler_stop.set()
    payload = {"seed": SEED, "stages": STAGES, "modes": results,
               "python": sys.version.split()[0],
               "argv": " ".join(sys.argv)}
    art = REPO / "output" / f"probe_gh18_alloc_site_{SEED}.json"
    art.write_text(json.dumps(payload, indent=1))
    print(f"\nartifact: {art}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

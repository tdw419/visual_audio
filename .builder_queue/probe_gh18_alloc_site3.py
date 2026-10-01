#!/usr/bin/env python3
"""DEFECT-22 follow-on, stage 3: quantify the two suspects stage 2 named.

Stage 2 (`output/probe_gh18_alloc_site2_2026091314.json`) attributed 1189.1 MB to
`tools/glyph_gpt/runner.py:132` -- `receipt["memory"] = [int(m) & 0xFFFFFFFF for m in cpu.memory]`
-- inside a single `GlyphRunner.run()` on the `paged_dispatch` image.

This stage separates the two quantities in one process, by monkeypatching (out-of-tree,
probe-only) `GlyphRunner._fill_receipt` to capture `cpu.memory` before delegating:

  A. the ENGINE's own memory list: `len(cpu.memory)`, `sys.getsizeof` (8 B/word of
     pointers; the zeros are one cached int, so the list is the cost)  [glyph_isa_v2.py:742
     extends `self.memory` toward `paddr + PAGE_WORDS`]
  B. the RECEIPT's copy of it: `len(receipt["memory"])` + `sys.getsizeof` + the number of
     non-cached ints (each >256 costs a separate ~28 B object)

Also reports which mode is affected (baseline / admit / paged_dispatch) so the claim is
scoped, not generalised. Writes output/probe_gh18_alloc_site3_<seed>.json.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SEED = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 0


def hwm_mb() -> float:
    with open("/proc/self/status") as fh:
        for ln in fh:
            p = ln.split()
            if len(p) >= 2 and p[0] == "VmHWM:":
                return int(p[1]) / 1024.0
    return -1.0


def main() -> int:
    from tools.glyph_gpt.atlas import build_default_atlas
    from tools.glyph_gpt.baker import syscall_abi_kernel_image
    from tools.glyph_gpt.runner import GlyphRunner

    caps: dict = {}
    orig = GlyphRunner._fill_receipt

    def wrapped(self, receipt, cpu, steps):  # noqa: ANN001
        key = f"call{len(caps)}"
        caps[key] = {"engine_memory_words": len(cpu.memory),
                     "engine_list_mb": round(sys.getsizeof(cpu.memory) / 1e6, 2),
                     "engine_nonzero_words": sum(1 for m in cpu.memory if m)}
        return orig(self, receipt, cpu, steps)

    GlyphRunner._fill_receipt = wrapped
    tmp = Path(tempfile.mkdtemp(prefix="gh18_alloc3_"))
    atlas = build_default_atlas()
    rows = {}
    for mode in ("baseline", "admit", "paged_dispatch"):
        out = tmp / f"{mode}.npy"
        syscall_abi_kernel_image(atlas, mode=mode, timer_quantum=35, out_path=out)
        before = len(caps)
        runner = GlyphRunner(out, ram_words=16384)
        rec = runner.run(max_instructions=60000, trace=True)
        cap = caps.get(f"call{before}", {})
        mem = rec.get("memory")
        rows[mode] = {
            **cap,
            "receipt_memory_len": len(mem) if mem is not None else None,
            "receipt_list_mb": round(sys.getsizeof(mem) / 1e6, 2) if mem is not None else None,
            "receipt_hwm_mb": round(hwm_mb(), 1),
            "steps": rec.get("steps"),
            "faulted": rec.get("faulted"),
        }
        print(f"{mode:16s} engine_words={cap.get('engine_memory_words')!s:>10} "
              f"engine_list={cap.get('engine_list_mb')!s:>9} MB  nonzero={cap.get('engine_nonzero_words')!s:>9}  "
              f"receipt_len={rows[mode]['receipt_memory_len']!s:>10} receipt_list={rows[mode]['receipt_list_mb']!s:>9} MB  "
              f"hwm={rows[mode]['receipt_hwm_mb']:8.1f} MB  steps={rec.get('steps')}", flush=True)

    payload = {"seed": SEED, "rows": rows, "argv": " ".join(sys.argv)}
    art = REPO / "output" / f"probe_gh18_alloc_site3_{SEED}.json"
    art.write_text(json.dumps(payload, indent=1))
    print(f"\nartifact: {art}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

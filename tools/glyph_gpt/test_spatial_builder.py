#!/usr/bin/env python3
"""test_spatial_builder.py — SB-0 front-end + SB-1 tile composition.

Falsifiable gates:
  * SB-0: an intent task builds, links, executes, halts, meets its contract.
  * SB-1: a 3-tile pipeline (clear -> memcpy -> accumulate) reaches the
    byte-exact composite end state and halts; every stage's CALL is what
    the model emitted.
  * SB-1 negative: an out-of-bounds destination in any stage faults the
    whole pipeline (exit non-zero), and the offending stage is named.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent), str(_HERE.parent.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from glyph_gpt.atlas import build_default_atlas               # noqa: E402
from glyph_gpt.model import load_checkpoint                   # noqa: E402
from glyph_gpt.tokenizer import GlyphTokenizer                # noqa: E402
from glyph_gpt.spatial_builder import (                       # noqa: E402
    build_task, parse_pipeline, run_pipeline, run_task, simulate_pipeline,
)

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


def main() -> None:
    model = load_checkpoint(str(_HERE / "checkpoint.pt"))
    tok = GlyphTokenizer.load(str(_HERE / "tokenizer.json"))
    atlas = build_default_atlas()
    try:
        from glyph_gpt.synth import ldi_reg_value_sets
        ldi = ldi_reg_value_sets(_HERE / "synth_receipts.jsonl")
    except Exception:
        ldi = None

    # ── SB-0: single intent task ─────────────────────────────────────────
    t = build_task("accumulate", 0, [7, 9, 5], 600, 4, 0xDEAD)
    r = run_task(t, model, tok, atlas, ldi, 1.0, 7)
    check("SB-0 accumulate task: builds, halts, contract holds",
          r["pass"] and not r["receipt"].get("faulted"), r["detail"])

    # ── SB-1: composite end-state simulation is sane ─────────────────────
    words = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5, 8, 9, 7, 9, 3]
    spec = (f"seed:500,{','.join(map(str, words))} "
            "clear:600,16,0 memcpy:500,600,16 accumulate:600,16")
    stages = parse_pipeline(spec)
    mem_exp, r10_exp = simulate_pipeline(stages)
    check("SB-1 sim: memcpy result folded into end state",
          all(mem_exp[600 + i] == words[i] for i in range(16)),
          str(mem_exp))
    check("SB-1 sim: accumulate end value == sum(words)",
          r10_exp == sum(words), f"{r10_exp} != {sum(words)}")

    # ── SB-1: the pipeline runs on the oracle and verifies ───────────────
    rp = run_pipeline(stages, model, tok, atlas, ldi, 7)
    check("SB-1 pipeline: 3 tiles chained, byte-exact end state, halts",
          rp["pass"] and rp["receipt"].get("halted")
          and not rp["receipt"].get("faulted"), rp["detail"])
    check("SB-1 pipeline: every stage CALL is what the model emitted",
          all(ok for _, _, ok in rp["model_calls"]),
          str(rp["model_calls"]))

    # ── SB-1 negative: OOB destination in the memcpy stage ───────────────
    bad = parse_pipeline(
        f"seed:500,{','.join(map(str, words))} "
        "clear:600,16,0 memcpy:500,1200,16 accumulate:600,16")
    rb = run_pipeline(bad, model, tok, atlas, ldi, 7)
    check("SB-1 negative: OOB stage faults the whole pipeline",
          (not rb["pass"]) and rb["receipt"].get("faulted"), rb["detail"])
    check("SB-1 negative: offending stage named (index 2, memcpy)",
          rb["oob_stage"] == 2 and bad[2]["tile"] == "memcpy",
          f"oob_stage={rb['oob_stage']}")

    # ── SB-2: C-to-atlas ingestion bridge ───────────────────────────────
    import shutil
    import subprocess
    import tempfile

    if shutil.which("riscv64-unknown-elf-gcc") is None:
        print("  SKIP SB-2 (riscv64-unknown-elf-gcc not installed)")
    else:
        def _native(c_func: str, call: str, want: int) -> bool:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "h.c"
                p.write_text(c_func + f"int main(){{return ({call})=={want}?0:1;}}\n")
                exe = Path(d) / "h"
                subprocess.run(["gcc", "-O1", "-w", str(p), "-o", str(exe)],
                               check=True, capture_output=True)
                return subprocess.run([str(exe)]).returncode == 0

        def _ingest_run(nm: str, c_func: str, sym: str,
                        arr: list[int], want: int) -> tuple:
            atlas.register_from_c(nm, c_func, sym)
            byte_base, w = 0x800, 0x800 >> 2
            h = ["LDI r31 30000", "LDI r2 20000"]
            for i, v in enumerate(arr):
                h += [f"LDI r14 {v}", f"LDI r15 {w + i}", "ST r15 r14"]
            h += [f"LDI r10 {byte_base}", f"LDI r11 {len(arr)}",
                  f"CALL :atlas_{nm}", "HALT"]
            r = atlas.run_linked("\n".join(h) + "\n", cols_instrs=64)
            got = r.get("registers_full", [None] * 11)[10]
            return r, got

        C_SUM = ("int sum_array(int *a,int n){int s=0;"
                 "for(int i=0;i<n;i++)s+=a[i];return s;}\n")
        C_MAX = ("int max_array(int *a,int n){int m=a[0];"
                 "for(int i=1;i<n;i++){if(a[i]>m)m=a[i];}return m;}\n")

        arr1 = [7, 9, 5, 4, 11, 2]
        r, got = _ingest_run("sum_c", C_SUM, "sum_array", arr1, sum(arr1))
        check("SB-2 sum_array: registered as ingested_c tile",
              atlas.tiles["sum_c"]["family"] == "ingested_c")
        check("SB-2 sum_array: native host == want",
              _native(C_SUM, f"sum_array((int[]){{{','.join(map(str, arr1))}}},"
                             f"{len(arr1)})", sum(arr1)))
        check("SB-2 sum_array: ingested tile runs on GlyphCPUv2, halts, == native",
              r.get("halted") and not r.get("faulted") and got == sum(arr1),
              f"a0={got} want={sum(arr1)} {r.get('error', '')}")

        arr2 = [7, 42, 5, 99, 4, 11, 2]
        r, got = _ingest_run("max_c", C_MAX, "max_array", arr2, max(arr2))
        check("SB-2 max_array: second ingested tile, GlyphCPUv2 == native",
              r.get("halted") and not r.get("faulted") and got == max(arr2)
              and _native(C_MAX,
                          f"max_array((int[]){{{','.join(map(str, arr2))}}},"
                          f"{len(arr2)})", max(arr2)),
              f"a0={got} want={max(arr2)}")
        # NOTE: the SpatialRV32ICore third leg (true three-way on the ingested
        # body) is deferred to the GPU-harness plumbing work that also gates
        # SB-3 — see SPATIAL_BUILDER_ROADMAP.md SB-3 scoping note.

    print(f"\nspatial_builder tests: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

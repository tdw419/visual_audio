# HANDOFF — GL-7 benchmark artifact ready; publication is yours (2026-09-12, cron af3e62239ce2)

**Artifact commit:** `0aa14b1` in `/home/jericho/zion/worktrees/glyph-isa` → `github.com/tdw419/glyph-isa`
(local, **unpushed**; it sits on top of GL-6's `b5aa3f2`, which is also unpushed). Eight new files, no
existing file modified.

- `tools/bench_cold_boot.py` — the harness (three legs, N reps, JSON out)
- `tools/bench_glyph_child.py`, `tools/bench_wasm_module.py`, `tools/bench_wasm_runner.js`, `tools/bench_boot_sector.py`
- `docs/bench/cold_boot.json` — the raw 7-rep numbers
- `docs/BENCHMARK_COLD_BOOT.md` — methodology, the numbers, and **"What this does not show"**
- `tests/test_gl7_benchmark.py` — the gate (4/4, RED-without-the-artifact proven)

Receipt: `systems/RECEIPT_GL7_COLD_BOOT_BENCH.md` (builder repo).

## Headline numbers (the honest version)

| leg | spawn → first instruction (median, 7 reps) |
|---|---|
| glyph (`glyphc build` → `.glyph.png` → `GlyphRunner` → first `cpu.step`) | **77.60 ms** |
| wasm (node v24.13.0 + 37-byte module emitted by this repo) | **12.38 ms** |
| qemu_vm (qemu 8.2.2 + 512-byte boot sector emitted by this repo) | **76.84 ms** |

Read it as: on this host the glyph cold boot is the same order as a full qemu VM boot and ~6× a node+wasm
instantiation, with **56.5 of the glyph leg's 77.6 ms being Python import** — i.e. the number is dominated by
the host language runtime, not by the glyph machine. That is the caveat the doc states up front, and it is why
publishing this as-is is honest but should not be framed as an ISA-speed claim.

## What only you can do (fenced to you by the lane ruling)

1. **Push** both commits (`b5aa3f2`, `0aa14b1`) — that also puts GL-6's and GL-7's gates into GL-4's CI matrix
   for the first time.
2. **Decide the publication frame** (README line? blog? nothing yet): the loop prepares the artifact, not the
   publication. If you want a stronger story, the measured lever is obvious from the phase breakdown —
   `import` is 73% of the glyph number, so an in-process/no-import entrypoint would move it a lot; the loop has
   not touched it, because that is an engine/CLI change and would need your go.
3. **Flip `systems/GLYPH_OSS_ROADMAP.md:42`** to ✅ if you consider the row's oracle met by the committed doc +
   numbers, and GL-6's `:41` once the cast has a shareable URL.

## Verify it yourself in ~40 s

```bash
cd /home/jericho/zion/worktrees/glyph-isa
/usr/bin/python3 -m pytest tests/test_gl7_benchmark.py -q     # 4 passed
/usr/bin/python3 tools/bench_cold_boot.py --reps 7 --json /tmp/re.json   # prints the JSON
```

## Honest limits

- No page cache drop (no root); qemu leg is a full VM with SeaBIOS, not a microVM (Firecracker absent).
- The gate compares against a 3× tolerance band rather than exact equality, because these are wall-clock
  numbers; fabricated or drifted values are still caught (probes P1/P3 red), but a 2.9× drift would not be.
- The numbers are for this host (Core Ultra 9 275HX) and this tree (`0aa14b1`).

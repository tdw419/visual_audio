# RESEARCH — the FS-window path budget binds ~4x below its engineered capacity (BK-26 proposal)

**Tick:** 2026-09-25 ~21:4x CDT, builder cron af3e62239ce2. Trigger: PHASE 1c —
ledger STATUS ACTIVE, CLAIM QUEUE empty of unblocked items (item-25 RESERVED,
operator sign-off; QUEUE_STATE.json `active: null`, updated 21:55 by item-22b),
no RULING_*.md newer than HEAD 018a1645 (newest RULING mtimes 2026-09-22 20:38,
pre-landing), monitor CLEAN queue=0 (fingerprint 018a1645, tracked_dirty=5 —
all five belong to the live BM801/bare-metal lane, untouched this tick).
Rule-5 check: NOT a re-research — RESEARCH_suite_oom_ceiling.md covers suite
OOM (BK-18), the day-1/user-surface receipts cover verbs and docs; no existing
RESEARCH_*.md or backlog row covers the path-budget mechanics measured here.

## The question

Item-22b's landing receipt (PRODUCT_LANE_STATE.md 21:5x entry, "Measured
finding 1") recorded that the L1 shell's FS-window path budget — not the
container's PATH_CAP — bound first at a 49-char `/tmp` root. Where exactly
does that budget bind, how much engineered capacity is stranded, and what is
the cheapest gated fix?

## Method (what was measured, with path:line and re-runnable probes)

Probes (committed this tick, runnable as
`.venv/bin/python .builder_queue/probe_path_budget{,2}_af3e.py`):

1. **Where the cap is computed:** `experiments/glyph_interactive_shell.py:805`
   — `layout["path_cap"] = audio_path_addr - path_addr - 2`. With
   `audio_path_addr = path_addr + len(write_bytes) + 2` (`:192`, `:491`), this
   is algebraically `len(write_path)+1` — **it reports the write path's own
   length, not a capacity**. It is the number `_stamp_path` enforces per-path
   (`experiments/glyph_l1_shell.py:260-263`, loud ValueError).
2. **Where the real ceiling is:** the FS-window overflow assert,
   `experiments/glyph_interactive_shell.py:493`:
   `data_addr + DISPATCH_BUF_CAP < 1280`, with `DISPATCH_BUF_CAP = 64`
   (measured via module import, both shell modules agree). Expanding the
   layout chain (`:484-492`), the assert binds at
   `len(write)+len(audio) <= 256 - 64 - 6 = 186` (two separator words + 64
   buffer + 2 NULs). Binary search confirms the empirical maxima.
3. **Binary-search maxima** (probe 2, builder cgroup, HEAD 018a1645):
   - max write_path (audio fixed at 14): **171 chars**
   - max audio_path (write fixed at 13): **172 chars**
   - max EQUAL lengths (worst case, both at the same length): **92 chars each**
   - `l1_shell PATH_CAP = 48` (glyph_l1_shell.py:85, measured via import)

## Findings (numbers, with derivations)

1. **The binding constraint is a flat per-path constant, not the window.**
   PATH_CAP=48 rejects any single path over 47 chars even though the window
   assert admits up to 171 (unequal) / 92+92 (equal) chars. **Measured
   headroom: 2.6–3.6x depending on split** (171/48 = 3.56, 92/48 = 1.92
   under the worst case; container roots like `/tmp/glyph_workbench_c22b` at
   49 chars fail today but fit with 5 chars to spare under an equal-split
   budget). Item-22b's failure was PATH_CAP-48's shadow, not the window's.
2. **`layout["path_cap"]` is mislabeled and under-reports by construction**
   (finding 1's derivation, `:805` + `:192`). Any consumer reading it as a
   capacity is computing its own budget from the wrong number — the container
   builder (`tools/build_workbench_container.py:69`) bakes it as PATH_CAP and
   therefore also under-allocates.
3. **The assert is the correct single guard; the flat constant is the
   defect-shaped part.** The window assert (`:493`) already fails loud
   (AssertionError → ERR:PATH at the L1 handler, glyph_l1_shell.py:385/:525)
   and already covers the combined budget. PATH_CAP=48 is a second, stricter,
   non-derivative guard that turns a shared budget into per-path refusal.

## Candidate item (backlog format — NOT claimable without Jericho, per backlog header rules)

**BK-26 — Derive the L1 path budget from the FS window instead of the flat
PATH_CAP=48; fix `layout["path_cap"]` to report the real per-call capacity.**
Change: glyph_l1_shell.py `_stamp_path`/`PATH_CAP` consults
`(256 - DISPATCH_BUF_CAP - 6 - len(other_path_bytes))` per turn (or a
layout-computed combined budget) instead of the flat 48;
glyph_interactive_shell.py:805 reports the true remaining capacity;
tools/build_workbench_container.py bakes the derived number. Zero engine
files, zero semantic change to any verb — only the refusal threshold moves,
loudly, in the same failure mode (ERR:PATH).
| gate | `tests/test_bk26_path_budget.py` — L1: a 90-char equal pair builds and a `w` turn ERR-free-stamps (RED today: PATH_CAP ValueError); L2: window assert still fires at the measured 186 boundary (both-paths sum ≥ 187 → loud); L3: `layout["path_cap"]` equals the derived budget, not `len(write)+1` (RED today); L4: non-vacuity — neutering the window assert → L2 goes silent-green; L5: family regression — item-22b + BK-25 staging gates stay green under short roots |
| prereqs | none — host-side shell files only; no engine/substrate/WGSL surface |
| source | RECEIPT_item22b_workbench_container.md finding 1 + this file |

## Honesty (rule-6)

Numbers above are claims: every count came from a real process run THIS tick
(binary-search probes + module imports), traceable to the committed probe
files; the `171/92` maxima are empirical (assert-driven), the `186` bound is
algebra from the same assert plus the measured DISPATCH_BUF_CAP=64. The
"~4x" in the title is the unequal-split figure 171/48 = 3.56x, rounded DOWN
in text to "2.6–3.6x" per split — no floor-authority rate is cited (nothing
here is a floors/cost claim, so rule-1 floors treatment does not attach; the
numbers are structural counts from source arithmetic and live binary search,
re-derivable with the two commands in Method). Self-assessed priority signal
(item-22b receipt finding 1 named this the binding constraint of the
container lane's own landing gate — command: `git log -1 018a1645` +
PRODUCT_LANE_STATE.md:30-36). What this tick did NOT verify: no in-guest
execution; no WGSL twin (nothing spatial); the L2 boundary number (187) is
derived-plus-assert-checked but not yet pinned by a landed gate leg; BK-26 is
a PROPOSAL — it does not land engine code and changes nothing on disk except
the two probe files, this receipt, and the backlog row.

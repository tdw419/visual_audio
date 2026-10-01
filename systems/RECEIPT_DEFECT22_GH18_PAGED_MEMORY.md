# RECEIPT — the GH-18 paged run's ~1.9 GB transient, NAMED: a 134.8-million-word flat memory for 27 values

**Tick:** 2026-09-13 14:2x CDT, builder cron `af3e62239ce2`, branch `glyph-transpiler-autoloop`, base `2e54fe7`.
**Question answered (named as *the* next probe by the previous tick's receipt):** which allocation inside
`tests/test_gh18_syscall_abi.py` reserves the ~1.9 GB transient that sets leg A's `pytest` `VmHWM` at 2684.3 MB
(`systems/RECEIPT_DEFECT22_LEGA_CAPTURE_FOOTPRINT.md:43-47`, ticket `.builder_queue/REPAIR_PENDING_suite_iso2_memory_containment.md:116`).
**Answer, one line:** `GlyphRunner.run()` on a **`paged_dispatch`** image grows the engine's flat memory list to
**134,810,550 words (1.08 GB of pointers) to hold 27 nonzero words**, and `runner.py:132` then copies that list a
second time into the receipt (**1.19 GB**) — 2.27 GB of live lists at the peak, 1.19 GB of it retained by the receipt.

No engine, ABI, test or baker file was touched by this tick. Measurement only.

## Method (and its own falsifier)

Four stages, all in one process per stage, all numbers from the kernel (`/proc/self/status`) or from `tracemalloc`
— no estimator, no model. Probes are in `.builder_queue/`; artifacts in `output/`.

| stage | probe | what it isolates |
|---|---|---|
| 1 | `probe_gh18_alloc_site.py` | stage attribution: imports / atlas / bake / `GlyphRunner` / `run()`, per bake mode, `VmHWM` deltas (monotonic ⇒ delta = the stage that ran in between) + a 20 ms `VmRSS` sampler for freed transients |
| 2 | `probe_gh18_alloc_site2.py` | `tracemalloc` top-N by line, plus a falsifier for the "it's the 60k-step trace" hypothesis |
| 3 | `probe_gh18_alloc_site3.py` | the two quantities separated in one process: engine list vs receipt copy, per mode (monkeypatched `_fill_receipt`, out-of-tree, probe-only) |
| 4 | `probe_gh18_alloc_site4.py` | the exact step/PC of each memory extension, one instruction at a time |

Non-vacuity is built in: the same instrument reads **0.13–0.14 MB** for `baseline` and `admit` and **1078–1189 MB**
for `paged_dispatch` (stage 3 table below). It discriminates.

## Stage 1 — the jump is `run()`, in one mode, and it is not the trace

Artifact `output/probe_gh18_alloc_site_2026091314.json` (seed 2026091314, foreground):

| stage | `VmHWM` | Δ |
|---|---|---|
| start | 16.8 MB | +16.8 |
| imports (`atlas`+`baker`+`runner`) | 227.1 MB | +210.3 |
| `build_default_atlas()` | 229.5 MB | +2.4 |
| bake baseline / `GlyphRunner` / run `trace=True` / run `trace=False` | 229.9 → 230.8 MB | **≤ +0.4 each** |
| bake admit / `GlyphRunner` / run `trace=True` / run `trace=False` | 231.0 MB | **≤ +0.2 each** |
| bake `paged_dispatch` / `GlyphRunner` | 231.4 MB | +0.4 / +0.0 |
| **run `paged_dispatch` (`trace=True`, 60k cap)** | **2289.5 MB** | **+2058.1** |
| run `paged_dispatch` (`trace=False`) | 3318.0 MB | +1028.5 |
| L3 light bake (quantum 0) | 3318.0 MB | +0.0 |

* `trace` was **10 entries** and the run **halted at 372 steps** — the "trace of 60,000 steps" hypothesis is
  **refuted**: the trace cannot be the cost.
* `RSS` after both runs is **1261.5 MB** and does not move between them, while `HWM` rises — consistent with one
  ~1.19 GB structure being retained by the receipt and the engine's own list being freed when `run()` returns.
* **Instrument caveat:** the second run's +1028.5 MB is measured while this probe still holds the *first* run's
  receipt and runner; it is a peak *including* that retained receipt, not an independent "two runs cost double"
  reading. It is reported because it is what the sampler saw, not because it is a clean second measurement.

## Stage 2 — `tracemalloc` names one line

Artifact `output/probe_gh18_alloc_site2_2026091314.json`:

```
     1189.1 MB  tools/glyph_gpt/runner.py:132  n=27
        0.0 MB  tools/glyph_gpt/runner.py:65   n=316
        0.0 MB  every other site
```

`runner.py:132` is `receipt["memory"] = [int(m) & 0xFFFFFFFF for m in cpu.memory]`. `n=27` is the tell: only 27
distinct non-cached int objects are allocated, so the 1189.1 MB is the **list's pointer array** (8 B/word), not
boxed ints. (Honest scope: `tracemalloc` traces Python allocations; the engine's own list may or may not appear —
stage 3 measures it directly instead, which is why both are reported.)

## Stage 3 — engine list vs receipt copy, separated

Artifact `output/probe_gh18_alloc_site3_2026091314.json` (`_fill_receipt` wrapped in the probe process only):

| mode | engine memory words | engine list | nonzero words | receipt len | receipt list | `VmHWM` | steps |
|---|---|---|---|---|---|---|---|
| baseline | 16,384 | 0.13 MB | 18 | 16,384 | 0.14 MB | 231.1 MB | 257 |
| admit | 16,384 | 0.13 MB | 30 | 16,384 | 0.14 MB | 231.3 MB | 299 |
| **paged_dispatch** | **134,810,550** | **1078.48 MB** | **27** | **134,810,550** | **1189.08 MB** | **2289.3 MB** | 372 |

The engine's memory is a bare Python list (`runner.get_cpu()` → `cpu.memory = [0] * self.ram_words`,
`tools/glyph_gpt/runner.py:46`); every element of the extension points at the *same cached* zero int, so the
1.078 GB buys exactly **27 nonzero words** (a 5.0-million-fold waste of address-space materialisation).

## Stage 4 — the two steps that did it

Artifact `output/probe_gh18_alloc_site4_2026091314.json` (same image, stepped one instruction at a time, no cap):

| step | pixel PC | mode | memory before → after | grew |
|---|---|---|---|---|
| 298 | (20, 23) | USER (1) | 16,384 → 17,304,265 | +17,287,881 words (**+138.3 MB** of pointers) |
| 371 | (24, 22) | SUPER (0) | 17,304,265 → 134,810,550 | +117,506,285 words (**+940.1 MB**) |
| — | — | — | final 134,810,550 words, list 1078.48 MB, **27 nonzero**, halted at 372 steps | 2 events total |

Store path: `tools/glyph_isa_v2.py:740-743` —

```python
paddr = pfn * PAGE_WORDS + offset            # pfn = pte >> 8, PAGE_WORDS = 256
if paddr >= len(self.memory):
    self.memory.extend([0] * (paddr + PAGE_WORDS - len(self.memory)))
self.memory[paddr] = val & 0xFFFFFFFF
```

**Arithmetic inference (derived from the observed list length, not observed directly):** `paddr = len - 256`
⇒ step 298 targets `paddr = 17,304,009` (`pfn = 67,593`, offset 201) and step 371 targets `paddr = 134,810,294`
(`pfn = 526,602`, offset 182). Both stores took the **RAM branch** (`glyph_isa_v2.py:739-743`) — i.e. the PTE
walked for those addresses carried neither `PTE_PIX` (0x8) nor `PTE_HILB`, so a `pfn`-shaped field was used as a
page-frame number and the engine materialised the whole span below it as zeros.

## Stage 5 — the two words the walk used as PTEs, NAMED

Artifact `output/probe_gh18_alloc_site5_2026091314.json` (same replay; at each extension the probe scans
`cpu.memory[:16384]` — where a page table must live — for words whose `>> 8` equals the implied `pfn`):

| step | implied `pfn` | RAM word | value | low byte | walk verdict |
|---|---|---|---|---|---|
| 298 | 67,593 | **1538** (`pt_base` 1536 + vpn 2) | `0x01080907` (bytes `07 09 08 01`) | `0x07` = `PTE_V\|PTE_W\|PTE_U` | accepted as a valid, writable, user PTE ⇒ RAM branch |
| 371 | 526,602 | **1539** (`pt_base` 1536 + vpn 3) | `0x08090A07` (bytes `07 0A 09 08`) | `0x07` = `PTE_V\|PTE_W\|PTE_U` | accepted as a valid, writable PTE ⇒ RAM branch |

Exactly one RAM word matches each implied `pfn` — the walker is reading the page-table window at `pt_base = 1536`,
and those two slots hold byte-run data whose bottom three bits satisfy the store walk's whole validity test
(`tools/glyph_isa_v2.py:710` checks only `PTE_V`, `PTE_W`, and `PTE_U` for USER — all three are present by
coincidence of the data). The store path then applies `paddr = pfn * PAGE_WORDS + offset` with **no bound**
(`:740-743`, `pfn` is a 24-bit field). The engine's own comment at `:632-636` documents this hazard class
("bake-time text garbage under the PT window") and mitigates it with RAM-before-image *ordering* — which cannot help
when the garbage is in RAM and passes the flag test.

**Not proven here:** why slots 1538/1539 hold those bytes (kernel program write, bake layout, or image stamp) — that
is the first probe of the fix tick, and option 1 in
`.builder_queue/REPAIR_PENDING_defect23_paged_flat_memory.md` exists for that reason.

## How this closes the leg-A number

Leg A's file-local peak was **2652.9 MB** isolated (and 2684.3 MB whole-run). This tick's chain: base ~231 MB
+ engine list 1078 MB + receipt copy 1189 MB ≈ **2.50 GB** live at the peak, inside the same file, in the same
mode, at the same test. That is the unexplained ~1.9 GB, named at three levels (stage attribution → allocation
line → step and store).

**Scope of the claim:** measured for `syscall_abi_kernel_image(mode="paged_dispatch", timer_quantum=35)` driven by
`GlyphRunner(out, ram_words=16384).run(...)`. `grep -rn paged_dispatch tests/` finds exactly **one** arc consumer,
`tests/test_gh18_syscall_abi.py:403` (`test_gh18_syscall_table_window_reserved`) — the same test the previous tick's
`-v` line stream bracketed. So this is a **test-shaped** peak: one mode, one test, two stores.

## What this PASS does NOT prove

* **The PTE values were not captured.** The `pfn`/offset numbers above are arithmetic from the observed list
  length; which image word the walker read, and whether that word is a corrupt PTE, a legitimate large `pfn`, or a
  mis-set flag, is **not** measured. That is the first probe a fix tick should run.
* **Whether the two stores are semantically required** is not established. The test passes with them; nothing here
  says the stores' *targets* matter to any assertion.
* **No fix, no policy, no cap, no exclusion** was applied, and no gate-bearing file changed. This tick adds
  evidence to two existing design tickets and files one new ticket; it does not close any of them.
* `n=1` per stage (seed 2026091314). The *extension arithmetic* is deterministic (a store at step 298/371 of a
  fixed image), but the leg-A spike *position* is seed-dependent; only the identity is claimed, not the timing.
* Nothing here says the production/resident path (non-`paged_dispatch`) has this behaviour: for `baseline` and
  `admit` the same instrument reads 0.13–0.14 MB.
* No substrate read this tick (teleop not exercised); no VCC/arc run (no gate-bearing file changed).

## Artifacts

```
.builder_queue/probe_gh18_alloc_site.py    output/probe_gh18_alloc_site_2026091314.json
.builder_queue/probe_gh18_alloc_site2.py   output/probe_gh18_alloc_site2_2026091314.json
.builder_queue/probe_gh18_alloc_site3.py   output/probe_gh18_alloc_site3_2026091314.json
.builder_queue/probe_gh18_alloc_site4.py   output/probe_gh18_alloc_site4_2026091314.json
.builder_queue/probe_gh18_alloc_site5.py   output/probe_gh18_alloc_site5_2026091314.json
```

Ticket: `.builder_queue/DEFECT-23_paged_flat_memory_growth.json`; design question and options:
`.builder_queue/REPAIR_PENDING_defect23_paged_flat_memory.md`.

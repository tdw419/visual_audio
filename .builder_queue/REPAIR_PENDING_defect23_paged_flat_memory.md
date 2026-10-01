# REPAIR_PENDING — DEFECT-23: the paged walk accepts a data word as a PTE, then materialises GBs of zeros

**Status:** OPEN — needs a design decision before any code change. **Filed:** 2026-09-13 14:3x CDT by builder cron
`af3e62239ce2`, the tick that measured the leg-A transient (`systems/RECEIPT_DEFECT22_GH18_PAGED_MEMORY.md`).
**Type:** engine memory-model / fault-policy question (the *instance* is measured; the *policy* is not mine to pick).
**Seat:** Jericho. **Ticket:** `.builder_queue/DEFECT-23_paged_flat_memory_growth.json`.
**Siblings:** `REPAIR_PENDING_worker_cgroup_memory_limit.md`, `REPAIR_PENDING_suite_iso2_memory_containment.md`
(both were configured *around* a quantity this note names) and, by discipline, ENG-1 / `INTEGRITY_FAIL` /
`REFUSAL: RV x31` (a detectable failure must not be silent).

## The measurement (not a hypothesis)

`syscall_abi_kernel_image(mode="paged_dispatch", timer_quantum=35)` driven by
`GlyphRunner(out, ram_words=16384).run(max_instructions=60000, trace=True)`, stepped one instruction at a time:

| step | pixel PC | mode | engine `memory` | the word the walk used as a PTE |
|---|---|---|---|---|
| 298 | (20, 23) | USER | 16,384 → 17,304,265 words | RAM word **1538** = `0x01080907` (low byte `0x07` = V\|W\|U) ⇒ `pfn = 67,593` |
| 371 | (24, 22) | SUPER | 17,304,265 → **134,810,550** words | RAM word **1539** = `0x08090A07` (low byte `0x07` = V\|W\|U) ⇒ `pfn = 526,602` |

Final state: **134,810,550 words — 1078.48 MB of a bare Python list — holding 27 nonzero words.** The engine is
freed when `run()` returns, but `runner.py:132` first copies the whole list into the receipt (**1189.08 MB**), which
the test then holds: peak `VmHWM` 2289.3 MB, retained `VmRSS` 1261.5 MB. `baseline` and `admit` modes, same
instrument, same process shape: 16,384 words, 0.13–0.14 MB. The measurement discriminates.

The mechanism is two lines apart in `tools/glyph_isa_v2.py`:

* **line 710** — the store walk's validity test is `not (pte & PTE_V) or not (pte & PTE_W) or (USER and not (pte & PTE_U))`:
  **the low byte only**. Any word whose bottom three bits happen to be `0x07` is a valid, writable, user-accessible PTE.
* **lines 740-743** — `paddr = pfn * PAGE_WORDS + offset` with `pfn = pte >> 8` (a 24-bit field, up to ~4.3e9 words)
  and **no bound**: `memory.extend([0] * (paddr + PAGE_WORDS - len(memory)))`.

The comment at lines 632-636 already documents the hazard class ("bake-time text garbage under the PT window") and
mitigates it with RAM-before-image **ordering** — which does not help here, because the garbage is *in RAM* and
passes the flag test. The bytes of the two words (`07 09 08 01`, `07 0A 09 08`) look like run-length/byte data, not
PTEs.

## The options (cheapest first)

1. **Name the writer of slots 1538/1539, then zero or correct them.** The indices and values are now known
   (`pt_base = 1536`, so `vpn = 2, 3`). If the `paged_dispatch` bake is supposed to leave them as invalid/zero PTEs,
   this is a bake-layout fix with no engine change and no fault-policy decision. **Cost:** one probe (which code
   writes 1538/1539, and what the walk *should* see). **Risk:** these slots may be deliberately stamped (the GH-25
   contract stamps a Hilbert PTE into image pixels only; a RAM stamp with the wrong layout is itself the defect).
2. **Bound the extension and fault loudly (E-PTEGARBAGE-class).** In the two walk sites: if `pte & PTE_V` but
   `pfn * PAGE_WORDS` exceeds a declared ceiling, take the existing fault path with a named marker instead of
   extending. ~6 lines, reuses landed fault plumbing. **Cost:** the ceiling's value/default is a policy choice
   (and the fault must be distinguishable from E-K1). **Risk:** a legitimate large-`pfn` RAM page would become a
   fault — none is known today, but that is exactly the judgement to make explicitly.
3. **Sparse memory (materialise pages, not spans).** A store to `paddr = 134e6` then costs one 256-word page
   instead of 1.08 GB, and the class of failure disappears. **Cost:** engine memory-model change; every landed
   receipt that asserts `len(memory)`/indexes it as a flat list, plus the WGSL twin, must be re-derived — a
   worktree-isolated round, not a tick. **Risk:** the largest, and it rewrites claims rather than adding a guard.
4. **Shrink the receipt copy (`runner.py:132`).** Copy only what the receipt's consumers read (or a sparse
   encoding). Halves the retained number and nothing else; rewrites the receipt contract that landed gates index
   into. **Cost:** medium, and it treats the symptom.

## Why this is filed instead of fixed

The measured half is mechanical; the change is not. A fix either (a) edits the engine's translation semantics —
`tools/glyph_isa_v2.py` is a core file, so AGENTS.md's worktree isolation applies and every paged/pixel/hilbert
claim must be re-derived — or (b) picks a **default ceiling and a fault vocabulary**, which is a policy decision the
loop does not self-apply. Per the skeleton contract: if a locked behaviour looks wrong, file the options, hold, and
pick the next eligible unit. **There is no next eligible unit** (`.builder_queue/REPAIR_PENDING_lane_supply_exhausted.md`;
`python3 tools/supply_census.py` → `TOTAL=59 OPEN=0`), so this note is also the loop's supply state.

## Candidate gate for whichever option is ruled (drafted now, not landed)

`tests/test_defect23_pfn_bound.py` (module absent ⇒ RED, pytest exit 4):

* **L1 (falsifier, the measured instance):** bake `paged_dispatch`, stamp RAM word `pt_base+2` with `0x01080907`
  (the measured garbage) and issue the store at pc (20,23) that step 298 performed — the engine must **NOT** grow
  `memory` past a declared ceiling and must record a **named** fault (or route to the image); asserted against the
  pre-fix behaviour, which grows to 17,304,265 words with **no** fault.
* **L1b (non-vacuity — a guard that refuses everything is not a guard):** a legitimate small-`pfn` PTE
  (`PTE_V|PTE_W|PTE_U`, `pfn` inside the declared ceiling) must still store and still grow within the bound.
* **L2 (the regression that matters):** `tests/test_gh18_syscall_abi.py` stays green — 14/14, and the file's
  isolated peak `VmHWM` is re-measured (pre-fix 2652.9 MB, post-fix expectation < 500 MB), reported as a number,
  not a claim.
* **L3 (parity honesty):** if the fix is engine-side, state whether the WGSL twin has the same acceptance rule; if
  the twin differs, the difference is a claim that must be written down (WF-1's discipline).

## UPDATE 2026-09-13 14:2x — the writer is NAMED, and it is an arming-loop typo

**Filed by:** builder cron `af3e62239ce2`, same tick. **This answers option 1's prerequisite and
reclassifies the ticket from "policy decision" to "one-line bake fix awaiting sign-off".**

**Probe (this tick):** `.builder_queue/probe_defect23_pt_slot_writer.py` →
`output/probe_defect23_pt_slot_writer_2026091314.json` (pre-fix / main tree) and
`output/probe_defect23_pt_slot_writer_2026091314_worktree_fixed.json` (fix present).

**Q1 answered — the words are written at RUN TIME, not stamped by the bake.** RAM 1538/1539 read
`0` before any instruction retires in **all three** modes (`baseline`, `admit`, `paged_dispatch`);
no image pixel carries their 24-bit triple either (zero hits in both)). The writer is kernel code
at **pixel pc (16,11), MODE_SUPER**, at steps **181, 195, 209, 223, 237, 251, 265, 279** — a
14-step cadence that matches the arming loop's instruction count exactly.

**Mechanism — `:__g18_ptloop`, `tools/glyph_gpt/baker.py:5210-5225`.** The loop's per-iteration
MOV is written as `ADD r14 r13` and **`r14` is never initialised**, so the "identity" PTE
accumulates:

    r14(n) = ((r14(n-1) << 8) | 7) + n        r14(-1) = 0x150001 (prologue leftover)

| slot | intended `(vpn<<8)|7` | measured pre-fix |
|---|---|---|
| 1536 | `0x007` | `0x15000107` |
| 1537 | `0x107` | `0x0010807` |
| 1538 | `0x207` | `0x01080907` | 
| 1539 | `0x307` | `0x08090A07` |
| 1540 | `0x407` | `0x090A0B07` |
| 1541 | `0x507` | `0x0A0B0C07` |
| 1542 | `0x607` | `0x0B0C0D07` |
| 1543 | `0x707` | `0x0C0D0E07` |

All eight observed values are reproduced **exactly** by that recurrence (arithmetic check this
tick), including the 32-bit truncation that turns `0x15000108 << 8` into `0x00010800`. So the
`pfn` values the walk later used (67,593 / 526,602 ⇒ 17.3M / 117.5M words) are not random
garbage: they are the *tail of an accumulator*, which is why the two growth events are ~7× apart.

**The bake is innocent and the intent is documented in-code.** The comment at
`baker.py:5198-5209` states the contract ("Arm the GH-17 page table with an identity map of the
low 8 pages… Identity PTEs are `(vpn << 8) | flags`"). The code fails its own comment. Compare the
**other** writer of this window: `admit` mode's per-slot arming (`baker.py:5155-5181`) writes
explicit constants and produces exactly `[0x7, 0x107, 0x207, 0x307, 0x407, 0x507, 0x50F, 0x707]`
(slot 6 = `(5<<8)|0xF`, the documented vpn-6 PIX remap). Measured this tick by
`tests/test_defect23_pt_identity.py::leg3`.

**Fix, verified in worktree isolation (AGENTS.md § Blast-Radius Containment):** branch
`defect23-ptloop-init` at `/home/jericho/zion/worktrees/defect23-ptloop`, commit **`6d8ab81`** —
one line, `LDI r14 0` before `ADD r14 r13`, plus a comment naming DEFECT-23, plus the new gate
`tests/test_defect23_pt_identity.py` (L1 falsifier / L2 non-vacuity / L3 discrimination).
**The main branch is untouched** — this is evidence, not a landing.

| leg | command (same on both trees, same instrument) | RED (main, pre-fix) | GREEN (worktree, fix) |
|---|---|---|---|
| gate | `python3 -m pytest tests/test_defect23_pt_identity.py -q` | **2 failed, 1 passed** (`slot 0 must be 0x7, got 0x15000107`) | **3 passed** |
| arc consumer | `/usr/bin/time -v python3 -m pytest tests/test_gh18_syscall_abi.py -q` | 14 passed, `Maximum resident set size: 2,350,292 kB` | 14 passed, `Maximum resident set size: 243,204 kB` |
| probe | `probe_defect23_pt_slot_writer.py` | 8 slots garbage, growth 17.3M then 117.5M words | slots `0x7…0x707`, **growth 0** over 380 steps |

Peak **2,350,292 kB → 243,204 kB (9.7×)**, wall 9.04 s → 3.85 s, 14/14 green on both sides.
Raw tails: `output/defect23_ptloop_gate_red.txt`, `output/defect23_ptloop_gate_green.txt`,
`output/defect23_gh18_main_prefix*.txt`, `output/defect23_gh18_worktree_postfix*.txt`.

**What the GREEN does NOT prove** (stated for the landing note): the WGSL twin is not re-derived;
non-identity maps are untested (this image has none); and **the engine's low-byte-only PTE
validity test is untouched** — option 2 remains un-hardened, so a future writer of `0x…07` into
the PT window is still accepted and still extends `memory` without bound. Option 1 removes the
observed trigger, not the class. Also NOT proven: that the fixed identity map leaves *every*
landed paged_dispatch receipt's status words unchanged — only `tests/test_gh18_syscall_abi.py`
(the one arc consumer named in the ticket) was re-run.

**Hazard found while producing this evidence (worth a line in the loop's discipline):**
`git stash` is **repo-global across worktrees**. A `git stash push <file>` inside a *linked*
worktree silently no-ops when that file is already committed, and the following `git stash pop`
then applies the stack's top entry — which may belong to another session or another branch.
That happened this tick: a pop dragged an unrelated `emulator-v2-baseline` stash into the
worktree (`UU` on three files). Recovered with `git reset --hard HEAD` in the worktree only; the
stash stack was verified intact (5 entries, top entry unchanged) and the correct RED was then
produced by checking out `6d8ab81~1 -- tools/glyph_gpt/baker.py` instead of stashing. No work
from any other session was lost, and the main tree was never touched by the pop.

**Requested decision (Jericho):** land `6d8ab81`'s one-line fix on `glyph-transpiler-autoloop`
(the gate and the branch are ready), or reject it. Option 2 (a pfn ceiling + named fault) is now
a separate, smaller question: with the arming loop fixed, the engine's unbounded extension has no
known live trigger — but it is still one bad word away.

## LANDING PACKET — independent verification added 2026-09-13 14:4x CDT by the orchestrator tick (cron `af3e62239ce2`)

The branch's own numbers were re-derived on my instruments rather than read from its commit body. Same file, same
command, same instrument (`/usr/bin/time -v`) on both trees:

| tree | command | result | peak RSS | wall |
|---|---|---|---|---|
| pre-fix (`6d8ab81~1` baker.py, checked out **by path**) | `pytest tests/test_defect23_pt_identity.py -q` | **2 failed, 1 passed**, exit 1 | — | — |
| pre-fix | `/usr/bin/time -v pytest tests/test_gh18_syscall_abi.py -q` | 14 passed | **2,351,292 kB** | 10.28 s |
| fixed (`6d8ab81`) | `pytest tests/test_defect23_pt_identity.py tests/test_gh18_syscall_abi.py -q` | **17 passed**, exit 0 | **245,380 kB** | 8.33 s (both files) |

The pre-fix failure is at `tests/test_defect23_pt_identity.py:99`, asserting `352321799 == ((0 << 8) | 7)`.
**My measured discriminating power is 2 of 3 legs** — the commit body records "3 failed in 3.25s"; that third leg
passes on the pre-fix tree in my run. The RED is real; the count does not reproduce, and the honest figure is 2/3.
Peak-RSS reduction measured by me: **9.58×** (the commit's 9.7× is inside instrument noise). Fix restored by path
afterwards; `baker.py` md5 `024a9e6d0da178d15082124b8a6ca868` on both sides of the measurement.

If you land it, the landing is these commands in this order (from the main checkout):

1. `git status --short` — no *modified tracked* file may be present (other seats' untracked files are expected here).
2. `git cherry-pick 6d8ab81` — the fix commit only (2 files: the `+12` in `tools/glyph_gpt/baker.py` and the new
   gate). **Do not merge the branch tip wholesale:** the branch predates `85fdaeb`/`1f41fe7`, so its merge diff would
   also delete the evidence artifacts those commits landed.
3. `python3 -m pytest tests/test_defect23_pt_identity.py tests/test_gh18_syscall_abi.py -q` ⇒ expect **17 passed**.
4. **Arc run on the merged tree** — `baker.py` is a core file (AGENTS.md § Blast-Radius Containment). Heavy sweeps go
   through the wide scope per RULING_worker_memory_containment (a):
   `bash ~/.hermes/scripts/suite_sweep.sh -b 12G -w 4 -- <arc command>`.
5. The commit message must carry the RED and GREEN tails literally plus the "what this PASS does not prove" section
   (the branch's own message already does; keep it).

Touching option 2 later does not conflict with this landing: they are complementary (option 1 removes the observed
trigger, option 2 guards the class).

## LANDED — 2026-09-13 19:4x UTC (cron `af3e62239ce2`), commit `c7995a7`

Option 1 is on main. `git cherry-pick 6d8ab81` onto `1833ba0`; message rewritten so the landed commit's own receipt
is self-consistent (the cherry-picked body still said "this branch is the evidence, not the landing"). Authority,
evidence and the flippability note: `.builder_queue/RULING_defect23_option1_landing.md`.

Re-derived by me on the merged tree, not read from the branch:

- **Step-3 gate**: `python3 -m pytest tests/test_defect23_pt_identity.py tests/test_gh18_syscall_abi.py -q`
  → **17 passed in 3.62 s, exit 0**, peak RSS **244,956 kB** (pre-fix, same file: 2,351,292 kB).
- **Step-4 arc** (owed at landing — `baker.py` is a core file): `SEED=2026091315 bash ~/.hermes/scripts/suite_sweep.sh
  -b 12G -w 4 -- bash tools/arc_lega.sh` → `rc=0 crashes=0`, **325 passed, 1 skipped, 1 deselected** in 126.46 s,
  `oom_kill_delta=0`, scope peak **816 MB**. Verdict matches the pre-fix arc at `9bd8dd2` (seed 2026091305): 325/1/1.
- **New datum at suite scale**: leg A's scope peak **2,970 MB inside a 4.0 GiB worker scope (72.5 % of cap)** pre-fix
  → **816 MB (6.8 %)** post-fix. Honest caveats: seeds differ (order differs), scope widths differ (4 GiB vs 12 GiB),
  and peak is scope-wide — the tighter per-file instrument above is the step-3 pair.
- **A RED that was not this diff**: the isolated gate first returned `1 failed` on
  `test_gh18_admit_syscall_via_ingest_end_to_end` — a `TimeoutError` at 120.66 s in an Ollama socket read with
  `nvidia-smi` at 100 % and `qwen2.5-coder:14b` resident. The same leg passed in the three newest pre-fix arc runs and
  in the landing arc itself, same code. Filed as **DEFECT-24**
  (`.builder_queue/DEFECT-24_arc_live_ollama_gate.json`), not a blocker here.

**Still open and still the seat's:** option 2 — the engine's low-byte-only PTE validity test (`tools/glyph_isa_v2.py:710`)
plus the unbounded `pfn` extension (`:740-743`). The observed trigger is gone; the class is not guarded.
**Not verified at landing:** the WGSL twin (not on this path), non-identity maps (the `paged_dispatch` image has none),
and "leg A is OOM-proof at rest" (816 MB is one seeded order's peak, not a bound).

# BRIEF — DEFECT-23-ROOT step 2: page-table window container tag (seat-ruled Option 1)

**Roadmap row:** `systems/GLYPH_SELF_HOSTING_ROADMAP.md:360` — `DEFECT-23-ROOT` (⏳ queued; step 1 landed `67be5c9`, seat ruling landed `912ebe2`).

**Read first (spec, not this summary):** `.builder_queue/RULING_defect23_root_pte_acceptance.md` (the seat's
ruling — Option 1 adopted, what it does NOT close, the declined options, and the implementer constraints);
then the row at `:360`; then `tests/test_defect23_pte_acceptance.py` (step 1's landed gate — L1/L2 are STRICT
xfail pins, L3/L4/L5 green) and `.builder_queue/probe_defect23_pte_acceptance.py` (the measured probe +
`PROBE_VERDICT: SILENT_MISDIRECTION_CONFIRMED`).

## What to build (Option 1, verbatim from the ruling)

A page-table window must carry a **magic/version header word at its base** (`memory[pt_base]`, or the walk's
equivalent header slot) **before any slot in that window is trusted as a mapping**. A window whose header does
not match **refuses through the existing fault path** (`fault_reason` names the mismatch), exactly like the
landed ceiling containment.

Both walk sites must enforce it: the LD walk (`tools/glyph_isa_v2.py:641-706`) and the ST walk
(`tools/glyph_isa_v2.py:710-800`). Keep the two sites in one declared rule (a single module-level constant for
the tag, and one shared predicate used by both) — the step 1 instrument exists precisely because the two sites
drifted apart (the LD path has no pfn ceiling at `:700`).

## The hard constraints (from the ruling — violating one means STOP AND REPORT, not adapt)

1. **No PTE value may change.** The words `0x7`, `0x107`, `0x507`, `0x01080907`, ... that producers bake and
   landed tests expect must be byte-identical after this change. If the tag cannot be added without changing a
   PTE value, **STOP and report** — that means the seat's Option-1 cost estimate was wrong and the ruling needs
   revisiting. Do not silently slide into Option 2 (a reserved bit on every PTE).
2. **`tests/test_defect23_pt_identity.py` and `tests/test_defect23_pfn_ceiling.py` must stay green** (both are
   landed, seat-confirmed).
3. **L3 (legit identity PTE still resolves), L4 (mechanism pin), L5 (ceiling containment) must stay green.**
   L4 currently documents the PRE-fix acceptance rule — when the rule changes, update L4 *deliberately* and say
   in the test that it now pins the post-ruling rule.
4. **L1/L2 may legitimately stay strict-xfail.** The ruling states plainly that Option 1 closes the
   *untagged-`pt_base`* vector, NOT the narrower in-window slot case (a garbage word sitting inside an
   otherwise-correctly-tagged window still misdecodes). If L1/L2 do not flip green, that is EXPECTED: update
   their `reason=` to say precisely what Option 1 closed and what remains open, and do NOT weaken their setup to
   force a green. If they DO flip green, verify why before trusting it (confirm the fix isn't accidentally also
   closing the in-window slot case — if it is, say so; that is a pleasant surprise to understand, not to accept
   silently).
5. **Windows declared by producers must carry the header**, or every existing paging path would start faulting.
   Enumerate the producers from the inventory below and stamp the tag in each *before* the slot writes:
   `tools/glyph_gpt/baker.py` (GH-17 arming / window bake; note the file is a CORE file → worktree isolation,
   see below), `tools/geos_aspace.py`, `tools/glyph_gpt/gh25_hilbert_paging.py`, and the window-building test
   harnesses (`tests/test_defect23_pt_identity.py`, `tests/test_defect23_pfn_ceiling.py`,
   `tests/test_defect23_pte_acceptance.py`, `tests/test_gh25_hilbert_paging.py`,
   `tests/test_osskel_engine_switch.py`, `tests/test_osskel_aspace_switch.py`, `tests/geos_engine_sink.py`).
   Measured inventory (this tick): 23 files mention `PAGE_TABLE_ADDR`/`pt_base`; the walk appears twice in the
   tree — `tools/glyph_isa_v2.py` and `glyph_dispatch/src/glyph/glyph_isa_v2.py` — and the WGSL twin at
   `tools/wgsl_glyph_isa_v2.py`.
6. **WGSL twin:** if the walk gains a tag check, a lockstep/parity claim about paging requires the twin to
   refuse identically. Mirror the check in `tools/wgsl_glyph_isa_v2.py:643-660`, or if you judge the twin cannot
   be mirrored within this step, **say so explicitly in the hand-back** and add the bound to the relevant claim
   surface — do not leave an unchecked parity claim behind.

## Header-slot choice (you decide, and you must document it)

`memory[pt_base]` is where `vpn == 0`'s PTE would live (`pte_idx = pt_base + vpn`), so putting the header there
collides with slot 0. Pick a header slot that does not move any existing PTE *value* and does not break the
landed tests' window layouts, and write the choice + the reasoning into the code comment and the receipt. If no
such slot exists without changing a PTE value or a landed window layout, that is constraint 1's STOP condition.

## Deliverables

1. The engine change (both walk sites, one declared tag rule).
2. Producer stamping so every existing window carries the header.
3. Updated gate legs in `tests/test_defect23_pte_acceptance.py` (L4 rewritten deliberately; L1/L2 reasons
   updated per constraint 4; add a leg that proves the tag is REQUIRED — an untagged window faults with the
   mismatch named — and that it is not vacuous).
4. A receipt `systems/RECEIPT_DEFECT23ROOT_WINDOW_TAG.md` carrying: the RED tail before the change, the GREEN
   tail after, the literals, and a **"what this does NOT prove"** section (the ruling's § "What Option 1 does
   NOT close" belongs there).
5. `output/` artifacts for both runs; raw tails, no invented numbers.

## Gate commands (run them; paste the tails literally)

```
cd /home/jericho/projects/zion/projects/visual_audio
python3 -m pytest tests/test_defect23_pte_acceptance.py tests/test_defect23_pt_identity.py tests/test_defect23_pfn_ceiling.py -q 2>&1 | tail -20
python3 .builder_queue/probe_defect23_pte_acceptance.py 2>&1 | tail -20
python3 -m pytest tests/test_gh25_hilbert_paging.py tests/test_osskel_engine_switch.py tests/test_osskel_aspace_switch.py -q 2>&1 | tail -10
```

Expected: zero failed; L3/L4/L5 green; L1/L2 xfailed strict **or** green-with-explanation (constraint 4);
`test_defect23_pt_identity.py` + `test_defect23_pfn_ceiling.py` fully green; the probe still shows the
in-window G2 misdirection (that case is explicitly NOT closed by Option 1).

## Scope — positive (the ONLY files this step may change)

- `tools/glyph_isa_v2.py` — the two walk sites (LD `:641-706`, ST `:710-800`) + one module-level tag constant/predicate.
- `tools/glyph_gpt/baker.py` — the GH-17 window bake / arming loop only (stamp the header).
- `tools/geos_aspace.py` — window construction (stamp the header).
- `tools/glyph_gpt/gh25_hilbert_paging.py` — window construction (stamp the header).
- `glyph_dispatch/src/glyph/glyph_isa_v2.py` — the dispatch-lane copy of the walk, kept in step with the engine.
- `tools/wgsl_glyph_isa_v2.py` — the twin's walk, per constraint 6 (or an explicit stated bound instead).
- `tests/test_defect23_pte_acceptance.py` — the gate legs named in Deliverables.
- Window-building harnesses that must stamp the header:
  `tests/test_defect23_pt_identity.py`, `tests/test_defect23_pfn_ceiling.py`,
  `tests/test_gh25_hilbert_paging.py`, `tests/test_osskel_engine_switch.py`,
  `tests/test_osskel_aspace_switch.py`, `tests/geos_engine_sink.py` — minimum edit needed for the stamped
  layout only, and say so in the hand-back.
- NEW: `systems/RECEIPT_DEFECT23ROOT_WINDOW_TAG.md`, `output/defect23root_window_tag_*`.

## Scope — negative (must NOT change)

- Any PTE **value** (constraint 1) — this is the STOP condition, not a preference.
- `.builder_queue/RULING_defect23_root_pte_acceptance.md`, `RULING_defect23_pfn_ceiling.md`,
  `tests/test_defect23_pfn_ceiling.py`'s containment assertions, `systems/GLYPH_SELF_HOSTING_ROADMAP.md`.
- No Option-2 reserved bit, no Option-3 bake-derived pfn bound, no Option-4 sparse-memory rewrite (all three
  are explicitly declined in the ruling) — do not compose them in.
- `tools/rv64i_to_glyph.py`, WGSL shaders other than `tools/wgsl_glyph_isa_v2.py`, `glyph_dispatch/**` other
  than the walk copy, any unrelated test, any unrelated `.builder_queue/` file.

## Blast radius / isolation

`tools/glyph_gpt/baker.py` and `tools/glyph_isa_v2.py` are CORE files → **worktree isolation per AGENTS.md**.
Do the work in an isolated worktree off HEAD, run every gate above there, and report the worktree path + the
gate tails; the orchestrator lands it.

## Definition of done

Every gate command above pasted with its real tail: zero failed; L3/L4/L5 green; L1/L2 xfailed-strict **or**
green-with-explanation (constraint 4); the identity + ceiling gates fully green; the probe still shows the
in-window G2 misdirection; receipt written with the RED→GREEN pair and the "what this does NOT prove" section.

**Interfaces are LOCKED. Never weaken a live guard to make a step pass. DO NOT COMMIT.** The orchestrator
re-runs every gate on the merged tree and commits.

# RULING — DEFECT-23-ROOT: PTE acceptance rule

**Date:** 2026-09-14 · **Seat:** Jericho, explicitly delegated this turn
**Covers:** `.builder_queue/REPAIR_PENDING_defect23_pte_acceptance_rule.md`
**Gate:** `tests/test_defect23_pte_acceptance.py`

## Verified before ruling

Independently reproduced the ticket's G2 measurement (not trusted from the probe
transcript alone): `ST` through PTE slot value `0x00000907` (pfn=9, a garbage word
that merely happens to carry valid-looking low-byte flags) does not fault. The store
silently lands at word 2394 (frame 9) instead of the intended word 1370, and word
1370 is left untouched at 0. `faulted=False` confirmed live. This is the defect the
options below address.

## Decision: adopt Option 1 (page-table window container tag) now

A page-table window must carry a magic/version word at its base (`memory[pt_base]`,
or the walk's equivalent header slot) before any slot in that window is trusted as a
mapping. A window whose header doesn't match refuses through the existing fault path
(`fault_reason` names the mismatch), exactly like the landed ceiling containment.

Rationale:
- **Cheapest option that changes zero PTE values.** No landed receipt's expected
  `0x7`/`0x107`/... word moves; no WGSL twin PTE reference changes.
- **Directly targets the observed root-cause mechanism.** DEFECT-23's origin was
  `baker.py` miscalculating `pt_base` into arbitrary code/data words (the arming-loop
  bug already fixed at `c7995a7`). A magic-tag check specifically closes "pt_base
  points at something that was never a page-table window at all" — an arbitrary
  code/data word is astronomically unlikely to coincidentally carry the chosen magic
  constant.
- **Proportionate to current evidence.** The ticket's own instrument explicitly does
  NOT prove this defect fires in any live OS workload — only the earlier, already-
  fixed `paged_dispatch` authoring bug did. No evidence yet justifies Option 2's
  full-format rewrite (every PTE producer, the WGSL twin, every landed receipt) or
  Option 4's sparse-memory rewrite.

## What Option 1 does NOT close — stated plainly, not oversold

Option 1 closes the untagged-`pt_base` vector. It does **not** close the narrower
case the ticket itself names: a garbage word sitting in a slot *inside an otherwise
correctly-tagged window* (e.g. an uninitialized or aliased slot within a real table)
still misdecodes exactly as measured above, because the tag validates the window,
not each slot. That means `test_l1_small_pfn_garbage_st_desired_contract` and
`test_l2_small_pfn_garbage_ld_desired_contract` — as currently written, seeding the
garbage word into an otherwise-legitimate, already-tagged table — will very likely
**still XFAIL after Option 1 lands**, and that is expected, not a sign Option 1 was
implemented wrong. Do not force those two legs green by weakening the test's setup
to dodge this; if they don't flip, update the xfail reason to say precisely what
Option 1 closed and what remains open, and file the slot-level gap as its own
follow-up rather than silently declaring victory.

## Explicitly declined for now

- **Option 2** (reserved tag bit on every PTE) — the only option that makes a data
  word structurally unrepresentable as a PTE at the slot level, but at an order-of-
  magnitude higher cost (every producer, `baker.py:5155-5225`, GH-25/GH-17 test PTEs,
  `tools/geos_aspace.py`, the WGSL twin's 43 references, every landed receipt).
  Revisit only if Option 1 proves insufficient in a reproduced live-workload instance,
  not preemptively.
- **Option 3** (bake-derived pfn bound at both walk sites) — NOT composed with Option
  1 in this ruling, because the ticket is explicit that Option 3 collides with the
  landed ceiling gate's L2 (which deliberately grows memory to pfn=100) and requires
  first deciding whether grow-on-demand past RAM stays a supported mapping. That is a
  separate policy question. It is not decided here and must not be bundled into this
  implementation.
- **Option 4** (sparse memory model) — disproportionate; no evidence justifies an
  engine-wide rewrite for a defect not yet shown to fire in a live bake.

## Constraints for the implementer

- Engine work → worktree isolation per AGENTS.md (this touches the walk's shared
  acceptance path, same discipline as the ceiling containment).
- `tests/test_defect23_pt_identity.py` and `tests/test_defect23_pfn_ceiling.py` (both
  landed, seat-confirmed) must stay green.
- L3 (legit identity PTE still resolves), L4 (mechanism pin, rewritten to match the
  new rule), L5 (ceiling containment) must stay green.
- If L1/L2 do not flip green, that is acceptable under this ruling — see above. If
  they DO flip green, verify why before trusting it: confirm the fix isn't
  accidentally also closing the in-window slot case (in which case say so, it would
  be a pleasant surprise worth understanding, not just accepting).
- No PTE value may change as part of landing Option 1. If an implementer finds this
  impossible without a value change, STOP and report — that means my Option-1 cost
  estimate was wrong and this ruling needs revisiting, not silent scope creep into
  Option 2.

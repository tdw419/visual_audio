# DEFECT-30 — stale L4 pin in test_defect23_pte_acceptance.py went RED after the 5-site naming pass

**Filed:** 2026-09-16 ~12:20 CDT, orchestrator cron af3e62239ce2
**Status:** FIXED this tick (test-side pin update, no engine change). Ticket kept as the record.
**Severity:** low (stale assertion, not a product defect — the engine behavior is correct per the landed ruling)

## Symptom

`tests/test_defect23_pte_acceptance.py::test_l4_user_mode_mechanism_pin` RED at HEAD `fd24c76`:

```
>       assert getattr(cpu_st_refuse, "fault_reason", None) is None, "refusal is at PTE walk, not extend site"
E       AssertionError: refusal is at PTE walk, not extend site
E       assert 'pte_invalid pte=0x1080906 vaddr=0x1568 mode=USER op=ST site=glyph_isa_v2' is None
```

## Root cause (measured, not inferred)

L4 line 151 was written 2026-09-14 (67be5c9/13d94a9) to pin that ST's USER-mode
PTE-U refusal fired at the paged walk **silently** (`fault_reason is None`).

Commit `26a29b7` (2026-09-16 10:44, the Pillar 1.2 "5 remaining sites"
classification pass) then **named** exactly that branch — ST's pte_invalid
fault now sets `fault_reason = "pte_invalid pte=… mode=… op=ST
site=glyph_isa_v2"`, matching its tag-mismatch siblings, per the recorded
ruling. The silent-fault pin became false by design.

**Bisect (isolated harness, `.builder_queue/orch_l4_isolate_20260916.py`,
engine revision swapped under the unchanged test):**

| engine rev | L4 verdict |
|---|---|
| `3814e66` (L4 landing, 09-14) | PASS |
| `dfc6126` (halt_reason, 09-16 08:02, PRE-naming) | PASS |
| `26a29b7` (5-site naming, 09-16 10:44) | **FAIL** — exact symptom string |
| `fd24c76` (HEAD) | **FAIL** |

⇒ introduction is exactly `26a29b7`. No engine file changed this tick (twins
md5-identical `a20311a1…` before and after).

## Why nothing caught it

`tools/arc_lega.sh` (arc leg A) globs `tests/test_defect1*.py` — the
`test_defect23_*` cluster is NOT in the arc. Arc leg A at `fd24c76`
(seed=202609162): **323 passed / 1 skipped / rc=0** (own run this tick), green
while the L4 pin was red. The DEFECT-23-ROOT cluster is only exercised when
run directly. 26a29b7's own 65-test verification sweep and addendum 101's
re-verification both ran `test_glyph_pte_invalid_fault_reason.py` (the new
gate) but never the older `test_defect23_pte_acceptance.py` (the stale one).

## Fix (this tick)

`tests/test_defect23_pte_acceptance.py:148-165` — the pin is updated to the
post-naming contract and made STRONGER, not weaker:

- `fault_reason` must be non-None (walk site names the fault — the 26a29b7 ruling)
- must contain `pte_invalid` and `op=ST` (identifies the walk site)
- must NOT contain `ceiling` (an extend-site string would mean the refusal
  fired at the wrong site — the original pin's actual concern, now enforced
  positively instead of via a None check)

**RED-first evidence:** isolation run above — updated L4 against the
pre-naming engine (`dfc6126`) goes RED with "walk-site refusal must be named";
against live HEAD it passes. The updated pin discriminates the two engine
generations; it cannot pass vacuously.

**Post-fix:** `tests/test_defect23_*` + `test_glyph_pte_invalid_fault_reason.py`
+ `test_glyph_halt_reason.py` → **27 passed / 2 xfailed, rc=0**; wider sweep
(gh17/gh25/bk2/se024×2/se022a/gh4/gh9×2/defect-d/pte_invalid/halt_reason) →
**58 passed / 1 skipped**; twins byte-identical; arc leg A 323P/1S rc=0.

## Follow-up filed

`tools/arc_lega.sh`'s `test_defect1*.py` glob predates the defect20/defect23
clusters. Widening the arc is a separate gated change (affects the pinned
arc denominator) — NOT done here. This ticket is the gap's record.

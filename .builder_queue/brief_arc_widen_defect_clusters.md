# BRIEF — arc-widen: pin tools/arc_lega.sh's selector to the full defect-cluster set

## Title

BRIEF — arc-widen: pin tools/arc_lega.sh's selector to the full defect-cluster set

## Spec pointer

`.builder_queue/DEFECT-30_stale_l4_pin_after_5site_naming.md` § Follow-up filed
(arc glob `test_defect1*` predates the defect20/defect23 clusters; a stale-red
pin in `tests/test_defect23_pte_acceptance.py::test_l4` survived arc-green for a
full tick because that file is invisible to the arc).

## Scope

POSITIVE (exclusive write set):
- `tools/arc_lega.sh` — FILES selector glob line only
- `tools/arc_lega_capture.sh` — mirrored FILES selector (byte-identical mirror rule)
- `tests/test_arc_selector_parity.py` — NEW gate module
- `tests/test_arc_determinism_audit.py` — `_get_arc_files()` pattern list only
- `.builder_queue/probe_arc_widen_red.sh` — RED-first probe
- `systems/RECEIPT_ARC_WIDEN_DEFECT_CLUSTERS.md` — receipt

NEGATIVE (must not touch):
- `tools/glyph_isa_v2.py`, `tools/wgsl_glyph_isa_v2.py`, `glyph_dispatch/**`,
  `tools/glyph_gpt/**`, `tools/rv64i_to_glyph.py` (sibling lane's live (d) work — hands off)
- pytest.ini markers, `-m "not live_smoke"` deselector
- the runner's seed-pinning, artifact-naming, OOM-survival, telemetry sections
- any engine or transpiler file

## Gate command

```
/usr/bin/python3 -m pytest tests/test_arc_selector_parity.py tests/test_arc_determinism_audit.py tests/test_instrument1_mark_registration.py -q -m "not live_smoke" -p no:randomly
```
Expected: exit 0, 13+ passed, 0 failed. Plus the full widened arc (see receipt)
exit 0 with the six defect-cluster files present in the run.

## Gate clause

`tests/test_arc_selector_parity.py` writes, when GREEN:
- L1: the selector line extracted from BOTH runner scripts (arc_lega.sh,
  arc_lega_capture.sh) names, after exclusion, all six known defect-cluster
  files: test_defect20_write_identity, test_defect23_bake_validation,
  test_defect23_pfn_ceiling, test_defect23_pte_acceptance,
  test_defect23_pt_identity, test_defect_d_ram_scoped_handlers.
  Refuses: any of the six absent from either script's expansion.
- L2: the two scripts' selector expansions are byte-identical to each other
  (mirror anti-drift). Refuses: divergence between the pair.
- L3: `_get_arc_files()` in test_arc_determinism_audit.py covers the same six
  files. Refuses: any of the six missing from the audit's file set.
- L4 (discriminating): a synthetic runner-content string using the OLD
  `test_defect1*` glob fails L1 (the gate detects the pre-widen selector).
Returns: pytest exit 0; the arc's own collected-file list contains all six.
What is refused: a future narrowing of any selector back below the full
defect-cluster set; a mirror drift between the two runners.

## Failure evidence (RED first — must be DISCRIMINATING)

`.builder_queue/probe_arc_widen_red.sh`, run at pre-change HEAD:
- LEG-A1: gate run with the glob monkeypatched to the OLD `test_defect1*` →
  audit legs FAIL (rc≠0) — proves the gate detects the old selector.
- LEG-A2: same gate, widened glob → PASS (rc 0) — proves the failure is the
  selector, not the gate.
- LEG-B: the new selector expansion names exactly the 6 cluster files,
  including `test_defect23_pte_acceptance.py` (the file whose stale-red pin
  went unnoticed).
Cannot pass by returning True: L1 extracts the selector from the REAL scripts
on disk and expands it via shell — a glob edit that doesn't actually widen the
expansion fails; L4 pins the negative shape.

## Interfaces LOCKED

The runner's public contract is locked and unchanged by this work: seed-pinning
semantics, artifact naming (`arc_lega_seed<SEED>_<HEAD>`), the sidecar JSON
schema, `-m "not live_smoke"` deselection, and exit-code passthrough. Only the
FILES glob line changes. `find_unmarked_live_tests()` in
test_arc_determinism_audit.py is locked; only its `_get_arc_files()` pattern
list is in scope.

## Definition of done

Brief's gate command exits 0; the widened arc runs end-to-end exit 0 with all
six defect-cluster files collected; the RED probe's LEG-A1/A2/B verdicts are
GREEN; receipt committed with both tails; `git status` shows only in-scope files.

## Never weaken a live guard

No live guard may be weakened to reach green: the `-m "not live_smoke"`
deselector, the exclusion list (`glass_box|gh24_s2_mcp`), the seed pin, and
L1–L4 of test_arc_determinism_audit.py stay intact. If a newly collected
defect-cluster file turns the arc RED, that red is a finding to be fixed or
ticketed — never an excuse to narrow the glob back.

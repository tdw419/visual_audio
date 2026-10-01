#!/usr/bin/env python3
"""One-shot: mark DEFECT-23 ticket CLOSED after option 2 landed at 5b62955 (verified by orchestrator cron af3e62239ce2, run 2026-09-14 ~08:10 CDT)."""
import json

P = ".builder_queue/DEFECT-23_paged_flat_memory_growth.json"
d = json.load(open(P))
if "OPTION 2 LANDED" in d["status"]:
    print("already closed; no-op")
    raise SystemExit(0)
d["status"] = (
    "CLOSED 2026-09-14 — both options landed. Option 1 @ c7995a7 (2026-09-13). "
    "Option 2 (seat-confirmed pfn ceiling 65536, RULING_defect23_pfn_ceiling.md + f217992) "
    "landed @ 5b62955: guard at the paged-ST memory.extend site (tools/glyph_isa_v2.py:764, "
    "twin glyph_dispatch/src/glyph/glyph_isa_v2.py byte-identical), fault reuses existing "
    "semantics with fault_reason evidence string, faulting store abandoned. "
    "Orchestrator re-verification on the merged tree (cron af3e62239ce2): "
    "tests/test_defect23_pfn_ceiling.py 3/3 (L1 containment-first falsifier pfn=526602, "
    "L2 legitimate pfn=100 growth, L3 in-RAM untouched); cluster re-run "
    "test_defect23_pt_identity + test_glyph_isa_v2 + test_run_containment + test_gh18_syscall_abi "
    "+ test_rv64i_to_glyph_bio = 29 passed / 1 deselected (live_smoke), exit 0. "
    "Honest boundary (unchanged): containment only — the low-byte-only PTE validity test "
    "stands, a byte run with low byte 0x07 still mis-decodes as a PTE; the ceiling bounds the "
    "damage at 64 MiB. NOT re-verified by the orchestrator: the full arc this tick (the landing "
    "commit's own 43/43 cluster receipt accepted; WGSL twin not on this path)."
)
json.dump(d, open(P, "w"), indent=2)
print("status updated:", d["status"][:120], "...")

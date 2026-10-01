# RULING — DEFECT-23 option 2: declare the pfn ceiling at the extend site

**Date:** 2026-09-14 · **Seat:** orchestrator ("you lead") · reversible by Jericho
**Ticket:** `.builder_queue/REPAIR_PENDING_defect23_paged_flat_memory.md` (OPEN for option 2 only)

## Decision

Option 2, with the ceiling set from this defect's own probe data:

    CEILING = 65536 pfn        (= 16,777,216 words = 64 MiB of 32-bit words)

Enforce at `tools/glyph_isa_v2.py:740-743` (the `memory.extend` site). If
`pfn > CEILING`, do NOT extend: fault through the **existing** fault path.

## Why 65536, from measurement

The probe recorded accidental PTE decodes (`.builder_queue/probe_defect23_pt_slot_writer.py`):
`implied_pfn` 67,593 and 526,602. At PAGE_WORDS=256 that is 17.3M words (69 MB) and
134.8M words (539 MB). The pre-option-1 runaway peaked at 2295 MB (~2.24M pfn).
So the ceiling sits ~2.6x below the smallest observed bad decode, and ~34x below the
runaway, while the 24-bit pfn field otherwise permits a ~4.3e9-word (~17 GB) extension.

## Fault vocabulary — reuse, do not invent

"Redefining fault vocabularies" is reserved, so this ruling does NOT create a new fault name.
Raise the engine's EXISTING fault/panic path and carry the evidence in the MESSAGE:

    pfn=<n> ceiling=65536 pte=<0x..> addr=<0x..> site=glyph_isa_v2:740

## What this does NOT license

- It is CONTAINMENT, not a root cause. The low-byte-only PTE validity test at
  `tools/glyph_isa_v2.py:710` is untouched, so a byte run whose low byte is 0x07 still
  mis-decodes as a PTE. The guard bounds the damage (<=64 MiB instead of unbounded); it does
  not stop the misread. DEFECT-23 stays OPEN on the root cause.
- Do not lower the ceiling to make a test pass, and do not widen it to silence a fault.

## Gate (both legs required)

1. RED leg: craft a PTE with pfn = 526602; without the guard memory grows by ~539 MB;
   with it, the fault fires and memory does not grow. The leg must show the byte delta.
2. GREEN leg: the existing page-table building suites still pass unchanged (no false positive:
   legitimate builds stay under the ceiling).

## SEAT CONFIRMATION (2026-09-14)

Confirmed by Jericho, explicitly, after review: the 65536 pfn ceiling and its margin
(2.6x below the smallest observed bad decode, 34x below the runaway peak) are adopted.
The orchestrator's prior ruling was provisional ("you lead" is not blanket authorization
for a reserved memory-ceiling decision); this note is the actual seat authorization the
standing matrix requires. The ceiling is NOT yet implemented in `tools/glyph_isa_v2.py` —
only this ruling document exists at commit `08b68da`. The gate above (RED + GREEN legs)
is now unblocked for the lane to build.

## ADDENDUM - implemented and gated (2026-09-14, post-confirmation)

Jericho seat-CONFIRMED the ceiling this day (commit f217992). Landed same day:

  engine   tools/glyph_isa_v2.py - ceiling check at the REAL extend site, the paged-ST
           fallback (only `memory.extend` in the engine, now :762-800). The ruling's
           original "enforce at :740-743" was a WRONG line cite (that region is
           fault-vector code); actual site confirmed by grep before implementation.
  fault    reuses the existing fault semantics verbatim: fault_addr/fault_pc written,
           FAULT_ADDR/FAULT_PC MMIO recorded, mode->SUPER, KFAULT_PC vector or halt.
           Evidence string on cpu.fault_reason:
             pfn=<n> ceiling=65536 pte=<0x..> addr=<0x..> site=glyph_isa_v2:764
           A faulting store is ABANDONED (do_store=False) - mirrors the PTE-fault
           path above; the first draft stored through the giant paddr (IndexError
           class) and was caught in review before any run.
  gate     tests/test_defect23_pfn_ceiling.py - L1 RED-first falsifier (pfn=526602:
           asserted memory<=16384 words FIRST, then faulted/halted/FAULT_ADDR) -
           measured RED on the unguarded tree at memory=134,810,458 words (the
           original defect reproduced by the gate itself), GREEN after the guard,
           0.14s. L2 legitimate growth (pfn=100) still lands; L3 in-RAM untouched.
  blast    43/43 across the paged-path cluster: pt_identity, glyph_isa_v2, kalloc,
           bio, proc, rv64i_to_glyph, gh18_syscall_abi, syscall_handlers,
           run_containment.

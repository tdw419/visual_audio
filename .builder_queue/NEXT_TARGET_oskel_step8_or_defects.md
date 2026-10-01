# NEXT TARGET — after OS-SKEL-R2 closed (2026-09-12, builder cron af3e62239ce2)

OS-SKEL-R2 is closed (receipt `systems/RECEIPT_OS_SKELETON.md`, last code commit `637f6e7`).
The ruling's primary lane supply is used up (`.builder_queue/RULING_next_lane_OSS_GL6_GL7.md`;
GL-6/GL-7 both loop-side done, handoffs in `.builder_queue/HANDOFF_gl*.md`), so the next run picks
the first of these that is still eligible. **Priority order:**

1. **DEFECT-18 — option (a), engine-side tick register snapshot** (`.builder_queue/RULING_20260912_defect18_a_defect17_d.md`).
   Mechanical hardening, ruled, no design judgment left. Gate `tests/test_defect18_tick_regfile.py`
   already exists — check whether the ruled leg is missing before re-implementing anything.
2. **DEFECT-17 — option (d), static-scan refusal gate** (same ruling). Gate
   `tests/test_defect17_x31_refusal.py` already exists — same check first.
3. **OS-SKEL step 8 — engine wiring** (`systems/GLYPH_OS_SKELETON.md` § 6 item 8): wire
   `AddressSpace.switch` to the real engine via `PAGE_TABLE_ADDR`, move space-lifetime ownership off
   `reap`. **Needs its own round brief and its own gate**, and it touches engine semantics — so it is
   the last of the three until a brief exists (the round was explicitly fenced out of steps 1–7).
4. Queued BK-* roadmap rows (BK-6, BK-9, BK-10, BK-12, BK-13, BK-14 …) only if none of 1–3 is eligible;
   skip anything marked BLOCKED-ON-DESIGN and leave a REPAIR_PENDING note instead.

Reserved to Jericho — do NOT pick up: GL-6/GL-7 publication, "declare the lane complete", new spine
items, residency/Tier C (`.builder_queue/RULING_lane_supply_20260912.md` § Reserved).

Open scope note carried forward from OS-SKEL-R2 step 7: `tools/geos_os_skel_verify.py` leg 6g (amended
at step 5) is still **flagged for lane review** — see § 4 of the round receipt.

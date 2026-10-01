# BRIEF — BM-503D: exec-from-data design pass (bare-metal ladder)

**Authority:** roadmap row BM-503D (systems/GLYPH_SELF_HOSTING_ROADMAP.md, census table). Queued under POLICY_decision_delegation_20260918.md (D-2, supply filing) — this is ordinary eligible supply, not a named hold-gate.

**Context:** Rung 5 completed 2026-09-18 (commit ea3cc949, GATE PASS x2) with TASK_BM503 skipped-with-reason: stage2 reads and CRC-verifies a second DATA image (img2 @ LBA 129), and writes (BM-502), but transferring control to a decoded second EXECUTABLE was left without a design. This brief commissions the design, not the implementation.

**Scope (files that may change):**
- `tools/bare_metal_poc/rung5/DESIGN_EXEC_FROM_DATA.md` (NEW)
- review companion (second file or a review section in the same file)
- roadmap BM-503D status cell
Nothing else. rung1-5 asm/trees are READ-ONLY inputs. TASK_BM001 (landing the bare_metal_poc tree) remains HOLD for Jericho verbatim ratification — do not git-add the tree as part of this row.

**The design must answer, explicitly:**
1. **Receipt protocol under isolation: NONE.** A crashing img2 is indistinguishable from a crashing stage2. Propose how the exec receipt proves img2 ran: e.g. img2's first duty is printing a distinctive banner over serial, then exiting with a magic byte/API the stage2 checks (the SE021 oracle pattern — test_glyph_app_glyph_on_glyph.py's CHILD_OK convention — is the in-repo precedent and SE021 was just unblocked: cross-reference RULING_SE021_release_by_measurement_20260918.md).
2. **Entry-state contract:** what registers/stack/segments/versioned state stage2 hands to img2, and what img2 may clobber. Keep it minimal and written down.
3. **Integrity gating:** reuse the build-time CRC32 gate pattern (rung5_consts.py / stage1_const.inc twin pattern) for the exec image; specify where the check lives (stage2, before jump) and the refusal format (RED-A style, computed-vs-expected).
4. **Blast radius:** state whether exec-from-data changes any rung 1-5 gate leg, and if yes which and how the gate scripts would grow a leg.
5. **Kill-or-continue verdict:** if the design concludes exec-from-data is not worth a rung (e.g. BIOS-mode exec proves nothing beyond SE021's host-exec RUN), say so with reasons — a reasoned NO is a valid deliverable and closes the row.

**Gate:** the roadmap row's gate cell is authoritative. Self-review pass mandatory (check the design against rung5_layout.inc's actual LBA map and stage2.asm's actual control flow — no prose-only hand-waving).

**Honest boundaries required in the design:** TCG-only, no ECC, no hardware claims, 16-bit real mode only, no Path-B compression.

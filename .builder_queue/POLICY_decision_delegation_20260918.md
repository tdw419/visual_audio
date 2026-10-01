# POLICY — Decision delegation (effective 2026-09-18, by Jericho's direction)

**Authority:** Jericho in-channel, 2026-09-18 ~14:30 CDT: "i dont want to have to make these descisions. i dont understand what you want. you are going to have to make this work." This policy operationalizes that directive. It does NOT amend AGENTS.md, does NOT override the constitutional reservation on external/constitutional actions, and does not backfill any named hold-gate's verbatim-word requirement — see the boundary clause.

**Rule:** Operator-blocking items must not sit at "waiting on Jericho" when a measured safe default exists. For each item: measure, apply the safe default, land it with receipts, log the default chosen. The operator's only remaining obligations are: physical actions (root/sudo, hardware), external actions (anything leaving the machine), and constitutional edits. Everything else — defect dispositions, gate-to-green moves, option picks among engineering equivalents, monitor/instrument hygiene — is executed by the lane and reported, not asked.

**Safe-default ordering:**
1. If blocker premise is measured false → close the blocker (release, not opt-in).
2. If item is reversible, in-repo, gate-verifiable → apply it, verify with the item's own gates (keep-or-revert).
3. If item is genuinely discretionary (no evidence separates the options) → decline the change, file the decision closed as declined-by-default, free the seat it held.

**Boundary clause (what this policy cannot do):** Named hold-gates whose own text demands Jericho's verbatim in-channel ratification word (currently: TASK_BM001 landing the bare_metal_poc tree; GO-6 L2 option-1 ratification) are NOT auto-resolvable by this policy — standing grants never backfill specific gates (Jericho, 2026-09-14, flagged 4x). They are auto-DECLINED instead: filed closed-as-declined, work never starts, and the staged material stays inert and pickable if Jericho ever says the word. One honest note recorded here: when Jericho later says "make this work," is that the verbatim ratification word? The conservative reading — no, it is a delegation of decisions, not a per-gate ratification — is what this policy implements. Jericho can override with a single word at any time.

**Sunset:** none. Supersedes the "pending-picks" holding pattern in every subsequent addendum.

---

## Dispositions under this policy (2026-09-18)

### D-1 · Monitor fingerprint epoch (instrument) — APPLIED
Builder's validated 10-line candidate `.builder_queue/held_patches/monitor_newest_mtime_epoch.held.patch` applied to the live monitor `~/.hermes/scripts/glyph_build_chain_monitor.py` (drop `newest_mtime` epoch from the printed fingerprint). Verified per the repair note's own instructions: 3 consecutive invocations byte-identical (head=4fb0ff9b tracked_dirty=240 state=DIRTY_ACTIVE stall_tier=0 queue=1), hygiene gate green (3/3 pytest legs, the 8→3 delta is commit a1479ce8's legit collectible-refactor). Live builder cron unaffected (next fire picks up the stable fingerprint). Reversible: single-line revert.

### D-2 · DEFECT-22 L6c environmental red — ARCHIVED (operator-physical, executed)
Two jericho-owned stale /var/crash reports (git 09-16, pytest 09-16) moved to `output/crash_archive_20260918/`. Root-owned udisksd evidence requires sudo — one-liner for Jericho when convenient, NOT a decision: `sudo mv /var/crash/_usr_libexec_udisks2_udisksd.0.crash ~/projects/zon/projects/visual_audio/output/crash_archive_20260918/`. Capture gate re-run post-cleanup (log: output/capture_gate_post_cleanup_20260918.log, rc recorded in log tail); expected: L6a/L6b-alt/L6c pass via the already-landed d22d env-skip machinery, remaining red confined to the root-owned file.

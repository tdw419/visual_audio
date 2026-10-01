# SYSTEM1_OPERATIONS.md — How System-1 Audits the Builder

**Status:** OPERATIONAL (since 2026-09-27) · **Owner:** visual_audio lane · **Model:** qwen2.5-coder:7b (Q4_K_M) via local Ollama, localhost:11434
**Cost:** $0 marginal · **Latency:** ~2.9s median per verdict · **Cadence:** every 2-min watchdog tick (Hermes cron 9022a527b259, no-agent)

---

## 1. The one-line thesis

> **It's the difference between a builder that self-reports and a builder that gets audited.
> The audit is what makes the receipts culture real at builder speed.**

The af3e builder produces code, tests, and receipts autonomously at ~30-minute cadence.
Historically, nothing checked those receipts until a human reviewer session ran — which is
rare, expensive (cloud tokens), and always after the fact. System-1 is a local, always-on,
schema-constrained classifier that screens every receipt as it appears and can force
remediation — turning "receipts culture" from an aspiration into an enforcement mechanism.

---

## 2. What it is (and deliberately is not)

| | |
|---|---|
| **IS** | A bounded, typed decision engine: evidence in → `{decision, confidence, probabilities, rationale, evidence_hash}` out |
| **IS** | A screener and (since Phase 3) a queue-injector with real enforcement teeth |
| **IS NOT** | A reasoning model. It cannot do BK-55-grade research or judge novel architecture |
| **IS NOT** | An oracle for truth. "Type-safe ≠ correct" — it classifies *shape*, and its verdicts are themselves audited |

The System-1/System-2 split (after TypeSafe's "Jev"): cheap local model handles the ~95% of
lane decisions that are bounded classification; expensive cloud/reviewer handles genuine
judgment. Volume at builder speed, judgment where it's earned.

---

## 3. Architecture (all in-repo, zero host dependencies beyond the Ollama daemon)

```
.builder_queue/RECEIPT_*.md, RESEARCH_*.md        (builder output)
        │
        ▼
tools/glyph_builder_watchdog.py (every 2 min, Hermes cron 9022a527b259)
   Step 6: scan_and_screen_unlogged()             tools/geos_system1.py
   Step 7: regenerate spatial build map
        │
        ├─ scope guards first (0.0 ms): empty input / non-receipt shape
        │    → insufficient-evidence, NEVER shown to the model
        │
        ├─ landing receipts  → Head 1:  honest | overclaim | missing-red-leg
        │                                | insufficient-evidence
        ├─ research receipts → Head 1b: probe-sound | missing-control
        │                                | nondeterministic | unauthorized-code-land
        │                                | insufficient-evidence
        │
        ├─ every verdict → .builder_queue/decision_log.jsonl
        │    (append-only, sha256:evidence_hash, model, latency, probabilities)
        │
        ├─ defect @ ≥0.85 conf → RULING_SYSTEM1_ADVISORY_<id>.md   (Phase 2, mailbox)
        └─ defect @ ≥0.90 conf → remedy-<ticket>-<hash8> injected into
                                  QUEUE_STATE.json, origin: system1_auto_injection
                                  (Phase 3, enforcement)
```

**Key structural properties:**

- **Scope guards (non-vacuity):** documents without landing-receipt shape (no gate/test
  markers) short-circuit *before* the model runs. Confidently-wrong on out-of-scope input
  was System-1's first real misfire — the guard is the fix, and it also saves GPU cycles
  (~25% of evaluations never touch the model).
- **Idempotency:** evidence-hash dedup means re-scans never re-judge or re-inject.
- **Provenance:** every verdict carries `sha256:<hash>` of the exact evidence text — the
  audit trail is cryptographic, not narrative.
- **Three-phase discipline:** Shadow (log only, 2026-09-27 morning) → Advisory (mailbox
  rulings) → Enforcement (queue injection). Promotion only after measured discrimination.

---

## 4. Measured record (first ~36 hours)

| Metric | Value |
|---|---|
| Total evaluations | 136 |
| Real model verdicts | 97 (33 short-circuited by scope guards) |
| Defect verdicts | 7 (5 genuine, 2 early false positives → drove the scope-guard fix) |
| Genuine catches | 5, all vacuous-verification class |
| GPU cost | ~19.7GB VRAM resident, $0 marginal |

**The catches that matter** (the builder's most dangerous failure mode — receipts that look
green but prove nothing):

| Receipt | Verdict | What was actually wrong |
|---|---|---|
| `item26_process_model` | missing-red-leg @ 0.95 | RED leg was a *test collection error* — gate ran zero tests |
| `L4_desktop` | overclaim @ 0.95 | RED leg was an ImportError — same void-proof class, different receipt |
| `DTF_floor` | overclaim @ 0.90 | No pre-fix failure evidence |

Two independent catches of the same failure class in different receipts is the evidence
that this is discrimination, not luck. **The lesson generalizes: an ImportError or
collection error as a "RED leg" is a void proof — the gate never discriminated anything.**

---

## 5. How to operate it

```bash
# Screen everything unlogged (what the watchdog runs)
python3 tools/geos_system1.py --scan-unlogged

# Backfill past logged defects >=0.90 conf into QUEUE_STATE.json
python3 tools/geos_system1.py --backfill-defects

# Classify one receipt
python3 tools/geos_system1.py --receipt .builder_queue/RECEIPT_item41_taskmgr.md

# Full gate (16 legs, incl. injection + backfill + idempotency + scope short-circuit)
pytest tests/test_geos_system1.py -q        # 16/16, ~19s

# Manual injection (normally autonomous — rehearse against a COPY of QUEUE_STATE)
python3 -c "from tools.geos_system1 import inject_remediation_ticket, ..."
```

**When to trust a verdict:** confidence ≥0.85 on receipt-shaped input is reliable for
routing; anything novel-shaped, or any verdict you intend to *act* on destructively,
deserves a System-2 second opinion (reviewer session). The advisory → your judgment,
enforcement → only above 0.90.

---

## 6. Known limits (all measured, all disclosed)

1. **Out-of-scope misfire class (fixed):** fed a postmortem, early System-1 said
   `overclaim @ 0.84` instead of refusing. Scope guards now refuse non-receipt shapes at
   0.0ms. *Lesson: check input shape before trusting judgment — applies to reviewers too.*
2. **Backfill gap (closed 2026-09-27 in `72154d37`):** resolved via `--backfill-defects`.
   Injected `remedy-item26_process_model-b727fcb1`, `remedy-L4_desktop-2079c461`, and
   `remedy-DTF_floor-33b1e687` into `QUEUE_STATE.json` with orders 0/-1/-2.
3. **Builder-actuation on auto-advisories (closed 2026-09-27 in `bf209a09`):** proven end-to-end.
   Builder claimed `remedy-item26_process_model-b727fcb1`, confirmed advisory, discovered
   unconfined 21-byte host-FS fallback escape (`handoff.txt`), fixed gate (`test_item26_process.py:204`)
   with mutation RED→GREEN (8 passed in 35.18s), re-audited via System-1 (`honest` @ 1.00 conf),
   and landed cleanly.
4. **Drift:** the classifier encodes current doctrine; a governance change (like the
   host-boundary ruling) changes what receipts should look like — heads need recalibration
   after doctrine shifts.
5. **Shared VRAM:** the resident model shares the 24GB card with WGSL compute lanes.
   Coexistence has been clean all week; if a probe ever OOMs, check `OLLAMA_KEEP_ALIVE`.

---

## 7. Where it fits in the lane's governance stack

```
you (Jericho)            — constitutional authority; explicit-yes domain (host, external)
  └─ reviewer sessions   — System-2: novel judgment, escalations, rulings (RULING_*.md)
      └─ System-1        — System-1: continuous bounded screening at builder speed
          └─ builder     — produces receipts; claims/remediates via QUEUE_STATE
              └─ falsifiers/gates — every verdict (human or machine) must be
                                    checkable by something that can fail
```

No auditor is above the audit: the builder is audited by System-1, System-1 was fixed by
reviewer catch + scope guards, the reviewer's own fix failed its gate twice before passing.
That reciprocity is the point. **No verdict without a falsifier, no claim without an audit
trail, no auditor above the audit.**

---

*Related: `tools/geos_system1.py` · `tests/test_geos_system1.py` (16 legs) ·
`tools/glyph_builder_watchdog.py` (Step 6/7) · `.builder_queue/decision_log.jsonl` ·
`tools/spatial_build_map.py` + `tools/build_map_viewer.html` (visualize the audit as
territory) · BK-58/BK-59 in `systems/GLYPH_BACKLOG.md` (desktop gate: containment before
compositor).*

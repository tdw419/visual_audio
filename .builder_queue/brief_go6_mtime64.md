# BRIEF — GO6-MTIME64: widen mtime/mtimecmp to 64-bit per draft ruling

**Spec pointer (read FIRST — it is the spec):**
`.builder_queue/RULING_go6l2_mtime64_DRAFT.md` — the executable spec lives
there (state layout, tick carry arithmetic, both write paths, the rewritten
gate clause T1-T5). Supporting evidence:
`kernel-builds/l2_test/QEMU_REFERENCE_VERDICT.md`,
`kernel-builds/l2_test/FINDINGS_go6_l2_stall.md`.

**PRECONDITION — this brief is INERT until the ruling is effective.** The
ruling file must be renamed to `RULING_go6l2_mtime64.md` with the DRAFT banner
removed (Jericho's ratification, not the builder's). If the file still says
DRAFT / NOT EFFECTIVE: do NOT start. Zero engine lines without an effective
ruling. Skip this brief and pick the next eligible unit.

**Interfaces are LOCKED.** The state struct widens only by additive append at
the END (indices 10/11 in the Python twin; end-of-struct in WGSL). Existing
indices 0-9 MUST NOT move (L1 receipt froze that surface). If the append
looks wrong for any baked artifact, STOP and re-file the blocker — do not
reorder fields to fit.

**Scope (files that may change):**
- `tools/SPATIAL_RV32I.wgsl` (mtime/mtimecmp model only)
- `tools/spatial_rv32i_cpu.py` (twin, identical arithmetic)
- `tests/test_go6_mtime64_parity.py` (new)
Nothing else. Must-not-touch: baked images unless T5 proves a re-bake is
required (and then only the re-bake outputs, never the state-word order);
transpiler; roadmap; other engine files (`glyph_dispatch/**`,
`tools/glyph_isa_v2.py`).

**Gate command (structural gate, must stay green after every step):**
`python3 -m pytest tests/test_go6_mtime64_parity.py tests/test_spatial_rv32i_cpu.py -q`
-> exit 0. Plus boot-smoke gate and the standing conjunction at the new HEAD.

| Step | Populate | New gate | Gate clause (concrete) |
|---|---|---|---|
| 1 | RED legs in `tests/test_go6_mtime64_parity.py` against the CURRENT engine | T1 wrap, T2 hi-word honesty, T3 no-early-fire | Each leg fails against current 32-bit engine with the literal failure recorded (T2: hi-address reads fall through to the generic accept-silently branch — no tracked hi half exists; T3: MTIP fires early at `(1,0)`). Paste literal RED tails. |
| 2 | Engine widening per ruling §The-change (WGSL + twin) | Same T1-T3 legs GREEN + T4 lockstep parity | T1: `(0xFFFF_FFFE,0)` + 2 ticks -> `(1,0)`; T2: hi decodes return the tracked counter (0 pre-wrap, 1 post-wrap), both mtimecmp hi write paths (MMIO `0x11004004`, SBI TIME a1) latch; T3: MTIP silent at `(1,0)`, fires at `(1,1)`; T4: WGSL and Python traces identical. |
| 3 | T5 re-bake check | T5 artifact enumeration | Every baked artifact embedding the state struct enumerated; additive-append invariant asserted (no existing word index moved); list of artifacts re-baked, with md5s. |
| 4 | Integration leg | T1-boot: recorded `Image_6.9_nommu_virtblk` + patched-DTB pair in the spatial engine | `timekeeping_advance` progresses past the 13M-step stall milestone (past the `cpu0: Ratio of byte access time…` UART line, matching QEMU's 0.45s behavior). May size as its own run if the boot exceeds one context window. |

**Failure evidence (RED first):** Step 1 exists precisely so the gate is shown
failing against the current engine before any engine line changes. A GREEN T1
that was never RED is invalid.

## Hard constraints
- Additive only. The 19 L1-era tests in `tests/test_spatial_rv32i_cpu.py`
  must pass UNMODIFIED — if one needs a change to stay green, STOP and
  re-file the blocker (that is a skeleton-sign-off signal, not a test fix).
- Keep live guards live. Never weaken a guard to make a step pass.
- Stdlib only. Do not edit constants to force agreement — report instead.
- One gate-able step = one run = one commit. Steps 1-4 are separately
  committable; do not batch.

## Receipt discipline
- RED tails pasted literally in the step-1 commit and report; GREEN tails in
  each subsequent commit.
- Standing conjunction re-measured at final HEAD (SEED recorded).
- The receipt must state what the PASS does NOT prove: other CLINT modeling
  gaps (MSIP, address decode) are not thereby exonerated; the proof
  obligation is the boot milestone, not a full CLINT equivalence claim.

## Definition of done
Steps 1-4 with RED->GREEN evidence, structural gate + boot smoke + standing
conjunction green at final HEAD, T5 re-bake list measured (not assumed), and
a receipt naming what is NOT claimed. GO-6 L2 row then closes per its own
gate clause (vd0 appears + dd round-trip on the spatial engine).

# RECEIPT — DTF-4 desktop-floor rung 4: BK-11 coreutils gate restored + measured GREEN at HEAD (builder cron af3e62239ce2)

**Date:** 2026-09-22 ~21:0x CDT · **Lane:** Glyph GPU OS product lane (PRODUCT_ROADMAP.md P2.5)
**Claimed:** DTF-4 — coreutils vol. 1 (BK-11 gate `tests/test_bk11_coreutils.py`)
**Head at claim:** 2090c163 (re-verified per parallel-session rule; no RULING_* newer
than the last landed commit; ledger STATUS ACTIVE; queue empty; DTF-3 landed this
afternoon names DTF-4 as next)

## What was actually wrong (this was a REPAIR tick, not a green-waving tick)

The BK-11 gate was RED at HEAD **worse than its committed 09-12 state**:

```
$ python3 -m pytest tests/test_bk11_coreutils.py -q          # at HEAD 2090c163, pre-fix
4 failed, 2 passed in 10.33s
FAILED ...[cat] FAILED ...[echo] FAILED ...[wc] FAILED ...[head]   # cmp 3/3 green
```

Symptom: cat/echo/wc/head all 0/3 fixtures, each faulting with an out-of-bounds
store at fault_addr ≈ 0xFFFFF80C (word 0x3FFFF603 > 16384) ~2800 steps in, stdout
window empty. cmp passed (it touches no small data on its fixtures).

### RCA chain (symptom → root, every step measured)

1. **Fault class**: engine's OOB-store fault (glyph_isa_v2.py:1046-1050, bounds
   checked against actual len(memory)). Register dump: r3 (gp) = 0 — the compiler's
   gp-relative small-data contract is unfulfilled.
2. **Contract**: `__global_pointer$` must seed x3 (DEFECT-9, GH-23;
   tests/test_gh23_libc_runtime.py:376-390 captures it BY NAME from parse_elf's
   symbol table before that loader's own junk filter; :530 emits `LDI r3 <gp>`).
   Sample check: cat fixture ELF has `__global_pointer$` = 0x1d81; out_ch's
   `sb s0,-2040(a5)` with gp=0 computes 0xFFFFF808-class addresses → the exact fault.
3. **Bisect** (predicate: `[cat]` leg exit code; range 564a05af..HEAD, transpiler
   path): first-bad = **6605f41a** (R2.3 hosted cross-compilation, landed 09-21
   15:19 — the LANDED-PENDING-REVIEW mailbox-race commit).
4. **Mechanism in 6605f41a**: parse_elf's junk filter changed from
   `st_shndx != 0` to `st_shndx not in (0, 0xFFF1)` — excluding **ALL ABS
   symbols** to kill the FILE-symbol-shadows-_start bug. But `__global_pointer$`
   is ABS, so it silently vanished from the table. The R2.3 gate
   (tests/test_glyph_cc.py) couldn't catch it: its freestanding programs are
   "no libc" by design and never touch gp-relative small data.
5. **Why nobody saw it for a day**: BK-11's gate was not in any standing
   regression set after 09-12 (it passed then — 5/6 — and the lane's standing
   suites don't include it). The repo's evidence-discipline lesson applies:
   a gate nobody re-runs is not a gate.

## The fix (tools/rv64i_to_glyph.py:181-236, additive, one hunk)

Exclude FILE symbols **by name/type** (st_shndx == ABS **and** st_type == FILE),
NOT by ABS-ness. FILE symbols carry st_value 0 and were the shadowing hazard;
`__global_pointer$` (ABS, NOTYPE) is restored to the table. Everything else in
the filter is unchanged (UND exclusion, typed-over-filler precedence, `$`-mapping
skip). The transpiler is a core file: this is a single-function, single-hunk
change to parse_elf's symbol loop — no algorithm touched, no WGSL engine change
(the WGSL twin consumes baked artifacts, not ELFs, so there is no shader-side
surface for this defect; nothing to twin-parity check beyond the suites below).

## Gate evidence (all run by this process, this tick, at the fix tree)

- **RED leg (pre-fix, HEAD 2090c163)**: `4 failed, 2 passed in 10.33s` (above).
- **Discrimination RED**: with the fix stashed (`git stash push`),
  `[cat]` leg → `1 failed in 1.92s`; unstashed → green. The gate discriminates
  exactly this change; it cannot pass vacuously.
- **GREEN (post-fix)**: `tests/test_bk11_coreutils.py` → `6 passed in 21.94s`
  (5 parametrized tools × fixtures + cmp exit-code pin). Includes **wc GREEN** —
  the amendment's no-waiver clause (DEFECT-18 ruled (a) at 11fe1acd, landed and
  receipted; the 09-12 "wc blocked" state is resolved by that landed fix, verified
  by this run, not assumed).
- **Blast radius (transpiler = core file, per AGENTS.md)**:
  - tests/test_glyph_cc.py (the R2.3 gate): 7 passed
  - tests/test_gh23_libc_runtime.py: 7 passed
  - 20 transpiler files (test_rv64i_to_glyph*.py + gh15 IR): 18 + 27 passed, 0 failed
  - tests/test_gh21_posix_shim.py + gh26 glass box + bk14 demo: 17 passed
  - **Arc regression** (amendment gate clause): `SEED=42 bash tools/arc_lega.sh`
    → `394 passed, 1 skipped, 9 deselected, 2 xfailed`, rc=0, crashes=0, 71.34s
    (log output/arc_lega_seed42_2090c163.txt)
- Worktree isolation judgment: single-hunk symbol-filter repair, full arc green on
  the working tree, no codec/protected-asset files touched — merged in place
  rather than a throwaway worktree, per AGENTS.md's own implementer-judgment clause.

## What this PASS does NOT prove

- No rate/cost claims → floors N/A (no rule-1 numbers cited).
- Single host/GPU; fixtures are ≤16 B (the documented 16-byte stdout-window tool
  contract, unchanged — this rung proves the toolchain story per tool, not
  arbitrary-size coreutils).
- The glyph_dispatch/src/glyph/rv64i_to_glyph.py copy is a frozen distribution
  snapshot (differs from HEAD already, incl. typing imports; the triple-sync gate
  covers wgsl_glyph_isa_v2.py only). Left untouched — flagged here, not silently.
- DTF-4's "delivery vehicle" demo (DTF-1 shell) and the floor-exit transcript
  (RECEIPT_DTF_floor.md + RECEIPT_DTF_agent_use.md) remain OPEN — next ticks.
- R2.3 itself stays LANDED-PENDING-REVIEW; this receipt only repairs its
  collateral damage, it does not rule on its review status.

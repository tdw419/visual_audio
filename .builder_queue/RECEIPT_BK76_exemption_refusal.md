# RECEIPT — BK-76 Option A No-Vector Refusal LANDED (oracle engine)

**Landed by:** builder af3e62239ce2 (cron glyph-teleoperation tick, 2026-09-29 ~08:3x CDT)
**Picked at:** HEAD 609deba8 — the in-flight unit (rule: finish the in-flight unit; the ledger's
named next-tick items are superseded by this un-landed engine change found dirty in-tree).
**Authority:** RULING_BK76_EXEMPTION_POSTURE.md (filed 07:13 with HEAD 609deba8, §0 SCOPE &
AUTHORITY): Option A No-Vector Refusal, amendment path honored — this lands the engine fix +
gate legs the ruling's amendment clause names ("the builder may land BK-76's engine fix under
this posture and the gate legs EX-L1..L7 as specified").

## The fix (tools/glyph_isa_v2.py, +58 lines, oracle only)

- `_bk76_ever_user` one-way latch (:630, :837-844): set in `step()` when a USER instruction
  executes on a tile-confined engine. Boot/config-phase vector writes (GH-25 fault image,
  GH-16/GH-6 kernels, loader seeding) all happen pre-first-USER and stay lawful.
- `_BK76_LOCKED_WORDS` = {KFAULT_PC, KSYS_PC, KTICK_PC} (word addresses >>2).
- `_bk76_exemption_refuse()` (:820-835): drop the store, fault_addr = word<<2,
  fault_pc packed (y, x/INSTR_WIDTH), fault_reason "mmio_exemption_refused", mode→SUPER
  (post-mortem), running=False, **no vector** (tick-19 restart-loop immunity).
- Consult site: ST arm (:1089-1103), fires only when `ever_user AND mode==SUPER AND
  _tile_confinement AND window(BOX_MMIO_BASE..+256) AND addr in LOCKED_WORDS` — the exact
  :968 exemption survivor posture, scoped per ruling §3 invariant 1.
- Triple-sync check: all THREE WGSL copies byte-identical to HEAD
  (md5 4be6ff26a4f913864c8d7e722090f5f8 ×3) — **twin untouched; BK-76 twin parity is
  separate sequenced-commit scope, not claimed.** Oracle md5 changed by design.

## Gate: tests/test_bk76_exemption_refusal.py — 8/8 GREEN

pytest 8 passed in 0.08s; standalone run exit 0 (all 8 legs print PASSED).
Legs: EX-L1 store refused (KSYS word unchanged, faulted, "mmio_exemption_refused",
not running, SUPER, handler never reached PRT — output has no 52); EX-L2 lawful no-tile
SUPER store lands (control); EX-L3 unpaged E-K1 rot-guard (faulted, refused, exit 1, SUPER);
EX-L4 paged rot-guard; EX-L5 non-vacuity; EX-L6 chain refused; EX-L7 persistence broken
(1 fire); EX-L8 KTICK-site measured leg (ruling §0's named extrapolation risk exercised,
not assumed).

## RED-first at landing time (measured this tick, fix git-stashed)

`git stash push -- tools/glyph_isa_v2.py` → pytest:
**5 failed, 3 passed** — EX-L1 FAILED (assert not True; captured stdout "OUTPUT: r5 = 52"
= the handler ran to PRT through the hijacked vector, the exact pre-fix landing shape),
EX-L5, EX-L6, EX-L7, EX-L8 FAILED. EX-L2/L3/L4 controls PASSED pre-fix (harness live).
`git stash pop` → byte-identical restore verified (cmp vs /tmp copy). RED tail pasted
literally in the commit body.

## Family on this tree (post-fix, single runs)

- BK-66 gate + BK-66 ruling invariants + BK-38 + BK-52 + BK-49 + BK-48 + BK-64 +
  BK-64red/BK-65 HILB: **43 passed** in 9.13s.
- ISA/syscall regression: test_glyph_isa_v2 + test_gh6_syscalls + test_gh18_syscall_abi +
  test_se024_jnz_jne + test_bk2_wgsl_syscall_parity + test_bk51 + test_bk62/63 +
  item-36 substantive legs: 61 passed, 2 failed.
- The 2 item-36 failures are `test_n1_engine_byte_unchanged` drift guards (and their
  transitive X9/R7/C7/C8 subprocess chains), which pin the engine to HEAD **by design** —
  they fail on ANY un-landed engine change. Bottom of chain verified: test_item29's
  substantive legs 9/9 green, only its N1 byte-guard fails (expected hash
  1e3ba5fc… vs worktree). These guards go green the moment this commit lands. They are
  NOT evidence of behavioral regression — all behavioral legs in the cascade pass.

## What this PASS does NOT prove

- The WGSL twin's exemption hole is OPEN (twin md5 unchanged; separate scope).
- xv6-nano real-handler window-store behavior stays open (ruling §0; Option B re-opens
  there if ever needed).
- Other :968 window words beyond the three locked vectors are NOT refused (scope is
  vector words only, per ruling invariant 2 — xv6-nano ISO_SYS_A0 8205 etc. stay lawful).
- EX-L8 exercises the KTICK site through the gate harness; per ruling §0 a live-kernel
  surprise there re-opens the ruling rather than fitting it.
- Numbers structural; rule-1 floors do not attach.

## Next tick (named, per protocol)

BK-50 door posture row, or the clause-4 MMIO-exemption twin parity leg, or BK-49's
oracle-side legs — unless a new CLAIM QUEUE item or binding RULING appears first.

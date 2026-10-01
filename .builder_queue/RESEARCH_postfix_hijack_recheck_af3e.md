# RESEARCH — Post-landing re-verification: 69a53298's read posture vs the
# measured hijack chains (BK-53/55 legs re-run at the fix HEAD)

- Tick type: Phase 1c research (af3e, 2026-09-27 ~14:0x CDT). Rule-5 grep
  BEFORE harness build: no existing RESEARCH_*/backlog row re-measures the
  BK-53/BK-55 chains at the post-fix HEAD; every row's numbers pre-date
  69a53298 (probe md5s were taken at 5d05c530/7ad6ddcf/4197658c).
- Run selection: HEAD e1e9887c (ledger entry for the BK-38/BK-56 landing),
  tracked tree clean at claim, mailbox clean (newest RULING
  RULING_BK38_READ_POSTURE.md mtime 1790533788 < HEAD commit time
  1790535670 — the ruling is CONSUMED by 69a53298, not binding new work),
  monitor CLAIM_PENDING queue=0 stall_tier=0. QUEUE_STATE: 22/22 landed,
  CLAIM QUEUE empty (items 19..41 all landed per ledger) → research
  eligible.
- What landed between the probes and this tick (69a53298 + 7161b883,
  worktree va_fence_worktree, verified at main HEAD e1e9887c):
  oracle `LD` gains (a) tile-confinement trap armed only by
  spawn(tile=...) (`glyph_isa_v2.py:917-945`, flag set at
  `glyph_process.py:166`) and (b) a USER MMIO-read gate — words
  [8192,8448) return 0 (`glyph_isa_v2.py:947-950`); twin `walk_ld`
  gains `if (!is_super) { return 0u; }` (`wgsl_glyph_isa_v2.py:364`);
  all three mirrors md5-synced (SYNC1/2/3-OK, diff-empty).

## Re-measurement 1 — oracle BK-53 probe re-run at HEAD

`.builder_queue/probe_ek1_vector_hijack_af3e.py` (untracked, landed
modules only), 3 runs byte-identical, run-1 stdout md5
5e107adaa9495bb7e1d4804d30444fc3 — IDENTICAL to the pre-fix receipt's
md5. Verdicts unchanged at post-fix HEAD:
- D1 pixel-overwrite escape: attacker PRT r6 executes post-trap in SUPER
  (canary '34' printed).
- D3 super capability: out-of-tile word 164 written by trapped-into code
  (out_word164 = 11399181 = 0x0ADF00D).
- D5 vector rewrite: trap executed attacker code at the rewritten PC
  (kfault_word 1966084 = (30<<16)|4; canary printed).
- D2/C1 controls still discriminating.
READING: expected — 69a53298 landed the READ posture + tile-LD gate, not
the vector-arm guard. D3's escape rides the trap arm's unguarded
KFAULT_PC vectoring (`glyph_isa_v2.py:1063-1068` region, kf read LIVE,
no kf!=0 guard on the E-K1 branch) and the fence-blind PARALLEL_ST
staging, both still open rows (BK-52/BK-53). The landing did NOT
quietly break the RED legs of open rows — their receipts stay valid.

## Re-measurement 2 — twin BK-55 probe re-run at HEAD

`.builder_queue/probe_ek1_vector_hijack_wgsl_af3e.py`, 3 runs
byte-identical, results md5 128582726113782d8c234a4a59d7b068 —
IDENTICAL to the pre-fix receipt. D1 hijack, D2 super capability, D3
door-only vector arm all still escape; C1/C2 discriminating.
READING: also expected — the WRITE door (`walk_st` MMIO branch,
`wgsl_glyph_isa_v2.py:443-446`) executes before the E-K1 consult with
no mode gate; BK-50's posture was NOT part of this landing. The arm at
`:595-602` still vectors LIVE. But the LANDING'S OWN CLAIM needed a
check (below) because D3 is also the aim-step leg the receipt says is
de-fanged.

## Re-measurement 3 — the receipt's de-fang claim, tested directly

RECEIPT_bk38_ld_fence_option2.md says F1 "de-fangs BK-55's aim step"
and cites "on-device ram_result_word: 0 for both D1 and D2". Two legs:

(a) TWIN, measured (dbg harness = the BK-50/55 device shape; USER LD of
word 8193 → in-box result ST to word 310, plus USER LD of RAM canary
word 200 → 311): ram[310] == 0 (the MMIO read returns 0 — BK-56 posture
LIVE on-device at HEAD), while ram[311] == 0x0BADF00D (the NON-MMIO
walk_ld RAM path is untouched by the gate). 9 steps, mode USER, clean
halt. The aim VALUE is no longer guest-readable on the twin.

(b) ORACLE, measured (dbg: GlyphCPUv2, USER LD of 8193/8196 seeded
0x1234/0x5678, results stored to 310/311): r3 == 0, r4 == 0, mem[310]
== 0, mem[311] == 0, faulted False — the oracle read gate is LIVE too.
Cross-check against the landed gate itself:
tests/test_bk38_ld_fence.py F1 asserts registers == 0 for both words
(6/6 GREEN re-run this tick in 0.06s; xv6-nano 13/13 in ~31s).
Non-vacuity: mutation-testing the F1 assertion in a THROWAWAY copy
under /tmp (no repo mutation) — flipping the expectation to
`!= 0`/`== 0x1234` makes F1 RED in both variants (the seeded values
would leak through if the gate were neutered → the assert BINDS).

## Verdict (measured, both engines)

The BK-56 read-posture claim is CONFIRMED ON-DEVICE at the fix HEAD on
the twin and by direct oracle run: the config block (KFAULT_PC word
8193 included) reads 0 to USER on BOTH engines post-landing. BUT the
de-fang is narrower than the receipt's phrasing: it removes the
ATTACKER'S AIM-VALUE READ, not the attack. The full BK-55 chain still
escapes end-to-end at HEAD (re-measurement 2, results-md5 identical to
pre-fix) because BOTH of its load-bearing legs were out of this
landing's scope: the write door (BK-50 open — the guest doesn't need
to READ kf to arm it; the probe's D3 writes an arbitrary packed PC
blind) and the live vectoring arm (BK-52 open). BK-55's gate clauses
L1-L3 therefore remain RED-today-at-HEAD, and BK-56's "L1 RED today:
ram[310]==7" line is now stale — L1/L2 of BK-56's gate are GREEN at
HEAD for the plain seeding posture (the gate must be re-based on a
seeded-config-BY-KERNEL fixture or a door-write fixture to stay
discriminating, else it passes vacuously).

Rule-1 floors: all quantities structural (word values, md5s, step
counts, byte-identity of probe stdout) — no rate/latency/cost claim,
floors do not attach.

## Consequence for the sequenced fence commit

1. BK-55's receipt should be amended with one line: aim-step de-fang
   CONFIRMED (both engines read 0), chain still live via door+arm —
   L1/L3 stay the binding RED legs; the D3 "read your own kf to aim"
   variant is dead, the blind-write variant is not.
2. BK-56's gate needs re-basing BEFORE it can land non-vacuously: as
   written, its RED-first clause is now GREEN at HEAD (consumed by
   69a53298). Suggested re-base: seed the config words through the
   KERNEL/super path (or the door) and assert USER LD still returns 0
   — that shape is RED pre-fix and GREEN post-fix.
3. The open-row set for the sequenced commit is unchanged: BK-41
   (kernel-write-only posture), BK-50 (door posture), BK-51 (tile
   predicate parity), BK-52 (vector-guard parity), BK-53/55 (the
   chains themselves). Nothing in this tick landed engine or shader
   code; probes re-run + throwaway /tmp mutation legs + this receipt
   only.

## Honesty block — what this tick did NOT verify

- The WGSL-side BK-53 mechanism (a) PARALLEL_ST class: structurally
  unreachable on the twin (_OPCODE_ORDER omits PARALLEL — carried from
  BK-55's receipt, not re-derived this tick).
- BK-51's tile-predicate parity on the twin post-landing: the twin
  gained the LD-side MMIO gate but NOT a tile term in addr_in_box; not
  re-probed here (BK-51's own probe would need a tile-armed twin run —
  its receipt's numbers are from 3e5ff03f and remain the operative
  measurement).
- Whether any LANDED kernel fixture relied on USER MMIO reads that now
  return 0: xv6-nano 13/13 + 38/38 differential were run by the
  landing session; I re-ran only the two named gates (6/6, 13/13),
  not the full suite.
- The sibling site :1075-1082 (in-box overflow vectoring) was not
  probed this tick; BK-52's receipt covers it.
- The oracle's D3 probe leg writes KFAULT_PC via PARALLEL_ST; the
  parity of that staging path with the door ST on the oracle was not
  re-measured (the oracle probe output was byte-identical to pre-fix,
  which is the only claim made).

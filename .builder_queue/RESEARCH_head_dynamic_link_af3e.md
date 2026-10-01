# RESEARCH — BK-46 finding (4) root-caused: head's dynamic path fails at LINK (missing `_COMMON`), not at the ring — the "empty ring" record is falsified (BK-47 proposal)

**Tick:** 2026-09-27 ~04:4x CDT, builder cron af3e62239ce2.
**Trigger:** PHASE 1c — ledger STATUS ACTIVE (ad4f2494, my BK-46 research
tick, 03:05); QUEUE_STATE.json active=null, all items 19..41 landed,
DEFECT-30 resolved; mailbox clean (newest RULING 2026-09-22 20:38 CDT,
predates HEAD); monitor CLAIM_PENDING queue=0 stall_tier=0. One research
item this tick. NOT a re-research (rule 5): the explicitly open scope is
the BK-46 receipt's finding (4) — "head in the dynamic path emits NOTHING
(empty ring) — separate defect, recorded not root-caused" — no existing
RESEARCH_*.md or backlog row measures the head dynamic-path mechanism.

## Question

Does head's dynamic shell-native path (`glyph_l1_shell.py:972-974` seed
block) fail the same way wc's does (missing `_COMMON` → compile/link
failure), and if so why did the BK-46 tick record an EMPTY RING instead
of an error string?

## Method (what was measured, with path:line)

- Probe `.builder_queue/probe_head_dynamic_af3e.py` (untracked, landed
  modules only) at HEAD ad4f2494. Three legs; verdicts from returned
  strings + compiler/linker stderr + ring bytes, never handler stdout:
  - **A** — the REAL dynamic path: `GlyphL1Shell._shell_native("head", …)`
    on two session fixtures (25 B 4-line; 480 B 60-line).
  - **B** — the exact dynamic head TU, built byte-for-byte the way
    `glyph_l1_shell.py:952-974` builds it (seed `head_data`, derived
    `HEAD_N`, alias `HEAD_DATA`, NO `_COMMON`), with gcc/ld stderr
    surfaced (the shell's own handler at `:1023`/`:1034` discards it).
  - **C** — control: identical TU WITH `_COMMON` prepended → compile →
    transpile → bake → `GlyphRunner.run` → BK-24 ring collect.
- Static reading: `_COMMON` (`tools/glyph_gpt/coreutils_port.py:72-88`)
  defines `bk11_out_ch`/`bk11_flush`; the head body (`:187-210`) emits
  exclusively through them; the shell's dynamic seed block (`:972-974`)
  emits only the seed/derived/alias lines, never `_COMMON`.

## Findings (measured, md5 of full results blob 43bf2f0366674987708daa3980aa326d)

1. **Leg A (both fixtures): `ERR:SHELLNATIVE:head`** — an opaque error
   string, NOT an empty ring. The dynamic head path never reaches the
   engine; it dies before bake.
2. **Leg B (mechanism): LINK failure** — `ld.rc=1`, `undefined reference
   to 'bk11_out_ch'` (tool.c:(.text+0x38) in `_start`). Same root cause
   as BK-46's wc finding: the dynamic seed block omits the `_COMMON`
   preamble. The shell masks it: `glyph_l1_shell.py:1033-1034` returns
   `f"ERR:SHELLNATIVE:{verb}"` on any nonzero gcc/ld rc with the stderr
   discarded — indistinguishable from a missing toolchain.
3. **Leg C (control): head works completely once `_COMMON` is supplied**
   — cc0/cc1/ld all rc=0, on-glyph run `halted=True faulted=False`, ring
   cursor 772 (ring_base 768 → 16 bytes delivered), output `alpha` =
   correct `head -n 1` on the 4-line fixture. There is NO separate head
   body defect.
4. **The landed record is wrong on the symptom:** BK-46's finding (4)
   and the ledger entry ("head emits NOTHING, empty ring — separate
   defect") describe a state the real path cannot produce — a link
   failure returns the ERR string at `:1034` and never touches the
   ring. The earlier tick most likely read the ERR-string turn's empty
   *output* as an "empty ring". head is not a second defect; it is the
   SAME defect as wc's, with a different observed symptom.

## Candidate (backlog format, NOT claimable lane-side per backlog header rules)

**BK-47 — Fix the dynamic seed block for the remaining shell-native
verbs (prepend `_COMMON` + per-verb seeds in `_shell_native`), covering
wc AND head in one change; surface gcc/ld stderr in the ERR path.**
BK-46's gate (L1 seed-block fix, L2 3-digit RED leg, L3 parity) already
specs the wc side; this extends the same L1 fix to head and adds the
diagnostic leg. Gate `tests/test_bk47_head_dynamic_path.py`:
L1 — `_shell_native("head","-n 1 f")` returns the first line, not ERR
(RED today: `ERR:SHELLNATIVE:head`); L2 — `-n 3` returns exactly three
lines; L3 — n-exceeds leg (n > line count returns whole file, the
fixture-table contract at coreutils_port.py:314-318); L4 — diagnostic:
compile-fail ERR strings carry a stderr excerpt (RED today: bare
`ERR:SHELLNATIVE:<verb>`); L5 — non-vacuity: revert the `_COMMON`
prepend → L1 fires loud; L6 — family: BK-46 gate + test_l1_shell_
personality + BK-11 fixtures byte-exact. Prereq: BK-24, BK-11 (landed);
coordinate with BK-46 (same file, same fix shape — land together or in
one sequenced commit; BK-47 does not alter BK-46's wc legs). Blast
radius: experiments/glyph_l1_shell.py only — no engine file.

## Honesty (rule 6)

Every number above is from one probe run this tick (string returns,
gcc/ld exit codes and stderr text, ring cursor arithmetic, results md5
43bf2f0366674987708daa3980aa326d). No floors_authoritative rate claim is
made (no engine-rate numbers; freshness window not consulted). NOT
verified: tr/grep dynamic-path audit for the same missing-preamble class
(grep/tr DID run in the dogfood suite, so their seed blocks must supply
what their bodies need — but their `_COMMON` usage was not re-derived
here); whether `ERR:SHELLNATIVE` masking hides other latent link
failures; WGSL twin (nothing spatial). The "empty ring" falsification
rests on leg A returning an ERR string — the exact opposite symptom —
reproduced on two fixtures in one process; the earlier tick's
mis-recording mechanism (ERR output misread as empty ring) is inference,
labeled as such.

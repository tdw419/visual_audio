# RESEARCH: the L1 shell's wc/head swap refusal — enforced by a COMPILE FAILURE, not the documented 16-byte-window limit (which BK-24 made stale)

**Tick:** Phase 1c research, builder cron af3e62239ce2, 2026-09-27 ~04:0x CDT
**Base:** HEAD e18658d6 (my BK-45 research tick), tracked tree clean at claim
**Probes:** `.builder_queue/probe_wc_swap_af3e.py` + `.builder_queue/dbg_wc_swap2_af3e.py` + `.builder_queue/dbg_wc_swap3_af3e.py` (all untracked, landed modules only)
**Backlog row filed:** BK-46 in `systems/GLYPH_BACKLOG.md`

## The question (friction signal, not invented scope)

R53_USE_LOG.md day 1 (Jericho, in-channel): *"the shell only repeats you … No
user surface exists yet."* The L1 shell's verb surface is the operator's real
entry point, so this tick audited which verbs actually execute where.
Selection command: `grep -n 'if verb ==' experiments/glyph_l1_shell.py` →
21 verb branches; of these, exactly 2 route through the native glyph-binary
swap (`grep`, `tr` — `:515-523`). Three verbs are pinned to host shims by an
explicit comment (`:505-513`):

> *"wc: NOT swapped — the landed wc binary delivers via the **16-byte window**
> and wc's report exceeds it on real files (swap would truncate). Host shim
> stays."* (same wording for head/tail)

That comment cites the PRE-BK-24 output channel. BK-24 (item 18, landed
2026-09-24) replaced the 16-byte single-flush window with a 256-byte
streaming ring (`libc_runtime.py:41-64`), and `_shell_native_collect`
(`glyph_l1_shell.py:1054-1075`) already reads the ring, not the window. So
the pinned refusal's stated mechanism looked falsifiable. Measured.

## Method

Three probes, deterministic, all verdicts from returned STRINGS / compiler
stderr / ring bytes — never handler stdout, never exit codes alone:

1. `probe_wc_swap_af3e.py` — drive `GlyphL1Shell._shell_native("wc", …)`
   exactly as the swap would (session file, cache on and off).
2. `dbg_wc_swap2_af3e.py` — replicate `_shell_native`'s compile chain
   verbatim with stderr surfaced, to locate which loud-refusal site fires.
3. `dbg_wc_swap3_af3e.py` — the falsification leg: supply the missing
   pieces host-side, compile → transpile → bake → run on GlyphRunner →
   collect from the BK-24 ring, byte-compare against the host shim.

## Findings (measured)

**(1) The swap NEVER RUNS today — it dies at gcc, before the engine.**
`_shell_native("wc", "small.txt")` → `ERR:SHELLNATIVE:wc` on every fixture
(results md5 `0b365dce36781f09cbc2d70bed3a85f3`, byte-identical with bake
cache on and off). dbg leg 2 shows why: the dynamic seed block
(`glyph_l1_shell.py:968-971`) seeds only `wc_data`/`WC_LEN`/`WC_NAME`-alias,
but the V1 tool bodies are compiled against the `_COMMON` emit preamble
(`coreutils_port.py:72-93`: `_buf`, `_n`, `bk11_out_ch/out_str/flush`) which
the BK-11 fixture builder prepends (`:389`) and `_shell_native` does NOT.
gcc: `error: '_n' undeclared` → the compile-leg refusal at
`glyph_l1_shell.py:1020-1021` fires. **The comment's justification
("delivers via the 16-byte window") is unreachable code's clothing: the
refusal is real but its documented mechanism is not what enforces it.**

**(2) The 16-byte-window claim IS stale: the BK-24 ring delivers a
30-byte wc report correctly.** With `_COMMON` + a `wc_name` seed supplied,
the native wc ran on-glyph and the ring collected
`' 2  5 29 small.txt              '` (30 bytes > 16) — multi-flush
streaming worked, the legacy window contract did not truncate it.

**(3) BUT the swap would still corrupt real-file output — for a different,
undocumented reason: the V1 wc body's counter formatting is 2-digit.**
Same GREEN leg on a 309-byte file: counters render `40 80 O0` — the third
counter (310 chars) goes through `'0' + (char)(v / 10)` in a 2-byte buffer
(`coreutils_port.py:158-160`), producing `'O'` (48+31=79) instead of `"310"`.
The fixtures (`:259-281`) never exceed 2 digits, so the landed BK-11 gate
cannot see this. Host shim reference: `40 80 310 multi.txt`. **The refusal's
CONCLUSION (host shim stays for wc) survives on real files — but the
documented reason (window) is falsified twice over, and the actual blockers
were unknown until now.**

**(4) head in the dynamic path emits NOTHING** (ring cursor == ring base,
empty string returned) — the head V1 body has a second, un-measured-to-root
defect in this harness shape (its pad/flush contract differs from wc's; not
root-caused this tick — recorded, not guessed).

## Verdict

The pinned wc/head swap refusal is **enforced by a latent compile failure**
(missing `_COMMON` + name-seed in the dynamic seed block), not by the
documented 16-byte window — which BK-24 retired, and which the plumbing
(`_shell_native_collect`) already no longer uses. A naive "delete the stale
comment and flip the branch" swap — the fix the comment's staleness invites —
would land a binary that prints `O0` for `310` on real files and empty output
for head. The host shims stay until BK-46's gate exists.

## Numbers discipline

All quantities structural (compiler stderr text, returned strings, ring byte
counts, a results md5, line numbers). No rate/latency/cost claim → rule-1
floors do not attach. No citation of superseded floors or banned ratios.

## NOT verified

- The exact defect in head's body (leg 4: empty output) — recorded, not
  root-caused; its gate must first show the failure shape.
- tail (no V1 `tail` source exists in `coreutils_port.py`; measured by
  `grep -n '"tail"'` → absent) — the comment pins tail to a host shim for a
  tool that has no native binary at all; noted as a comment-accuracy item
  inside BK-46, not separately gated.
- WGSL twin (shell personality is Python-host-side; unchanged).
- Whether VOL2 tools (grep/tr, which DO have `_VOL2_COMMON` prepended —
  `glyph_l1_shell.py` seeds match) hit any analogous formatting ceiling;
  out of scope this tick.

## Backlog candidate (filed as BK-46, systems/GLYPH_BACKLOG.md)

Gate: `tests/test_bk46_native_wc_swap.py` — L1: dynamic-path compile must
include the `_COMMON` preamble + per-tool name seeds (probe: `_shell_native`
returns the report, not ERR:SHELLNATIVE — RED today); L2: RED leg — a
3-digit counter renders correctly (`310`, not `O0`) BEFORE the swap flips,
i.e. the wc body fix is proven against a real-file-sized fixture;
L3: parity — native output == host `_wc` output byte-exact on a >256-byte
file; L4: head/tail posture decided explicitly (fix body or keep host shim
with an ACCURATE comment — the current comment's mechanism must not
survive); L5: non-vacuity — revert the seed-block fix → L1 fails loud;
L6: family — test_l1_shell_personality + test_bk11_coreutils green (the
16-byte window guard stays live for BK-11-era consumers);
L7: `_SHELL_NATIVE=False` hook still proves the branch is live.
Prereq: BK-24 (landed), BK-11 (landed). Blast radius: experiments/ +
coreutils_port tool body only — no engine file, no worktree isolation
required, but the wc body change must keep every landed BK-11 fixture
byte-exact (they pin the 2-digit shape).

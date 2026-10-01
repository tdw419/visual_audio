# RESEARCH (RECONCILIATION): head "emits NOTHING" — re-research overlap
# acknowledged; the root cause was already landed at 9e8b1bc0 (BK-47). This
# receipt's net-new content: the measured mechanism of the ORIGINAL
# mis-record (NUL pad frame, not "cursor == base"), and a NEW measured
# defect — the BK-24 ring cursor is unbounded (filed as BK-54).

**Tick:** af3e62239ce2, 2026-09-27 ~05:4x CDT, Phase 1c research (queue empty:
QUEUE_STATE.json all items 19..41 landed, DEFECT-30 resolved, mailbox clean —
0 RULING_* newer than HEAD d5afe55e, mtime-scanned; monitor CLAIM_PENDING
queue=0 stall_tier=0).

## Rule-5 disclosure (self-flagged)

This tick targeted the BK-46 receipt's open leg (4): "head emits NOTHING —
recorded not root-caused". **That question was answered by the immediately
preceding tick (commit 9e8b1bc0, ~04:4x, HEAD's direct ancestor):** head's
dynamic path dies at LINK (`undefined reference to 'bk11_out_ch'` — the same
missing-`_COMMON` class as wc), the shell's ERR path discards gcc/ld stderr
(`glyph_l1_shell.py:1033-1034`), so the failure surfaces as
`ERR:SHELLNATIVE:head` — and the landed "empty ring" symptom record was
falsified as unreachable on the real path. That root cause (BK-47) is the
authority; this tick does NOT supersede or re-land it. I started the probe
before grepping the backlog tail for a head-specific row — the rule-5 check
must run BEFORE the harness build, and this receipt is the record of that
ordering mistake. My probe runs at HEAD d5afe55e reproduce the ORIGINAL
dbg3-shape symptom (empty return) because that shape differs from the real
dynamic TU — see finding 1; the two receipts are consistent once the harness
shapes are distinguished.

## What this tick measured anyway (all at HEAD d5afe55e; probe
`.builder_queue/dbg_head_root_cause_af3e.py` — dbg_wc_swap3's harness with
RAW cursor + ring dump BEFORE any rstrip; results blob md5
645e32d319f2e9014d2e06fd5cfa178b)

1. **Mechanism of the original mis-record, measured (refines 9e8b1bc0's
   labeled inference "ERR output misread as empty ring"):** the
   dbg_wc_swap3_af3e.py head leg — which produced the "emits NOTHING"
   observation — seeded `static long HEAD_N = 1;` BEFORE the alias
   `#define HEAD_N head_n` (copied from the fixture builder's alias_map,
   coreutils_port.py:381, WITHOUT its matching seed at :350). The seed
   stayed `HEAD_N` (never referenced); the body's `HEAD_N` expanded to
   unseeded BSS `head_n` = 0 → zero lines → `bk11_flush()`'s pad delivers
   a 16-NUL frame. Measured leg A: halts clean, cursor = 772 (base+4, ONE
   frame), ring words (0,0,0,0); `_shell_native_collect`'s
   `.rstrip(b"\x00")` (glyph_l1_shell.py:1072) renders it `""`. So the
   pre-9e8b1bc0 probe saw a real empty-string return from a REAL ring
   write of NULs — a third failure shape, distinct from both the landed
   ERR-string path (leg A of BK-47) and a working head. CORRECTION to the
   BK-46 receipt's prose: it says "ring cursor == ring base" — measured
   cursor = 772, not base.
2. **head WORKS in the fixture-builder seed shape AND in `_shell_native`'s
   own seed shape** (legs B/C): real bytes, cursor = 872 = 26 frames =
   416 bytes for the 401-byte line, byte-exact `word word word w...`;
   leg C is `_shell_native`'s existing head seed block
   (`derived HEAD_N` + `#define HEAD_DATA head_data`,
   glyph_l1_shell.py:972-974) with only `_COMMON` missing — confirming
   BK-47's conclusion by a second route: **no head body defect; the
   dynamic head swap needs only the `_COMMON` prepend BK-47 already
   specs.** Leg D (short file `hi\n`): one frame decodes `hi\n` + NUL
   pad, word 682344 = 0x000A6968 byte-exact vs host.
3. **NEW DEFECT — BK-24 ring cursor UNBOUNDED (filed as BK-54):** leg B/C
   cursor = 872 = ring_base 768 + 104 words — 40 words past the declared
   ring end 832 (libc_runtime.py:54-57; saturation documented as a
   non-goal at :111-116; the write tile's cursor arithmetic :144-161 has
   no clamp). 416 bytes landed byte-exact with no visible corruption in
   this image, but words 832..872's occupancy is unmapped and a >256-byte
   stream is exactly the case the ring docs claim saturates. Single
   observation, blast radius NOT mapped; BK-54 carries the gate spec
   (clamp-or-reserve, canary RED-first legs).

## Numbers discipline

All quantities structural (word addresses, cursor values, byte counts, hex
words, two md5s, line numbers). No rate/latency/cost claim → rule-1 floors
do not attach. No superseded-floor or banned-ratio citations.

## NOT verified

- Anything BK-47 already measured (real `_shell_native("head",...)` ERR
  path, linker stderr, control leg) — not re-run; BK-47 stands.
- BK-46's wc legs — unchanged, not re-measured.
- Blast radius of the unbounded cursor (what lives at words 832.. in the
  libc-mode image; whether longer streams corrupt program data) — BK-54's
  gate, not this receipt.
- WGSL twin — shell personality is host-side Python; unchanged.
- Probe defect (disclosed): leg D's display field `host_head` computed
  `data_small[:1]` → `"h\n"` instead of `"hi\n"`; display-only — the raw
  ring word is the verdict.

## Backlog delta

- BK-54 filed (systems/GLYPH_BACKLOG.md): ring-saturation clamp-or-reserve,
  gate `tests/test_bk54_ring_saturation.py`.
- BK-46/BK-47 rows unchanged — this receipt adds no claim against them.

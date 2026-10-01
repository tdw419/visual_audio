#!/usr/bin/env python3
"""Append BK-46/BK-47 RESOLUTION tails to systems/GLYPH_BACKLOG.md (af3e)."""
from pathlib import Path

p = Path("/home/jericho/projects/zion/projects/visual_audio/systems/GLYPH_BACKLOG.md")
text = p.read_text()

old46 = "BK-46 | **L1 native-swap blocker:"
new46 = ("BK-46 | **[RESOLVED 2026-10-01, builder af3e62239ce2: wc swap landed "
         "+ body V2 — resolution tail at this row's end; head's half of the "
         "same defect class = BK-47, landed in the same sequenced commit]** "
         "L1 native-swap blocker:")
assert old46 in text
text = text.replace(old46, new46, 1)

old47 = "BK-47 | **Shell-native dynamic seed block:"
new47 = ("BK-47 | **[RESOLVED 2026-10-01, builder af3e62239ce2: head swap "
         "landed in the BK-46/47 sequenced commit — resolution tail at this "
         "row's end]** Shell-native dynamic seed block:")
assert old47 in text
text = text.replace(old47, new47, 1)

tail = """

---

## BK-46 RESOLUTION (2026-10-01, builder af3e62239ce2, sequenced BK-46/47 commit)
The L1 shell's wc branch is SWAPPED to `_shell_native` (the "16-byte window
truncates" refusal is retired as falsified — the refusal comment now states
the falsification; the BK-24 streaming ring carries any report size, past its
64-word extent the swap refuses LOUDLY). Fix set: (1) `coreutils_port.py` wc
body V2 — `bk11_out_dec` arbitrary-width emitter replaces the 2-digit
`char buf[3]` renderer (the measured '310'→'O0' class), single-space
`%d %d %d %s` format; fixture table gains `three_digit` (data_len_override)
and wc pins move to the new shape. (2) `glyph_l1_shell.py` `_shell_native`
prepends `_COMMON` to the dynamic TU for V1 bodies (VOL2 grep/tr excluded)
+ adds the `wc_name` seed — the omitted preamble was the real swap blocker
(every swap died at gcc '_n' undeclared before the engine ever ran).
GATE tests/test_bk46_native_wc_swap.py 8/8 ×2: L1 swap-returns-report, L2
3-digit render ('40 40 600 big.txt'), L3 parity >256B, L3b POSIX
no-trailing-newline parity (NEW DEFECT found by the family: the HOST SHIM
counted lines via splitlines() — phantom line on 'aa\\nbb\\ncc' where native
+ real wc count 2; `_wc` fixed to `text.count("\\n")`, w5 pin migrated 3→2,
RED measured `('2 3 8 noeol.txt', '3 3 8 noeol.txt')` pre-fix), L4 head/tail
posture pinned (tail host-side, no native source), L5 non-vacuity (no-_COMMON
TU dies at ld), L7 `_SHELL_NATIVE=False` shim arm, L4b head edges.
RED-first: probe_bk46_red_af3e.py measured at HEAD 9fa94508 (P1/P1b ERR
strings cache on AND off, P3 gcc stderr, P4 '40 40 l0'); BK-11 gate's own
addendum RED (3 original wc legs failed on the updated pins pre-body-fix).
Receipt-hygiene caveat stated in the receipt: the gate's L1/L2/L3 pass
vacuously on an unfixed tree (host-shim arm routes around the dead native
branch) — the probe + BK-11 RED pins carry the defect evidence.
Family: BK-46+47+BK-11+l1_shell_personality 35/35; BK-50/BK-45/monitor
suites 26/26; engine mirrors byte-identical 8dd8ce80 (no engine change).
NOT proved: pipe/stdin forms (host shim by design), WGSL twin (host surface),
tail native path (none exists). Full receipt:
.builder_queue/RECEIPT_BK46_BK47_shell_native_seed.md
Numbers structural, rule-1 floors do not attach.

## BK-47 RESOLUTION (2026-10-01, builder af3e62239ce2, sequenced BK-46/47 commit)
head's dynamic path fixed by the SAME preamble injector as BK-46 (the
'undefined reference to bk11_out_ch' LINK death — probe_head_dynamic_af3e.py
leg B, results md5 43bf2f0366674987708daa3980aa326d) and the branch is
SWAPPED to `_shell_native`. The landed "head emits NOTHING (empty ring)"
record stays FALSIFIED: the real pre-fix path returned the ERR string.
NEW (the row's extension leg): `_gcc_err` diagnostic — compile AND link
failures now return `ERR:SHELLNATIVE:<verb>:<first stderr 'error:' line>`
(both arms wired; the opaque bare ERR that hid this defect is retired).
GATE tests/test_bk47_head_dynamic_path.py 6/6 ×2: L1 head -n 1 → 'alpha',
L2 -n 3 → three lines, L3 n-exceeds → whole file, L4 diagnostic (source
pins + live no-_COMMON TU dies at link with 'bk11_out_ch' + selection-rule
pin), L5/L5b non-vacuity — L5b is the discriminating leg: `_COMMON`
surgically neutered via monkeypatch → the device run returns the bare ERR
string (pre-fix measured behavior), restored → green.
RED-first: gate stash-RED at HEAD 9fa94508 = 3 failed / 3 passed (L4/L5/L5b;
L1-L3 vacuous pre-swap per the BK-46 caveat — the probe carries the true
RED). Family = the combined 35/35 above. NOT proved: pipe/stdin forms,
WGSL twin, tail native path. Full receipt:
.builder_queue/RECEIPT_BK46_BK47_shell_native_seed.md
Numbers structural, rule-1 floors do not attach.
"""
text = text.rstrip() + tail
p.write_text(text)
print("backlog updated, len", len(text))

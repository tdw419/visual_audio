# RECEIPT — DESKTOP FLOOR: agent pre-verification transcript (DTF exit criterion)

**Date:** 2026-09-23 ~19:4x CDT · **Executed by:** seat lane (Hermes session)
**Per:** AMENDMENT_DTF1_desktop_floor.md, "Agent pre-verification of the floor"
section · **HEAD:** 32e69569 (clean, stall_tier=0)
**Verdict: ALL LEGS GREEN — desktop floor COMPLETE.**

## Scope-of-proof reminder (binding wording from the amendment)

This transcript certifies CORRECTNESS of the four legs. It does NOT certify
usability — no batch/piped transcript can. Usability remains the sole purpose
of an operator's own session entry. Different artifacts, different signers,
neither laundered into the other.

## Leg 0 — Boot (installer, WGSL fleet on the shader path)

```
status      : fleet_ready_verified
receipt word: 0x5eed0005
done bits   : 0b1011
```
Fleet runs to completion ON THE SHADER PATH (GlyphRunner.run_wgsl), halt @458,
words host-verified — R1.4 convergence criteria still holding.

## Legs 1-2 — Shell dispatch + grammar, from the real human entry point

Pipe: `what time is it` / `w [glyph]{floor} 95%` / `read me the news` / `r` / `quit`
into `experiments/glyph_interactive_shell.py` (the surface a person types into):

- `what time is it` → **ERR:UNKNOWN_CMD** (not silently written — item-11 fix holding)
- `read me the news` → **ERR:UNKNOWN_CMD** (not silently read)
- `w [glyph]{floor} 95%` → file written, byte-exact: ` [glyph]{floor} 95%`
- `r` → read back: ` [glyph]{floor} 95%`
- audio produced by natural sentences: **none (correct)**
- all 95 printable ASCII glyphs render — brackets/braces/pipe/tilde included
  (BK-19/landed atlas), decoded glyph-side byte-exact:
  in  : `glyph-sh: [floor]{done} | 95/95 ~`|`
  out : `glyph-sh: [floor]{done} | 95/95 ~`|` — **byte-exact: YES**

## Leg 3 — FS grow (files that grow)

```
test_bk7_two_appends_grow_file_and_read_back PASSED
test_bk7_delete_creates_reusable_slot     PASSED
2 passed
```
Append twice → whole file read back byte-exact; delete → hole; create → reuse.

## Leg 4 — Coreutils (five real compiled C programs on the GPU)

```
[cat]   PASSED   [echo]  PASSED   [wc]  PASSED
[cmp]   PASSED   [head]  PASSED   cmp exit-code pin PASSED
6 passed in 24.55s
```
Real riscv64-gcc → transpile → GPU execution → byte-exact vs native, per tool.

## Regression stack at HEAD (same run window)

Console + dispatch suites: **17 passed** · BK-7: **2 passed** · BK-11: **6 passed**
· installer fleet: fleet_ready_verified. Monitor: CLEAN, stall_tier=0.

## Apple-II-comparable, in the amendment's checkable sense — MET

Keyboard → shell → commands that do things → files that grow → visible on-GPU
screen → five real compiled programs. Every leg machine-verified in sequence,
today, at HEAD.

## Not verified / honesty

- Usability: NOT certified by this receipt (see scope reminder).
- The 16-byte stdout-window tool contract stands; fixtures are ≤16 B by design.
- wg `head` fixtures ≤ window; no claims about arbitrary-size coreutils.
- No rate claims → floors N/A (rule 1 not triggered).
- Interactive leg used piped stdin through the real entry point, not a tty.

**FLOOR STATUS: COMPLETE.** Next: BK-18 (sharded suite runner — builder infra),
BK-21 (SE021 'x' verb reachability), BK-15/16 (ls/time verbs) as supply.

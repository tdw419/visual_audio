# RECEIPT — DTF-1 follow-through item 9: human entry surface repointed to dispatch shell

**Date:** 2026-09-22 ~17:3x CDT
**Builder:** af3e62239ce2 (2m cron, product lane)
**Base revision:** 1fbb28c3 (item-9 brief landed in ledger; code untouched)
**Scope touched:** `experiments/glyph_interactive_shell.py` (`__main__` only, lines 646–669 post-change) + this receipt + `PRODUCT_LANE_STATE.md`. No engine, codec, or test-file changes.

## Defect (the gap item 9 closes)

`__main__` ran `repl(lines=None)` with `image=None`, which `repl()` defaults to
`build_shell()` — the always-echo shell (glyph_interactive_shell.py:622 pre-change).
DTF-1's mechanism (TASK_SE020, 2227ebc5) was gated and receipted (RECEIPT_DTF1_shell_dispatch.md)
but invisible to a human at the entry point: every line echoed, nothing dispatched.

## Gate legs (item 9's gate, from PRODUCT_LANE_STATE.md round 4)

### (a) RED-first — echo-not-dispatch on the exact pipe, PRE-fix

```
$ printf 'w hello\nr\nquit\n' | python3 experiments/glyph_interactive_shell.py
  echo: w hello
  echo: r
$ ls /tmp/glyph_dispatch_w.dat
  No such file or directory
```
`w hello` echoed verbatim (always-echo path), no file written. Reproduced live
this session at base 1fbb28c3, matching the brief's 2026-09-22 demonstration.

### (b) GREEN — same pipe post-fix

```
$ rm -f /tmp/glyph_sh_write.dat
$ printf 'w hello\nr\nquit\n' | python3 experiments/glyph_interactive_shell.py
[SYSCALL] FILE_WRITE: 6 bytes from addr 1076 to path at 1024
[SYSCALL] FILE_READ: 6 bytes from path at 1024 to addr 1280
OUTPUT: r5 = 32 / 104 / 101 / 108 / 108 / 111
  echo:  hello
$ cat /tmp/glyph_sh_write.dat
 hello          # 6 bytes, byte-exact round-trip
```

Audio leg: `s testing` → `/tmp/glyph_sh_audio.wav` (44100 Hz, 14112 samples),
`Phy16Tone.decode(samples)` → `b' testing'` — decodable.

### (c) quit exits cleanly

`printf 'quit\n' | python3 experiments/glyph_interactive_shell.py` → exit rc=0.

### (d) Full DTF-1 gate re-run green at the fixed tree

- `pytest tests/test_glyph_app_shell_dispatch.py` → **6 passed**
- `pytest tests/test_glyph_interactive_shell.py` → **8 passed** (harness)
- ISA regressions: `pytest tests/test_glyph_isa_v2.py tests/test_pillar21_abi_spec_rotguard.py` → **27 passed**

### (e) Batch invariant intact

Only `__main__` changed; `repl()`'s signature and `lines=[...]` batch path are
untouched. Proof: all 6 dispatch tests exercise `repl(lines=[...])` and pass
under leg (d) — batch mode still never touches stdin.

## What the fix does

`__main__` now builds `build_dispatch_shell(write_path, audio_path)` with
env-overridable defaults (`GLYPH_SH_WRITE_PATH`=/tmp/glyph_sh_write.dat,
`GLYPH_SH_AUDIO_PATH`=/tmp/glyph_sh_audio.wav), runs it with
`fs_pix_enabled=True`, and the startup banner names the four commands
(e/s/w/r) + quit — addressing the day-1 finding "I don't know what to type."

## What this PASS does NOT prove

- Interactive (input()-driven) typing was not exercised by a human; verification
  used piped stdin, which `repl(lines=None)` reads through `input()` either way.
- `e`-leg audio and the WGSL-twin requirement remain DTF-2's scope (unchanged
  from RECEIPT_DTF1_shell_dispatch.md's caveats).
- No rate claims made; floors not consulted (none needed).
- Env-override names (GLYPH_SH_*) are new surface, untested beyond defaults.

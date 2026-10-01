# RECEIPT — DEFECT-22 live SIGSEGV capture instrument (arc leg A under GDB)

**Tick:** builder cron `af3e62239ce2`, 2026-09-13 ~08:0x CDT. Head at start **`5da0a63`** (`tracked_dirty=0`).
**Target:** the only open ticket, `DEFECT-22` (`.builder_queue/DEFECT-22_arc_legA_instability.json`), whose own
`next_step` reads: *"the next RED should be captured LIVE rather than post-mortem — run the replay under gdb so
the [fault is caught where it happens]."* No roadmap row and no product-design judgment: this is an instrument.
**Deliverables (all new, all committed this tick):**

| Path | Role |
|---|---|
| `tools/gdb_segv_capture.gdb` | non-interactive GDB command file: `handle SIGSEGV stop print nopass` + greppable `DEFECT22_CAPTURE:` marker block (signal, `$pc`, `si_addr`, faulting instruction, `info symbol $pc`, `thread apply all bt 40`, `$_exitcode`) |
| `tools/arc_lega_capture.sh` | the instrument: runs arc leg A (same 52-file selector + pinned `--randomly-seed` as `tools/arc_lega.sh`) **under GDB**, writes `<OUTDIR>/arc_lega_capture_seed<SEED>_<HEAD>[_rerun<N>].{txt,json,gdb.txt}` |
| `tools/gate_arc_lega_capture.sh` | the gate (conventions of `tools/gate_arc_lega_naming.sh`): exit 0 = RED observed AND green holds · 1 = fail · 2 = setup fail |
| `tests/fixtures/faulthandler_segv_fixture.py` | deterministic crasher used by the gate (faulthandler on, sentinel line, then `ctypes.string_at(0)`) |

## 1. The mechanism, measured before it was built

The 05:18 core was recovered (`systems/RECEIPT_DEFECT22_CORE_RECOVERED.md`) but **could not supply the
faulting address or instruction**: `faulthandler` consumes the original `siginfo` when it re-raises. Measured
on this host, `/usr/bin/gdb` = GNU gdb 15.1, `yama/ptrace_scope = 1` (so GDB traces a child it launches
itself — this is why the instrument launches and never attaches), `core_pattern` = apport pipe:

```
Program received signal SIGSEGV, Segmentation fault.
__strlen_avx2 () at ../sysdeps/x86_64/multiarch/strlen-avx2.S:76
=> 0x7ffff7d8badd <__strlen_avx2+29>:	vpcmpeqb (%rdi),%ymm0,%ymm1
$1 = (void *) 0x0                                   <- p $_siginfo._sifields._sigfault.si_addr
#1  ... in ?? () from /usr/lib/python3.12/lib-dynload/_ctypes.cpython-312-x86_64-linux-gnu.so
```

`stop` fires **before** the in-process handler, so no `Fatal Python error:` line appears and the native
context is intact. That is the whole value: address + instruction + shared-object attribution, live.

## 2. Gate — run by the orchestrator, twice, identical verdicts

Command: `bash tools/gate_arc_lega_capture.sh` → **rc=0**, all five legs PASS
(`output/defect22_live_capture_gate_GREEN.txt`). Legs and their observed values:

- **L1 capture works on the real mechanism** (fixture crashed on purpose, through the instrument's own gdb
  file): marker present; `si_addr = (void *) 0x0`; `pc = 0x7ffff7d8badd`;
  `pc_symbol = __strlen_avx2 + 29 in section .text of /lib/x86_64-linux-gnu/libc.so.6`; faulting
  instruction `vpcmpeqb (%rdi),%ymm0,%ymm1`; instrument exit **139**. *This is a genuine crash, not a mock —
  it is the same libc frame my independent probe above hit.*
- **L2 what it buys / the gate discriminates**: the same fixture run plain →
  `Fatal Python error: Segmentation fault` present **1**, literal `si_addr` **0**, `.so` attribution **0**.
  The post-mortem path really does lose exactly what L1 asserts.
- **L3 plumbing + no-clobber**: `PY` stub run twice at the same (seed, head) → both artifacts written, sidecar
  JSON has every required key, `capture.segv_caught=false`, `capture.si_addr=null`, rc = the stub's; the
  second run lands on `…_rerun2.*` and the first pair's md5s are **byte-identical** afterwards.
- **L4 explicit falsifier**: a temp copy of the gdb file with the stop clause neutralised
  (`handle SIGSEGV nostop pass`) → `si_addr=none`, `pc_symbol=none` → L1's assertions **RED**. A gate that
  cannot go red is not a gate; this one was shown red on demand.
- **L5 hygiene**: 0 tracked modifications, all four deliverables present.

**Second, independent RED leg (orchestrator, outside the gate):** the instrument moved aside →
`bash tools/gate_arc_lega_capture.sh` → **rc=2**, `L1 SETUP FAIL: no gdb transcript written`
(`output/defect22_live_capture_gate_RED_holdout.txt`). Instrument restored byte-identical
(md5 `dbe0103e1c897d768ceaa8f9189b2ae3` before and after).

## 3. Acceptance on the real arc (the 52 files, not a stub)

`SEED=1914088745 bash tools/arc_lega_capture.sh` at `5da0a63` →
**rc=0, 325 passed / 1 skipped / 1 deselected, 123.58 s, `segv=no`, crashes=0**
(`output/arc_lega_capture_seed1914088745_5da0a63.{txt,json,gdb.txt}`; the transcript's capture block reads
`segv_caught=false` with `exitcode=$1 = 0`, and the pytest log in the same file carries the full 325-pass
summary). Overhead vs the plain runner is ~+3 s (123.58 s here vs 120.8–121.3 s for `tools/arc_lega.sh` at
`cf9ae6d`), so running the arc under the debugger does not meaningfully perturb wall-clock. The 52-file
selector and the ARGS block are byte-identical mirrors of `tools/arc_lega.sh:52-53` and `:70-71`, cited by
line number at both mirror points.

## 4. Honest boundaries — what this does NOT establish

- **It has not yet caught the real defect.** Capture runs under this instrument: **n=1, 0 disturbed**. The
  claim "the next RED will yield si_addr + instruction" is untested against DEFECT-22 itself; it is proven
  only against a crash we caused on purpose (L1).
- **The plain-arc ledger is unchanged: post-`194844c` 12 runs / 0 disturbed.** The capture run above is
  recorded as its own series (instrument acceptance), *not* folded into the plain ledger, because a debugger
  changes timing and a gdb-stopped process is not the same experiment as an unwatched one.
- **A stopped process is not a diagnosed one.** With `handle SIGSEGV stop`, GDB halts the run at the first
  SIGSEGV — including a *handled* one. Only `tests/test_suite_iso_harness.py` mentions SIGSEGV in `tests/`
  and it is not in the arc's 52-file selector, but the risk is stated rather than exhausted.
- **Implementation warts found in review (behaviour verified, ergonomics not):** (a) the "did a signal stop
  us?" branch keys on `$_thread != 0`, an indirect heuristic — L1/L3/L4 exercise both branches, but it is a
  heuristic; (b) `crashes` in the sidecar counts `Fatal Python error` lines in the *run log*, so a captured
  SIGSEGV yields `crashes=0` + `rc=139` + `capture.segv_caught=true` — the capture object is authoritative,
  the counter is not; (c) the gate's L5 verifies *no tracked file was modified* + the four files exist, which
  is weaker than the brief's "git status shows only the four new files".
- **Not verified this tick:** any crash mechanism; whether a *new* core is written on the next crash (the
  re-armed path from the previous tick remains structural, not exercised); WGSL/GPU; QEMU lockstep; the OSS
  lane repo (unpushed, out of lane); the canvas.

## 5. Teleop (B-state discipline)

**Meta only**, no surface read, so no spatial claim is made. `geos_surface_meta`: `tick = 0`,
`age_seconds = 223628.2` ≈ **62.1 h** — the machine is not stepping (the snapshot is the same archaeology it
was last tick, +275 s). Every number in this receipt comes from commands run on the host shell, which is
exactly the asymmetry the skill names: nothing governed my writes here, so the gate above is the containment
layer.

## 6. Next step

Arm it and wait for a RED: `SEED=<seed> bash tools/arc_lega_capture.sh` (exit 139 + a `capture` object with
non-null `si_addr`/`pc_symbol` is the signal). The two remaining supply questions are Jericho's:
renew the lane, or accept DEFECT-22 as a documented stability bound and release the level trigger.

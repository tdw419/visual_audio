# Brief — DEFECT-22 live SIGSEGV capture instrument (ticket-directed, no roadmap row)

## Why (read this first)

`DEFECT-22` (`.builder_queue/DEFECT-22_arc_legA_instability.json`) is the only open ticket: arc leg A
(52-file canonical set) is intermittently disturbed — 2 of 17 runs, both at `194844c`, plus an
LLM-sampling red in the gh12 leg (that half is already closed by `RULING_gh12_gate_determinism.md`
OPTION 3). The 05:18 SIGSEGV left a core, and it was recovered this session
(`systems/RECEIPT_DEFECT22_CORE_RECOVERED.md`), but the post-mortem **could not supply the faulting
instruction or address**: `faulthandler` consumes the original `siginfo` before re-raising, so the core's
`si_addr` is gone (`output/defect22_core_bt.txt`). The ticket's own `next_step` says exactly what to build:
**capture the next RED live under gdb**, not post-mortem.

So this is an INSTRUMENT task, not a product feature. There is no roadmap row and no design judgment left —
the semantics below are already MEASURED by the orchestrator on this host (see next section). Your job is to
turn that measured mechanism into a committed-quality script pair plus a gate.

## MEASURED by the orchestrator this tick (do not re-derive, do not contradict)

Host: `/usr/bin/gdb` = GNU gdb 15.1 (Ubuntu 15.1-1ubuntu1~24.04.1); `yama/ptrace_scope = 1`
(so gdb may trace a child it launches itself — this is why we launch under gdb and never attach);
`kernel.core_pattern` = apport pipe.

Probe: a faulthandler-enabled Python that calls `ctypes.string_at(0)`, run as
`gdb -q -batch -x cmds.gdb --args /usr/bin/python3 faulthandler_segv.py` with `cmds.gdb` =
`set pagination off` / `set confirm off` / `handle SIGSEGV stop print nopass` / `run` / capture / `quit`.

Result (verbatim, this is the mechanism the instrument must reproduce):

```
Program received signal SIGSEGV, Segmentation fault.
__strlen_avx2 () at ../sysdeps/x86_64/multiarch/strlen-avx2.S:76
=> 0x7ffff7d8badd <__strlen_avx2+29>:	vpcmpeqb (%rdi),%ymm0,%ymm1
$1 = (void *) 0x0                     <- p $_siginfo._sifields._sigfault.si_addr
#1  0x00007ffff7bc6b7c in ?? () from /usr/lib/python3.12/lib-dynload/_ctypes.cpython-312-x86_64-linux-gnu.so
#4  0x00007ffff7fab0be in ffi_call () from /lib/x86_64-linux-gnu/libffi.so.8
```

Three facts that are the whole point:
1. `handle SIGSEGV stop print nopass` stops **before** Python's `faulthandler` runs — no
   `Fatal Python error:` line appears in the probe output, so the signal was intercepted while the
   original `siginfo` was still intact.
2. `$_siginfo._sifields._sigfault.si_addr` is therefore readable = `0x0`.
3. The backtrace attributes frames to concrete shared objects (`_ctypes...so`, `libffi.so.8`) — library
   attribution is exactly what the 05:18 core lacked (the interrupted PC fell inside
   `/usr/bin/python3.12` between two named symbols with no instruction).

Also measured: gdb printed a debuginfod prompt banner when the command file did not disable it. Put
`set debuginfod enabled off` in the command file so the run is non-interactive and fast.

## Deliverables (exact paths, all NEW — do not modify any existing file)

### 1. `tools/gdb_segv_capture.gdb` (NEW)
gdb command file, non-interactive, no prompts. Must contain at least:
`set pagination off`, `set confirm off`, `set debuginfod enabled off`, `set print frame-arguments none`,
`handle SIGSEGV stop print nopass`, `run`, then the capture block, then `quit`. The capture block must
emit a stable machine-readable marker line and, under it: the signal name; `$pc`; `si_addr` via
`p $_siginfo._sifields._sigfault.si_addr`; the faulting instruction (`x/2i $pc`); symbol/region
attribution (`info symbol $pc`); a full backtrace (`thread apply all bt 40`); and the inferior's exit code
(`$_exitcode`). Line labels must be greppable and stable — the instrument parses them (suggested
`DEFECT22_CAPTURE:` prefix per field, e.g. `DEFECT22_CAPTURE: si_addr=0x0`).

### 2. `tools/arc_lega_capture.sh` (NEW, executable)
The instrument: run arc leg A under gdb using the command file above.
- **Mirror, do not fork.** The 52-file selector must be byte-identical to `tools/arc_lega.sh:52-53` and
  the pytest ARGS block identical to `:70-71` (same `-q|–v`, `--tb=line`, `-m "not live_smoke"`,
  `-p randomly --randomly-seed=$SEED`). Same `SEED`/`VERBOSE`/`PY`/`OUTDIR` env knobs, same
  `ulimit -c unlimited`. Add a comment at each mirror point citing the `arc_lega.sh` line numbers so the
  two selectors cannot drift silently.
- **Artifacts, never clobber** (same discipline as `arc_lega.sh:58-65`):
  `<OUTDIR>/arc_lega_capture_seed<SEED>_<HEAD>[_rerun<N>].txt` (the run log),
  `.json` (sidecar), plus the raw gdb transcript `<...>.gdb.txt`.
- **Sidecar JSON keys**: `seed`, `head`, `rc`, `crashes`, `seconds`, `summary`, `log`, `gdb_log`,
  `started_utc`, `loadavg_before`, and a `capture` object
  `{"segv_caught": bool, "signal": str|null, "pc": str|null, "si_addr": str|null, "pc_symbol": str|null}`
  parsed from the transcript.
- **Exit code**: a caught SIGSEGV must be unmistakable — exit **139** when `capture.segv_caught` is true;
  otherwise propagate the inferior's exit code from `$_exitcode` (state the fallback in a comment if gdb
  does not supply it — e.g. gdb's own rc). Do not swallow rc=0 into success when a SIGSEGV was caught.
- **stdout summary** (one line, matching the existing style):
  `arc leg A (live capture) :: seed=… head=… rc=… segv=yes|no si_addr=… pc=…` then the log/sidecar paths.
- Must run end to end with `PY` pointed at a stub (see the gate) so the plumbing is testable in <2 s.

### 3. `tools/gate_arc_lega_capture.sh` (NEW, executable)
The gate. Follow the conventions of `tools/gate_arc_lega_naming.sh` exactly: `set -u`, `REPO=`, `cd`, exit
**0 = red observed AND green holds**, **1 = gate failed**, **2 = setup failure**, a `mktemp -d` with a
`trap cleanup EXIT`, and per-leg PASS/FAIL lines. Legs (each must be individually re-runnable and its
verdict printed):
- **L1 — capture works on the real mechanism (not a mock).** Drive the instrument's own gdb command file
  against `tests/fixtures/faulthandler_segv_fixture.py` (deliverable 4) with a `PY` stub so pytest is
  skipped. Assert the transcript carries the marker, a non-empty `si_addr`, a non-empty faulting
  instruction, and a `pc_symbol`/attribution line naming a shared object. Print the parsed values.
- **L2 — what it buys, i.e. the gate can discriminate.** Run the SAME fixture WITHOUT live capture
  (neutralised: `handle SIGSEGV nostop nopass`, and/or plain `python3` with faulthandler) and assert the
  output shows `Fatal Python error: Segmentation fault` **and** has **no** `si_addr` and **no** shared-object
  attribution. If the neutralised run also produces a faulting address, the gate must FAIL — a gate that
  cannot go red is not a gate.
- **L3 — instrument plumbing + no-clobber.** With a `PY` stub that echoes a nonce and exits 0: both
  artifacts are written, the JSON parses, `capture.segv_caught` is false, `capture.si_addr` is null, the
  summary line is present, and the exit code equals the stub's. A second run at the same (seed, head) must
  produce a `_rerun2` pair and leave the first pair's md5 byte-identical.
- **L4 — explicit falsifier.** Make a temp copy of the gdb command file with the `handle SIGSEGV stop`
  clause removed, run L1's assertions against that copy, and show them RED (with the observed output).
  Print both observations.
- **L5 — hygiene.** `git status --short` at the end shows only the four new in-scope files (plus anything
  already untracked before you started — do not clean the tree).

### 4. `tests/fixtures/faulthandler_segv_fixture.py` (NEW)
Tiny, deterministic: `faulthandler.enable()`, print a sentinel line, flush, then dereference NULL via
`ctypes.string_at(0)`. It exists to be crashed on purpose by the gate.

## Hard constraints

- **Do NOT commit.** Leave everything in the working tree.
- Do not modify: `tools/arc_lega.sh`, `tools/gate_arc_lega_naming.sh`, `pytest.ini`, any existing
  `tests/test_*.py`, `systems/GLYPH_SELF_HOSTING_ROADMAP.md`, or any core file
  (`tools/glyph_gpt/baker.py`, `tools/rv64i_to_glyph.py`, `glyph_dispatch/**`, WGSL shaders).
- Do not add anything to `tests/` that a plain `pytest tests/` would execute as a real test.
- Keep it boring: bash + gdb, no new Python dependencies, no daemons, no network.
- Hermetic: the gate must not need the 52-file arc to run (it is 138 s); the arc is exercised separately
  by the orchestrator.

## Report back

Exact file paths, the one-line gate command, and the gate's raw output (all legs, PASS/FAIL, exit code).
State plainly anything you could not verify.

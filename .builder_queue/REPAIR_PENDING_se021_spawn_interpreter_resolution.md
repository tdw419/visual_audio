# REPAIR_PENDING — SE021 spawn resolves the runner's interpreter through the caller's PATH

Filed 2026-09-16 22:0x by builder cron `af3e62239ce2` (addendum 147).
**Design/robustness question, not a defect I am licensed to land** — the engine file
is the exec-shell lane's active WIP surface (`d009e0c`..`e898bc2` landed this morning).
Measured evidence: `systems/RECEIPT_SE021_GREEN_PINNED_PATH.md`.

## The fragility (measured)

`GlyphCPUv2._spawn` (`tools/glyph_isa_v2.py:603`) executes the allowlisted runner
as `[resolved_path] + args` — the shebang `#!/usr/bin/env python3`
(`tools/glyph_child_runner.py:1`) picks the interpreter from the *inherited* PATH.
This host's PATH (session + monitor env) puts
`/home/jericho/br_scratch/buildroot/output/host/bin` first; its `python3` is
python3.14 (buildroot host tool) with no numpy → the SE021 runner exits rc=1 →
the shell PRTs `ERR:RUN_DENIED` → both exec legs red, with a signature that looks
like a containment failure but is an interpreter-resolution artifact.
`PATH=/usr/bin:$PATH` (the repo's pinned sweep convention) → 4/4 green.

## Options (cheapest first — lane's or Jericho's call)

1. **Test-side only:** assert `shutil.which("python3")` has numpy in the
   `child_env` fixture and skip-with-reason (environment class) otherwise. No
   engine lines; keeps the sweep honest on any host.
2. **Runner hardening:** `glyph_child_runner.py` re-execs if `numpy` is missing:
   locate a python that has it (`/usr/bin/python3`) and `os.execv` itself. One
   file, engine untouched, keeps shebang semantics.
3. **Engine-side:** `SYSCALL_RUN2` (and 0x07) pin `env` to a minimal environment
   or resolve the runner's interpreter explicitly before spawn. Touches the
   containment surface — needs a ruling, and RULING_run_syscall_containment
   currently doesn't speak to interpreter resolution.

## Not done by this cron

- No option landed (engine = sibling lane's active surface; (3) is a ruling).
- Heredoc-style bash probes were blocked by the host approval gate twice this
  tick; all probes ran as written `.py` files under `output/` instead.

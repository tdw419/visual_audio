# RULING — 0x07 SYSCALL_RUN: default-deny allowlist

**Ruled:** 2026-09-13
**Decision seat:** Jericho
**Drafted by:** Hermes, authorized by "You lead" (2026-09-13)
**Decides:** the containment question the builder flagged in its 2026-09-13 report
(landed in `tools/glyph_isa_v2.py`, handler `_handle_syscall`, syscall 0x07).

## What the code does today

    elif syscall_num == 0x07:  # SYSCALL_RUN
        path_addr = self.registers[1]
        path = _read_path(path_addr)          # guest-supplied, up to 4096 bytes
        if not os.path.isfile(path): return -1
        os.chmod(path, 0o755)                 # <-- side effect on HOST perms
        res = subprocess.run([path], cwd=parent_dir, timeout=30, capture_output=True)
        return res.returncode

Two problems, in order of severity:

1. **No containment.** Emulated spatial code names any host path and the host runs
   it. Guest images are untrusted input here (they can arrive as a tile or container
   the guest loaded), so this is the largest blast-radius expansion in the codebase:
   arbitrary host execution, granted implicitly, with no operator decision.
2. **`os.chmod(path, 0o755)` mutates the operator's filesystem.** An execute
   syscall has no business changing host permissions, and the change persists after
   the VM exits. This is a defect in its own right, fixed by this ruling.

## The enabling finding (why this is cheap)

`tests/test_glyph_run_program.py` pins the **encoding** (r1=path_addr, r7=7,
`SYSCALL r0 7`) and asserts only `assert not cpu.running` (line 50). It never
asserts that the run *succeeded*. Therefore a default-deny allowlist breaks
**zero existing tests**, and the ABI is untouched. The 3 pinned tests pin the
instruction encoding, not the behaviour.

## Decision — default deny, exact match, no chmod

1. **Keep the syscall.** Semantics and encoding unchanged (r1 = path_addr, r7 = 7,
   return = exit code or -1). This ruling changes *policy*, not interface.
2. **Default deny.** The allowlist comes from env `GLYPH_RUN_ALLOW`, a
   colon-separated list of absolute paths. Unset or empty means **deny all**.
   The safe posture is the default; execution is an explicit operator grant.
3. **Exact match on resolved paths.** Compare `os.path.realpath(requested)` against
   `os.path.realpath(entry)` for equality. No prefix matching, no globbing —
   a prefix rule on a directory would grant everything beneath it, and
   realpath-first means `ok.py/../evil.py` cannot smuggle past entry `ok.py`.
4. **Drop `os.chmod`.** The guest may not change host file permissions. (The pinned
   test chmods its own temp script at line 14, so removal breaks nothing.)
5. **Keep** `shell=False` with list argv, `timeout=30`, `capture_output=True`,
   `cwd=os.path.dirname(abspath(path))`.
6. **Refusal is a return, never an exception.** Return -1 and print one line naming
   the reason. A denied request must not raise into the guest or the host loop.
7. **Make the runner injectable** (module-level indirection over `subprocess.run`).
   This is what lets the gate prove "no process was spawned" without spawning one —
   without it, the strongest negative leg is unavailable.

## Gate clauses (gate: `tests/test_run_containment.py`, RED first)

- **L1 allowed path runs** — path in the allowlist → exit code echoed; with the
  injected runner double, called exactly once with `argv == [path]`.
- **L2 default deny** — `GLYPH_RUN_ALLOW` unset or empty → returns -1 **and the
  runner is never called**. Counting double; no process spawned.
- **L3 not-allowlisted** — file exists and is executable but is not allowlisted →
  -1, no call. *This leg fails on today's code — it is the discriminating check.*
- **L4 no prefix smuggling** — allowlist `/tmp/x/ok.py`; requests
  `/tmp/x/ok.py/../evil.py` and `/tmp/x/ok2.py` both deny (realpath equality).
- **L5 no chmod** — a target with mode 0o644 has the same mode after the call
  (stat before == after), using the runner double.
- **L6 pinned test unchanged** — `tests/test_glyph_run_program.py` still passes with
  no opt-in line added (it asserts only `not cpu.running`).
- **L7 refusal is a return** — denial yields rc -1, one reason line naming the
  cause, and no exception propagates.
- **L8 invariant** — the handler source contains no `shell=True`.

L3, L4 and L5 must be **shown RED against the pre-fix code** and their transcript
recorded, per the repo's evidence discipline.

## Cost and non-goals

Cost: ~30 lines in the handler plus a small allowlist helper and one new test file.
No ABI change, no existing-test breakage, no interface churn.

Non-goals (deliberately): this is **not** a sandbox — no namespaces, chroot, seccomp
or resource limits; not a network policy; not the general capability model (that
direction is `tools/geos_caps.py`); not removal of the syscall. It is the single
minimum that stops untrusted guest code from executing host binaries by default.

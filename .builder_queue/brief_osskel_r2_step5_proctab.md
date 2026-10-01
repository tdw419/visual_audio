# BRIEF — OS-SKEL-R2 Phase 3, Step 5: `Proctab.admit` / `mark_exited` / `reap`

**Round:** `.builder_queue/brief_osskel_r2_phase3.md` (step 5 of 7)
**File in scope (ONLY):** `/home/jericho/projects/zion/projects/visual_audio/tools/geos_proctab.py`
**Gate (already authored by the orchestrator — do NOT edit it):** `tests/test_osskel_proctab_lifecycle.py`
**Harness already amended by the orchestrator — do NOT edit:** `tools/geos_os_skel_verify.py`

## Gate command (run it yourself; it must end `7 passed`, exit 0)

```
cd /home/jericho/projects/zion/projects/visual_audio
/usr/bin/python3 -m pytest tests/test_osskel_proctab_lifecycle.py -q
```

RED baseline (captured this tick, `output/osskel_r2_step5_gate_RED_20260912.txt`, exit 1):
`6 failed, 1 passed` — L1..L6 fail against the stub module; L7 (interface hygiene) passes today.

Also must stay green (run each):
```
/usr/bin/python3 tools/geos_os_skel_verify.py     # exit 0, 85 legs + self-test, count unchanged
/usr/bin/python3 tools/geos_spine_verify.py       # exit 0
/usr/bin/python3 tools/geos_proctab.py            # exit 0 (module smoke must still run)
```

## The gate's clauses (each is a leg; implement to satisfy all of them)

| Leg | Clause |
|---|---|
| L1 | admit → READY + pid reserved in `Proctab.pids`; RUNNING; `mark_exited(pid, 42)` → ZOMBIE holding 42, excluded from `ready_set`, present in `zombies`; `reap` returns 42, state DEAD, asid gone from the bound `AsidAllocator` |
| L2 | while a pid is an unreaped zombie, NEITHER that pid NOR its asid is handed out again (`alloc()` returns the next free); after reap both are lowest-free again and a fresh descriptor with the same pid+asid admits |
| L3 | `reap` on READY / RUNNING / WAITING raises `InvalidTransition` and mutates nothing (note: READY→DEAD *is* in `LEGAL_TRANSITIONS`, so reap must check ZOMBIE explicitly, not rely on the transition guard alone) |
| L4 | with no allocator bound, `reap` raises `RuntimeError` BEFORE mutating: process stays ZOMBIE with its code, pid stays reserved, asid stays live; binding afterwards lets the same reap complete (no partial release) |
| L5 | `admit` refusals are loud and non-mutating: duplicate live pid → `ValueError`; descriptor not in NEW → `ValueError`; pid not the lowest free pid (I1) → `ValueError` AND the failed pid reservation is rolled back; no allocator bound → `RuntimeError`; asid that no allocator handed out (I5) → `ValueError` |
| L6 | two children (pids 1,2 under parent 0) exit 11 and 22; reap returns each child's own code in any order; afterwards only the parent is live and both pids+asids are reusable |
| L7 | signatures/annotations unchanged: `admit(self, desc)`, `mark_exited(self, pid, code)`, `reap(self, pid) -> Optional[int]`, `admit(...) -> ProcessDescriptor`; `__all__` unchanged (exact set asserted); the allocator hook stays in `tools/geos_aspace.py` |

## Exact semantics to implement

1. **Allocator hook (step-3 idiom — do NOT invent a fourth convention).** `reap` and `admit` reach the `AsidAllocator`
   through `tools.geos_aspace.get_asid_allocator()`. Import it at module level:
   ```python
   from tools.geos_aspace import AsidAllocator, get_asid_allocator   # noqa: F401 (AsidAllocator used in __main__)
   ```
   The harness AST-scans imports and whitelists the top-level name `tools`, so this import is legal. But
   `python3 tools/geos_proctab.py` puts `tools/` (not the repo root) on `sys.path`, so guard it:
   ```python
   try:
       from tools.geos_aspace import ...
   except ModuleNotFoundError:            # direct script execution
       sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
       from tools.geos_aspace import ...
   ```
   `__all__` must NOT gain any allocator name.

2. **`admit(desc)`** — validate first, mutate last (any refusal leaves `procs`, `pids` and the allocator untouched):
   - `desc.state != STATE_NEW` → `ValueError`.
   - `desc.pid` already in `self.procs` with a state other than `STATE_DEAD` → `ValueError`
     (an unreaped pid is not reusable, I4). A stale `DEAD` entry may be replaced.
   - `get_asid_allocator()` is `None` → `RuntimeError` ("no asid allocator bound: refusing …").
   - `desc.asid not in allocator.live()` → `ValueError` (a process whose aspace nobody allocated is malformed, I5).
   - pid reservation: `granted = self.pids.alloc()`; if `granted != desc.pid`, `self.pids.free(granted)` then
     `ValueError` (lowest-free determinism, I1 — never silently retarget the descriptor).
   - then `self.procs[desc.pid] = desc` and `self.transition(desc.pid, STATE_READY)` (reuse the live I2 guard for
     NEW→READY instead of assigning the state directly). Return `desc`.

3. **`mark_exited(pid, code)`** — reject a non-int/bool-negative code with `ValueError`; then
   `desc = self.transition(pid, STATE_ZOMBIE)` (only RUNNING→ZOMBIE is legal, so a READY/WAITING/NEW process raises
   `InvalidTransition` from the live guard) and record `desc.exit_code = code`. Return `desc`.

4. **`reap(pid) -> Optional[int]`** — atomic: pre-flight everything, then mutate.
   - unknown pid → `KeyError`.
   - `desc.state != STATE_ZOMBIE` → `InvalidTransition` (explicit check, see L3).
   - `get_asid_allocator()` is `None` → `RuntimeError`, leaving state ZOMBIE and both pid and asid reserved.
   - pre-flight: `pid in self.pids.live()` and `desc.asid in allocator.live()`; if either is missing, raise
     (`KeyError`/`RuntimeError`) WITHOUT mutating — never a half-release.
   - then `self.transition(pid, STATE_DEAD)`, `self.pids.free(pid)`, `allocator.free(desc.asid)`, and return the
     held exit code. The descriptor stays in `self.procs` in state `DEAD` (harness leg 6g asserts exactly that);
     pid reuse happens through `PidAllocator`, and `admit` accepts a reused pid because the stale entry is DEAD.

5. **`ready_set` / `children_of` / `zombies` / `PidAllocator` / `can_transition` / `LEGAL_TRANSITIONS` / constants:
   UNCHANGED.** Never weaken the live guards to make a leg pass.

6. **`__main__` smoke**: it currently admits two processes without an allocator and calls `reap`, which under the
   new contract refuses. Bind an `AsidAllocator`, allocate each descriptor's asid from it, and unbind at the end —
   the smoke must still print and exit 0.

7. Update the module docstring's `PHASE STATUS` / `PHASE 3 TODO` text so it describes the populated bodies (still
   no kernel wiring, no real MMIO, no engine integration — say that plainly).

## Constraints

- **Additive only**, stdlib + `tools.*` imports only. Do NOT touch any other file (not the gate, not the harness,
  not `tools/geos_aspace.py`, `tools/geos_caps.py`, `tools/geos_devtab.py`, `systems/**`, `.builder_queue/**`,
  `tests/**`).
- **Do NOT commit.** Leave the tree dirty with your changes; the orchestrator verifies and commits.
- If any gate leg looks wrong or contradicts the frozen interfaces, STOP and report the conflict instead of
  editing the gate.
- Report: files changed, the literal tail of the gate run, and anything you could not make pass.

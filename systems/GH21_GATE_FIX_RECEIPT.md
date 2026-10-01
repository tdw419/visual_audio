# GH-21 Gate Fix Receipt — 2026-09-09 (builder run, 16:28–17:05 CDT)

## Symptom

GH-21 gate at 2/5: legs 2 (C binary write+exit word-exact), 3 (unrecognized
ecall traps clean), 4 (admission refusal) RED; legs 1/5 GREEN. Leg 2's
failure mode: `receipt.faulted=True, fault_addr=0x800C` (BOX0_LO E-K1
store trap from USER mode) — or, in an earlier state, stdout words 718/719
stuck at 0 with a clean halt.

## Diagnosis chain (each step measured, probes in output/dbg_gh21_*.py)

### Fix 1 — baked image was saved BEFORE the shim stamps

`posix_shim_kernel_image(out_path=...)` baked via `B.bake_image(...,
out_path=out_path)`, which saves the image to disk at that moment. The
shim tiles + table-slot entries were stamped into the in-memory array
AFTER. The test round-trips through the .npy, so the executed image had
NO shims at all.

- Probe: `dbg_gh21_stages.py` — px(1322) = (0,0,0) at every lifecycle
  stage (baked npy, runner.image, cell-137, end).
- Fix: re-save after stamping (mirrors `syscall_abi_kernel_image`
  baker.py:4432-4440 and `pixel_fs_v2_kernel_image` fs_v2.py:131-139).

### Fix 2 — tile rect PC computed from the UNSPLICED layout

`_gh18_tile_pc(mode="posix")` assembles the UNspliced kernel text:
`:__g18tile` at cell 232. The C-program splice (task A body replaced,
32 extra instructions) shifts the rect to cell **257** (probe
`dbg_gh21_layout.py`). `_stamp` therefore wrote 23 tile instructions
over cells 232–254 — the tail of the C task's own code.

Executed trace (probe `dbg_gh21_seq2.log`): the run enters the write
TILE's code at task cell 240 in USER mode, KJMPs `:__ksys_done`, SYSRET
restores the pre-trap regs and jumps to SYSCALL_PC — which was never
set by a real SYSCALL (stale 0) — landing at cell 0: the kernel
prologue re-executes AS USER and E-K1 faults on the BOX0_LO store
(word 8195, cell 59). One probe run after the OTHER fix showed the
exit-code word holding **93** — the raw SYS_N — proving the exit tile
had read SYS_N, not SYS_A0 (see fix 3).

- Fix: derive `tile_pc` from `coords1[":__g18tile"]` (the spliced
  two-pass coords) instead of `_gh18_tile_pc`. `:__ksys_done` and
  `:__g18done` sit BEFORE the task region, so their coords are
  splice-invariant and the `_gh18_dispatch_resume(mode="posix")` /
  coords1-based homes stay correct.

### Fix 3 — exit tile read SYS_N (0x200C) instead of SYS_A0 (0x200D)

`_gh21_sys_exit_tile()` used `LDI r15 0x200C`. Word 0x200C = 8204 =
SYS_N (0x8030>>2); SYS_A0 is 0x200D (0x8034>>2). After fixes 1–2 the
whole chain ran and the exit-code word (720) held 93 — the syscall
number — instead of 0 (probe `dbg_gh21_now.py`). Carried over from the
prior session's diagnosis item #3 (identified, never applied).

- Fix: `LDI r15 0x200D` with receipt comment.

## GREEN evidence

- `tests/test_gh21_posix_shim.py`: 5/5 pass (exit 0).
- `output/run_gate_gh18.sh`: 14/14 pass (GH-18 invariant intact).
- Full GH1–GH21 regression: see run log (expected ≥150 pass).

## Prior-session items (from the 16:28 report) — status

1. sp init (`LDI r2 1023`) — already present in the WIP loader; not
   re-touched this run.
2. `.rodata` seeding — already present in the WIP loader; the
   word-exact HELLO at 718/719 confirms it works.
3. Tile ABI word bug — applied this run (fix 3).
4. `admit_shims` semantics inversion — the WIP code already routes
   admit_shims=True through escalate; leg 4 passes; no change needed.
5. Exit-tile KJMP home — already in the WIP (`_home()` rewrite); the
   KJMP target is splice-invariant so it was correct once the rect PC
   was fixed.

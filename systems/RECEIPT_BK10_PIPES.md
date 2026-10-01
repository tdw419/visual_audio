# BK-10 Receipt — stdio beyond uart: pipes as FS files (SYS 16/17)

**Roadmap row:** BK-10 (promoted from GLYPH_BACKLOG at `b379c7a`, 2026-09-12)
**Implemented:** 2026-09-12, builder cron af3e62239ce2, branch `glyph-transpiler-autoloop`
**Gate:** `tests/test_bk10_pipes.py` — 2/2 (RED `output/bk10_gate_run1_red.txt` → GREEN `output/bk10_gate_run2_green.txt`)

## Spec → implementation mapping

Roadmap gate clause: "`tests/test_bk10_pipes.py` — `echo hi | toupper` via
two mailbox tasks + FS handoff; output byte-exact vs native pipe."

| Clause | Implementation |
|---|---|
| two mailbox tasks | prog1 (`echo`, BOX0 task A) + prog2 (`toupper`, BOX0 task B), GH-8 dispatch shape: entry KJMP → A, A exits via `:__bk10dispatch` KJMP → B |
| FS handoff | SYS 16 (pipe write) claims FSTAB slot 0 for `'PIPE'` (name/start/len/in_use = `PIPE`/1048/2/1) and copies exactly ONE word scratch[736] → pixel data region 1048; SYS 17 (pipe read) copies data[1048] → read-out 752. The pipe **is** an FSTAB file — a shell pipe reduces to a 1-word file copy |
| output byte-exact vs native pipe | test oracle runs the REAL host pipe `printf 'hi' \| tr a-z A-Z` via subprocess and asserts `mem[758] == b"HI"` packed — no hand-computed constant |

## Design decisions (mechanical, per spec)

- **The case flip lives in prog2, not the kernel.** The kernel's copy is
  byte-pure (LD/ST only); prog2 applies `XOR 0x2020` (ASCII a-z ↔ A-Z) after
  the read. Leg 2 asserts readout[752] still holds raw `'hi'` while
  stdout[758] holds `'HI'` — proving the handoff went through the FS copy
  rather than a transformed transfer.
- **stdout is an in-image word (758), not the GH-10 uart.** Words 910..912
  stay untouched: uart becomes one output channel among many, stdout is the
  FS/box-backed alias the shell can later `dup()` for real redirection.
- **SYS numbers 16/17** continue the FS family (GH-8 6/7/8, BK-7 9, BK-9
  12/14) in the same KSYS selector shape — no new dispatch machinery.

## Defects found during bring-up (both engine-contract lessons)

1. **BUG-14 — E-K1 on out-of-box staging.** First bake put the task→kernel
   scratch window at RAM word 1096 (outside BOX0). Task A's staging store
   faulted instantly: `fault_addr=0x1120` (= 4368 bytes = word 1096),
   `faulted=True`, steps=32. Root cause: USER stores outside the box trip
   E-K1 by design (GH-6 isolation contract); GH-8's scratch (736) and
   readout (752) are in-box for exactly this reason. Fix: scratch → 736,
   stdout → 758 (both inside BOX0 [700,768)); only the KERNEL touches the
   pixel FS window, tasks reach it exclusively through SYS.
2. **Exit-word packing.** `BK10_N_WRITE & 0xF` packs 0 not 0x10 — the
   `& 0xF` idiom only works for syscall numbers ≤ 15. Fix: `LDI r4 16` /
   `LDI r4 17` are LDI-safe direct constants added to `0xFEED << 16`.

## Verification (measured this run)

- Gate: 2/2 passed (`output/bk10_gate_run2_green.txt`, exit 0)
- Arc regression: **117 passed** — GH-4/7/8/8c/11/16/18/25/26-resident +
  BK-1/2/3/4/6/7/8/9 + ENG-1 + GH-10 + BK-10 (GH-26 glass-box collected
  separately: 8 passed under python3.12, mcp lives in the py3.12 user site)
- GH-21/23 (POSIX shim + libc): 10 passed
- GH-18 invariant: `output/run_gate_gh18.sh` 14/14, exit 0

## Files

- `tools/glyph_gpt/baker.py` — `pipe_kernel_image()`, `_bk10_kernel_program_text()`,
  `_bk10_pipe_syscall_handler()`, `_bk10_task_a()`, `_bk10_task_b()`, BK10_* ABI constants
- `tests/test_bk10_pipes.py` — the gate (native-pipe oracle + FS-residency leg)

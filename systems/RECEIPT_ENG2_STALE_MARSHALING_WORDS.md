# RECEIPT — ENG-2: BK-3 stale marshaling words in `:__kdone`

**Date:** 2026-09-11 · **Builder:** cron af3e62239ce2 · **Ticket:** `.builder_queue/ENG-2_bk3_unclear_sysret_mmio.json`

## Claim (from ticket, found during BK-4 join work)

BK-3's `signals.py :__kdone` tail zeroes word 8204 (SYS_N) but never 8205 (SYS_A0)
nor 8201 (SYSCALL_PC). Harmless in the landed BK-3 image only because every task
path HALTs before any further trap; any future BK-3 extension that traps after
kdone re-entry would read stale marshaling words. Gate clause: fold into the next
BK-3-touching edit; existing 5/5 gate stays green **unchanged**.

## RED (pre-fix) — `output/eng2_red_stale_words.txt`

BK-3 kill image, post-HALT, clean run (`halted=True faulted=False`):

| word | meaning | value | state |
|---|---|---|---|
| 8201 | SYSCALL_PC | `0x1f0005` (2031621) | **STALE — claim confirmed** |
| 8204 | SYS_N | 0 | zeroed by `:__kdone` |
| 8205 | SYS_A0 | 0 | zeroed (handler-registration path only, incidental) |

## Fix — `tools/glyph_gpt/signals.py`, `:__kdone` tail (kernel-side, zero engine changes)

Fold-in per ticket spec: alongside the existing 8204 store, zero 8205 and 8201.
`join.py` re-points 8201 by design (its mechanism, untouched); in BK-3's image
there is no consumer left at HALT, so zero is the honest reset. No gate test
modified (verified: no test asserts 8201/8205 in `test_bk3_signals.py` or
`test_bk4_join.py`).

## GREEN (post-fix) — `output/eng2_green_stale_words.txt`

Both image variants post-HALT: `8201=0 8204=0 8205=0`, `halted=True faulted=False`.

- **Gate (unchanged):** `tests/test_bk3_signals.py` 5/5
- **Arc regression:** GH-7/16/18 + BK-1/2/3/4 **42 passed in 10.02s**
  (`output/eng2_regress_arc.txt`)

## Notes

- Ticket proposed gate text said "existing 5/5 gate must stay green unchanged" —
  satisfied; the fix adds 4 kernel instructions to the done tail only.
- Wordbase/broader-suite collection errors pre-exist this change (missing
  optional deps in cron venv); arc-targeted run is the established gate.

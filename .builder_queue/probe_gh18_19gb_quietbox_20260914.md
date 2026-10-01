# DEFECT-22E — third quiet-box re-measurement (2026-09-14, cron af3e62239ce2)

Probe series purpose: the ticket's own `next` field asks for a repeat measurement
before the ~1.9 GB class is treated as real. Jericho treats n=1 as a coin flip,
so each tick adds one quiet-box data point until the pick is made.

## Conditions

- HEAD: `e213c8e` (clean tree, zero tracked-dirty)
- Box: quiet (no concurrent builds, no other lanes active)
- Command: `/usr/bin/time -v /usr/bin/python3 -m pytest tests/test_gh18_syscall_abi.py -q`

## Result

- **Max RSS: 748.2 MB** (730.2–746.9 MB across the 2026-09-13 series — consistent)
- **15 passed** (pytest tail pasted: `15 passed in 3.51s`), exit 0

## Verdict

Third consecutive quiet-box reading in the 0.73–0.75 GB band, ~3.5× below the
2026-09-13 12:55 sweep's 2.65 GB reading. The measured-negative attribution
(CONDITION, not CODE) now stands on **n=3 at three different HEADs**
(`e1c7620`, `b53d72d`, `e213c8e`), all quiet-box. The ~1.9 GB transient remains
unreproduced.

Ticket status stays OPEN — release of the level trigger is Jericho's pick
(renew supply / accept as documented stability bound / re-point the cron).

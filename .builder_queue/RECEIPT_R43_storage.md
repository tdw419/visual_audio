# RECEIPT — R4.3 Storage: block device with the writeback contract, ENOSPC-safe

Runger: PRODUCT_ROADMAP.md:75 (R4.3), Phase P4 (Drivers and device reality).
Builder: af3e62239ce2, 2026-09-21 ~18:0x CDT. HEAD at start: c927796f.

## Deliverable

- `.builder_queue/probe_r43_storage.py` — the whole mechanism: a HOST-SIDE
  block-device seat built over LANDED substrate channels only (mailbox ABI +
  GlyphCPUv2 CPU oracle). Zero production lines changed.
- `tests/test_r43_storage.py` — the gate (5 legs).

## Contract (what the probe enforces)

- **Request mailbox** (word addresses, plain-RAM region 3100+, no production
  words): BLK_CMD 3100 (1=WRITE/2=READ/3=FLUSH), BLK_SECTOR 3101,
  BLK_STATUS 3102 (0=OK/1=ENOSPC/2=E_IO), BLK_DATA0 3108. Guest posts
  SECTOR+DATA first, CMD last; the seat services any nonzero CMD between
  step() calls and clears it; guest polls bounded (r10 budget, R1.1
  discipline).
- **Writeback contract**: WRITE lands in the seat's dirty cache ONLY. The
  backing file (`GBD1` header | 8 sectors × 16 words + per-sector sum
  checksum) is written ATOMICALLY (tmp + `os.replace`, the R3.2 container
  pattern) on FLUSH and on clean-halt unmount. `--no-flush` proves the
  contract load-bearing: with the writeback skipped, the backing file never
  appears and the persistence check rejects.
- **ENOSPC-safe**: capacity is N_BLOCKS=8 sectors BY CONSTRUCTION (the
  contract is tested, not the host disk). A WRITE to sector 8 returns
  STATUS=1 (ENOSPC); the guest logs it and CONTINUES; committed sectors are
  untouched. Honest note: /home measured at 98% full this tick — the rung's
  own named hazard — which is exactly why capacity was modeled in-contract
  rather than relying on real disk headroom.
- **Torn-write detection**: per-sector checksum (sum & 0xFFFFFFFF); a single
  flipped byte in a committed sector is rejected.

## Evidence (all runs this session, true exits via file redirection)

RED first, all three legs discriminating, then GREEN:

```
$ python3 .builder_queue/probe_r43_storage.py --no-flush        # exit 1
R4.3 seat serviced {'write': 6, 'read': 1, 'flush': 2, 'enospc': 1} in 523 steps; halted=True committed=0
R4.3 no-flush RED leg: the seat skipped the writeback and the persistence check REJECTED (data loss detected): backing file MISSING — writeback never persisted

$ python3 .builder_queue/probe_r43_storage.py --torn-block      # exit 1
R4.3 torn-block RED leg: the flipped byte REJECTED by the sector checksum (torn write detected): torn write: sector 3 checksum 0x44440008 != 0x4444ff08

$ python3 .builder_queue/probe_r43_storage.py --corrupt-verify  # exit 1
R4.3 corrupt-verify RED leg: verifier REJECTED the good run under wrong expectations (correct discrimination): status log [...] != [90, 346, ...]

$ python3 .builder_queue/probe_r43_storage.py                   # exit 0
R4.3 seat serviced {'write': 6, 'read': 1, 'flush': 2, 'enospc': 1} in 523 steps; halted=True committed=6
R4.3 STORAGE: MATCH (6 sectors persisted, checksums valid, read-back word-exact, ENOSPC surfaced cleanly ...) — block device with the writeback contract, ENOSPC-safe, host-verified
```

GREEN: exit 0 (/tmp/r43_green.log); RED1 no-flush exit 1 (/tmp/r43_red1.log);
RED2 torn-block exit 1 (/tmp/r43_red2.log); RED3 corrupt-verify exit 1
(/tmp/r43_red3.log).

Gate:
```
$ python3 -m pytest tests/test_r43_storage.py -q
5 passed in 0.46s
```
(3 subprocess RED/GREEN exit-contract legs + corrupt-verify + in-process
atomic-writeback stale-.tmp leg.)

Lane regression:
```
$ python3 -m pytest tests/test_r41_input_mailbox.py tests/test_r42_display_frame.py tests/test_box_abi_conformance.py tests/test_glyph_run.py tests/test_gh26_fleet.py -q
33 passed in 9.70s
```

## Defects found and fixed in this rung (recorded, not hidden)

1. **Log-addressing dead instruction** (guest program): the log-append
   sequence loaded LOG_BASE (3300) into `r4` but the following `ADD r7 r9`
   uses `r7` — so the base register still held 3296 (LOG_COUNT), and job 0's
   log entry OVERWROTE the count word. Caught by the first --no-flush run
   failing for the WRONG reason (malformed log, not missing backing file) —
   the no-flush RED fired, but a RED for the wrong reason is a defect, not a
   pass. Fixed (`LDI r7 3300`), all three legs re-run and re-verified to
   reject for their stated reasons.
2. Dead code in the probe (`cpu.halted_ok` attribute access, dead
   conditional in the sector packer) — caught by lint before first run.

## What PASS does NOT prove (honesty)

- **No real block hardware.** The device channel is the mailbox ABI + a host
  file — not virtio-blk, not a disk driver.
- **NO WGSL shader-path leg.** Request servicing needs a per-step host hook;
  `run_wgsl` executes to HALT in ONE call (the same measured gap R4.1
  recorded).
- **No filesystem.** Raw block layer only — no names, no directories, no
  allocation bitmap.
- **One word per sector exercised** (DATA0); a full 16-word sector payload
  is the same loop with more guest stores, not a new mechanism.
- **Capacity is in-contract, not physical.** ENOSPC is tested against the
  device's own 8-sector geometry, not against the host filesystem filling up.
- **No rate claims** — nothing here quotes a rate → floors/check_regime N/A.

## Scope

Changed: `.builder_queue/probe_r43_storage.py` (new),
`tests/test_r43_storage.py` (new, force-added past .gitignore test_*.py),
`.builder_queue/RECEIPT_R43_storage.md` (this file),
`.builder_queue/PRODUCT_LANE_STATE.md` (ledger). Zero production lines.

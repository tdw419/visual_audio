# TICKET SUPPLY STATE — ADDENDUM 328 (2026-09-20 ~00:1x CDT, cron af3e62239ce2)

## Trigger: first FROZEN_STALLED_T1 fire of this chain

Monitor fingerprint: `8bdf921c` DIRTY_ACTIVE (17 dirty) → `8bdf921c` FROZEN_STALLED_T1.
Same head, no commits since addendum 327 (22:48). The transition is the stall
detector reacting to dirty-file mtimes aging past 30 min.

## Disposition: DEFER, do not adopt (three-way rule, EVENT_DRIVEN_BUILDER_LOOP.md:157)

Adoption was evaluated against the actual dirty set before being rejected:

- **Actively dirty right now:** `.pxc1_delta.jnl` (00:07:27) and
  `.hermes_guest_context/guest_state.json` (00:07:26) — written at tick time by
  the LIVE guest: `pgrep` confirms virtio_pixel_backend (pid 1419146) +
  qemu-system-x86_64 q35 6G (pid 1419204, hostfwd :2222, 9p host_zion) up
  against `ubuntu_desktop_pxc1_v3_selfhost/`. The tracked frame_00xxx.png churn
  (2896 dirty paths incl. frames ballooning to 67MB) is backend journal/frame
  I/O, not builder work.
- **No abandoned increment:** newest non-churn dirty file is 19:34 (Qoder-lane
  `bm902_diff_receipt.txt`); newest tooling/source dirt is 2026-09-17. Nothing
  in the PS-lane write set (tools/pyshader_*, tests/test_pyshader_*) is dirty.
  Nothing to adopt.

Class note for future ticks: with the PXC1 guest running, this tree can go
FROZEN_STALLED on daemon churn alone. Discriminator used here: (1) is anything
in the lane's own write set dirty, (2) is the newest non-churn mtime a builder
artifact, (3) is a guest backend process live. If all three say churn → defer,
never stash (stashing would eat live guest frames — adoption-not-erasure
applies with extra force here).

## Supply: unchanged from addendum 327

- HEAD still 8bdf921c; no new commits, rulings, or tickets since 22:48.
- PS007 ✅ PS008 ✅ landed; PS009 next but ineligible x2 (J-DECISION-reserved +
  REPAIR_PENDING_ps008_branch_convention_vs_ps007.md OPEN, Jericho's call).
- Re-measured this tick: `pytest tests/test_pyshader_fde.py tests/test_pyshader_ctl.py -q`
  → **29 passed**, exit 0. Landed tree still green.
- scan_open_rows OPEN_COUNT=1 (SUITE-FIX-1 leg 1b, BLOCKED-ON-DESIGN, ineligible).
- SE021 ~90th hold BLOCKED-ON-JERICHO.

## Jericho's unblock (unchanged, one decision)

Branch-offset convention for PS007 `execute_one`: (a) keep `pc+1+imm//4`, or
(b) spec `pc+imm//4` (ticket recommendation; matches PS008 + pixel CPU + QEMU).
Two-word answer releases PS009 (the data-generating part; the ≥5x fork stays reserved).

## Not verified this tick

- Substrate teleop read not repeated (addendum 326: md5 3744eaa7 byte-identical,
  tick=0; no PS row touches the canvas).
- PS005 compiler suite (part of the 78/78 historical claim) not re-run this tick;
  only fde+ctl (29/29) re-measured.

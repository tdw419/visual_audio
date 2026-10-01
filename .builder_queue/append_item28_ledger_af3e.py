#!/usr/bin/env python3
"""af3e item-28 landing: sync QUEUE_STATE.json + CURRENT_TICKET.json,
append the ledger entry, commit. Append-count asserted == 1."""
import json, subprocess, sys, os

REPO = "/home/jericho/projects/zion/projects/visual_audio"
WT = "/home/jericho/zion/worktrees/item28-rootinit"

# 1) QUEUE_STATE.json — item-28 -> landed (run in MAIN tree; canonical)
qs_path = os.path.join(REPO, ".builder_queue/QUEUE_STATE.json")
qs = json.load(open(qs_path))
n = 0
for item in qs["queue"]:
    if item["id"] == "item-28" and item["status"] != "landed":
        item["status"] = "landed"
        item["blocks_on"] = []
        n += 1
qs["active"] = None
qs["updated"] = "2026-09-26T07:40:00-05:00"
qs["updated_by"] = "builder af3e62239ce2 (item-28 landed, item-29 unblocked)"
json.dump(qs, open(qs_path, "w"), indent=2)
assert n == 1, f"item-28 status updates = {n}, expected 1"

# 2) CURRENT_TICKET.json
ct = {
    "ticket": "item-28",
    "title": "Spatial root init (ext2 PNG root mount and PID 1 startup sequence)",
    "status": "landed",
    "blocker": None,
    "defect_status": "DEFECT-32 found + fixed in tools/glyph_vfs.py sync() "
                     "(debugfs mkdir on existing dir orphans inode; "
                     "reboot-write-reboot through a subdir was impossible)",
    "worktree": "~/zion/worktrees/item28-rootinit (21201b56, cherry-picked "
                "to main as a220b26b)",
    "attempt": 1,
    "gate": "tests/test_item28_root_init.py (8 legs: B1-B4, P1, R1-R3; "
            "B4 = DEFECT-32 regression; R2/R3 = migration re-runs of "
            "item-25/26 gates)",
    "last_gate_result": "GREEN: 8 passed in 67.78s (worktree 21201b56) and "
                        "40 passed in 142.29s on main at a220b26b "
                        "(+item25+item26+png_vfs+box_abi), exit 0. "
                        "RED-first: gate file absent -> pytest exit 4. "
                        "Mid-fix RED: P1 DID NOT RAISE -> boot() now "
                        "refuses reused Kernel. Non-vacuity probe "
                        "(dbg_item28_nonvacuity_af3e.py): N1 unguarded-sync "
                        "-> B4 fails; N2 mount-check removed -> R1 fails.",
    "untrusted_probes": [],
    "notes": [
        "tools/glyph_root_init.py NEW: GlyphRootFs (format/mount, loud "
        "RootInitError on init-less roots), Kernel.boot (PID-1-first "
        "contract; init program FILE_WRITEs its argv boot record through "
        "the mounted root then EXIT 0), shutdown_sync (VFS-3 persistence), "
        "boot() one-liner",
        "DEFECT-32: debugfs -w mkdir on an EXISTING directory allocates+links "
        "a fresh inode then errors 'already exists' (rc 0) -> e2fsck -fn rc=4; "
        "landed unconditional mkdir broke reboot-write-reboot through any "
        "existing subdir (/etc/motd resync measured rc=-1, write lost); fix = "
        "stat-probe each segment, mkdir only missing (_image_dir_exists)",
        "ZERO new syscall numbers — no guest-visible ABI, twin contract "
        "untouched (TICKET_ITEM8 class avoided); engine byte-unchanged",
        "NOT proven: WGSL twin parity (host-side boot, item-27 shader-threat-"
        "model precedent); no GPU-image execution (Phase-2 doctrine); no "
        "multi-user init/runlevels/respawn; utmp placeholder; init program "
        "assembled host-side, guest-loaded binary init not claimed",
    ],
    "next_step": "Next claim by claim_order among unblocked: item-29 "
                 "(per-process spatial containment: bind GO-1 box "
                 "enforcement to spawn-allocated tiles; blocks_on cleared "
                 "by item-26 landing).",
    "updated": "2026-09-26T07:40:00-05:00",
    "updated_by": "builder af3e62239ce2 (item-28 landed)",
}
json.dump(ct, open(os.path.join(REPO, ".builder_queue/CURRENT_TICKET.json"), "w"), indent=2)

# 3) Ledger append (PRODUCT_LANE_STATE.md) — prepend new entry after header
ledger = os.path.join(REPO, ".builder_queue/PRODUCT_LANE_STATE.md")
text = open(ledger).read()
entry = """### 2026-09-26 ~07:4x CDT — CLAIM QUEUE item 28 (spatial root init: ext2 PNG root mount + PID 1 startup) LANDED; DEFECT-32 found + fixed (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD fba4494d (my item-27
  ledger lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0
  supply=claim item-28; QUEUE_STATE active=null, item-28 unblocked
  (blocks_on=[item-27] cleared); no RULING newer than HEAD. Claimed
  per Phase-1b (lowest claim_order unblocked).
- ADOPTED an abandoned partial patch in the item28 worktree (uncommitted
  edit at 06:36, no live process, no lane record): it referenced an
  _image_dir_exists helper that was never written — completed it as the
  DEFECT-32 fix below, after measuring the mechanism myself.
- DEFECT-32 (new, measured this tick, evidence chain in
  RECEIPT_item28_root_init.md): `debugfs -w -R mkdir` on an EXISTING
  directory allocates + links a fresh dir inode and only THEN errors
  "already exists" (rc 0) — e2fsck -fn rc=4 "Unconnected directory
  inode" (5/5 shell trials). The landed unconditional mkdir-per-segment
  in GlyphVfs.sync() broke the reboot-write-reboot cycle through any
  existing subdirectory: /etc/motd resync measured sync rc=-1 with the
  write LOST (probe dbg red v15). Item-25's gate missed it (L1 fresh
  disk, L3 root-level files — no existing-subdir mkdir). Note: a
  redundant mkdir followed by a successful write "settles" the orphan,
  which is why naive sync-level probes look clean; the fail case needs
  an existing file (rm+write) in an existing dir. Fix: stat-probe
  segments, mkdir only missing. Pinned by gate leg B4.
- LANDED (commit 21201b56 in worktree ~/zion/worktrees/item28-rootinit,
  cherry-picked to main as a220b26b after gates passed):
  - tools/glyph_root_init.py NEW — GlyphRootFs.format (ext2 1MiB root
    in the VFS-1 PNG transport, seeded /etc/hostname + /sbin/init +
    /var/run/utmp), GlyphRootFs.mount (loud RootInitError on init-less
    roots), Kernel.boot (PID-1-FIRST contract: first table spawn must
    be pid 1, reused Kernel refuses; init program SYSCALL 0x03-writes
    its argv boot record through the mounted root then 0x05 EXIT 0),
    shutdown_sync (VFS-3 persist), boot() one-liner.
  - Gate: tests/test_item28_root_init.py (force-added past .gitignore)
    — 8 legs. GREEN 8 passed in 67.78s (worktree 21201b56) and 40
    passed in 142.29s (main a220b26b, incl. item25+item26+png_vfs+
    box_abi re-gates), exit 0. RED-first: gate file absent -> pytest
    exit 4 (output/item28_gate_run0_absent_red.txt). Mid-fix RED,
    disclosed: P1 DID NOT RAISE (second boot allowed on same Kernel ->
    init pid would not be 1); boot() now refuses — enforcement added,
    no guard weakened. Non-vacuity (dbg_item28_nonvacuity_af3e.py,
    rc=0): N1 guard removed -> B4 fails; N2 mount-check removed -> R1
    fails. Gate proven able to fail at the implementation level.
  - ZERO new syscall numbers; engine byte-unchanged (TICKET_ITEM8
    twin false-success class structurally avoided).
- Honesty (rule 6): all asserts structural — no rates/latencies, rule-1
  floors do not attach; check_regime not implicated. NOT verified: no
  WGSL twin parity (host-side boot, shader-threat-model precedent per
  item-27); no GPU-image execution (Phase-2 doctrine); no multi-user
  init (single PID 1, no runlevels/respawn; utmp placeholder); init
  program assembled host-side — a guest-loaded binary init is NOT
  claimed; DEFECT-32's write-fails-after-redundant-mkdir corner argued
  from the landed pre-wrap e2fsck refusal, not probed.
- Queue state: QUEUE_STATE.json item-28 -> landed, item-29 unblocked;
  CURRENT_TICKET.json reconciled. Next tick: claim item-29
  (per-process spatial containment: bind GO-1 box enforcement to
  spawn-allocated tiles). REPAIR_PENDING_BK27_L5 unchanged (holds;
  sign-off change).

"""
marker = "STATUS: ACTIVE\n"
idx = text.index(marker) + len(marker)
new_text = text[:idx] + "\n" + entry + text[idx:]
open(ledger, "w").write(new_text)
assert open(ledger).read().count("CLAIM QUEUE item 28 (spatial root init") == 1

print("ledger+queue+ticket updated OK")

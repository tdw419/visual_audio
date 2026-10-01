#!/usr/bin/env python3
"""af3e item-27 landing sync: QUEUE_STATE + CURRENT_TICKET + ledger prepend.

Same pattern as append_item26_ledger_af3e.py (the established landing
sync). Run from repo root: python3 .builder_queue/append_item27_ledger_af3e.py
"""
import json
from pathlib import Path

BQ = Path(".builder_queue")

# ── QUEUE_STATE.json ──
qs_path = BQ / "QUEUE_STATE.json"
qs = json.loads(qs_path.read_text())
for item in qs["queue"]:
    if item["id"] == "item-27":
        item["status"] = "landed"
        item["blocks_on"] = []
qs["updated"] = "2026-09-26T07:15:00-05:00"
qs["updated_by"] = "builder af3e62239ce2 (item-27 landed)"
qs_path.write_text(json.dumps(qs, indent=2) + "\n")

# ── CURRENT_TICKET.json ──
ct_path = BQ / "CURRENT_TICKET.json"
new_ct = {
    "ticket": "item-27",
    "title": "Driver ABI freeze (unified contract for Mailbox, Console, and Block channels)",
    "status": "landed",
    "blocker": None,
    "defect_status": None,
    "worktree": "~/zion/worktrees/item27-driverabi (91ce8e78, cherry-picked to main as ba9a302a)",
    "attempt": 1,
    "gate": "tests/test_item27_driver_abi.py (10 legs: M1-M2 mailbox, C1-C2 console, B1-B2 block, U1 unification, R1-R3 corrupt-expectation RED)",
    "last_gate_result": (
        "GREEN: 10 passed in 0.22s (worktree 91ce8e78) and 0.25s (main tree "
        "ba9a302a, post-cherry-pick re-gate), exit 0. RED first: gate file "
        "absent -> pytest exit 4 (output/item27_gate_run0_absent_red.txt); "
        "mid-fix REDs: C1 trailing-space (decode rstrips), B1 wrong layer "
        "(disk == unwrap() output, not PNG bytes), B2 wrong corruption byte "
        "(magic lives at pixel (0,0) red channel). In-suite non-vacuity "
        "R1/R2/R3 corrupt-expectation legs. Adjacent re-gate: item25+item26+"
        "png_vfs+box_abi conformance 32 passed in 73.09s."
    ),
    "untrusted_probes": [],
    "notes": [
        "docs/DRIVER_ABI_v1.md NEW: the unified channel freeze — MAILBOX "
        "(BOX_ABI_v2 s4 verbatim: GH-22 word, check vector 0x3B00112A, "
        "frozen receipts), CONSOLE (DTF-2 glass-TTY: 8x16 cell, strict "
        "two-color decode, text->pixels->text byte-exact), BLOCK (VFS-1: "
        "28B header PVFSIMG1/RGB24/Hilbert, loud failures). Change policy "
        "inherited from BOX_ABI_v2: frozen fields need a major bump.",
        "Gate U1 = the unification proof: ONE GlyphVfs attached to TWO "
        "spawned engines (item-26 vfs_shared pattern) — A 0x03-write -> B "
        "0x04-read byte-exact, no host-FS file",
        "ZERO new syscall numbers — no guest-visible ABI added, twin "
        "contract untouched (TICKET_ITEM8 class avoided)",
        "NOT proven: WGSL twin parity (console render host-side, block "
        "channel host e2progs — out of the shader threat model, "
        "0x07/0x12/0x13 normative-negative precedent); no rate/floor "
        "claims (nothing timed); no silicon device model; LD read-isolation "
        "unaffected (BOX_ABI_v2 s7)",
    ],
    "next_step": (
        "Next claim by claim_order among unblocked: item-28 (spatial root "
        "init: ext2 PNG root mount + PID 1 startup; unblocked by item-27). "
        "item-29 (per-process spatial containment) also unblocked but "
        "claim_order sits behind 28."
    ),
    "updated": "2026-09-26T07:15:00-05:00",
    "updated_by": "builder af3e62239ce2 (item-27 landed)",
}
ct_path.write_text(json.dumps(new_ct, indent=2) + "\n")

# ── PRODUCT_LANE_STATE.md: prepend ledger entry ──
ledger = BQ / "PRODUCT_LANE_STATE.md"
text = ledger.read_text()
lines = text.split("\n")
entry = """### 2026-09-26 ~07:1x CDT — CLAIM QUEUE item 27 (driver ABI freeze: unified Mailbox/Console/Block contract) LANDED (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD 16c285fe (my item-26
  ledger lineage); tracked tree CLEAN; monitor CLAIM_PENDING queue=0
  supply=claim item-27; QUEUE_STATE active=null, item-27 unblocked;
  no RULING newer than HEAD (only DOGFOOD_GPU_OS_* refreshed, 7/7
  healthy 05:50). Claimed per Phase-1b claim-queue-first (lowest
  claim_order unblocked).
- LANDED (commit 91ce8e78 in worktree ~/zion/worktrees/item27-driverabi,
  cherry-picked to main as ba9a302a after gates passed):
  - docs/DRIVER_ABI_v1.md NEW — the unified channel freeze: MAILBOX
    (BOX_ABI_v2 s4 verbatim: GH-22 word format, canonical check vector
    0x3B00112A, frozen receipts 0x5EED0003/4/5 + 0xFA026 + 0xCAFE0026 +
    ABI 0x00020026); CONSOLE (DTF-2 glass-TTY: 8x16 VGA cell, band
    rows*16 x cols*8, strictly two colors, strict decode raises on a
    third, text->pixels->text byte-exact); BLOCK (VFS-1: 28B header
    b"PVFSIMG1" / "<8sHHII8s" / RGB24 3B/px / Hilbert d2xy transport,
    loud PngVfsError on corrupt magic/version/short payload). Change
    policy inherited verbatim from BOX_ABI_v2 (frozen field change =>
    major bump + migration note; the gate enforces).
  - Gate: tests/test_item27_driver_abi.py (force-added past
    .gitignore) — 10 legs. GREEN 10 passed in 0.22s (worktree
    91ce8e78) and 0.25s (main tree ba9a302a, post-cherry-pick re-gate).
    RED first: gate file absent -> pytest exit 4
    (output/item27_gate_run0_absent_red.txt). In-suite non-vacuity
    R1/R2/R3 (corrupt-expectation legs). Mid-fix REDs, disclosed:
    C1 trailing-space mismatch (decode_band rstrips lines — contract,
    not bug); B1 asserted disk == PNG bytes (wrong layer — disk is
    unwrap() output; header decoded via decode_payload of the PNG);
    B2 flipped disk byte 0 instead of the canvas header magic (the
    magic lives at Hilbert offset 0 = pixel (0,0) red channel;
    test_png_vfs.py leg-3b pattern).
  - U1 unification leg: ONE GlyphVfs, TWO spawned engines (item-26
    GlyphProcessTable vfs_shared=True) — task A 0x03-writes
    /t27.txt, task B 0x04-reads byte-exact through the staged
    overlay; no host-FS file (VFS-2 contract intact).
  - ZERO new syscall numbers — no guest-visible ABI added, so the
    WGSL twin bridge false-success class (TICKET_ITEM8) is
    structurally avoided; no engine file touched.
- Adjacent re-gate at the worktree: item-25 + item-26 + png_vfs +
  box_abi conformance = 32 passed in 73.09s (exit 0).
- Honesty (rule 6): all asserts structural — no rates/latencies, rule-1
  floors do not attach; check_regime not implicated. NOT verified: no
  WGSL twin parity (console render is host-side, block channel is host
  e2progs — out of the shader threat model per the 0x07/0x12/0x13
  normative-negative precedent); no rate/floor claim (nothing timed);
  no silicon device model (GH-22 trusted-unproven boundary stands); LD
  read-isolation unaffected (BOX_ABI_v2 s7).
- Disk note: worktree add initially failed ENOSPC (/home 100%); two
  fully-merged stale worktrees removed (defect17-x31, go6-virtio-l1 —
  both tips verified ancestors of HEAD before removal) -> /home 97%,
  then add succeeded.
- Queue state: QUEUE_STATE.json item-27 -> landed, item-28 unblocked
  (blocks_on=[item-27] cleared); CURRENT_TICKET.json reconciled. Next
  tick: claim item-28 (spatial root init: ext2 PNG root mount + PID 1
  startup) by claim_order among unblocked. REPAIR_PENDING_BK27_L5
  unchanged (holds; sign-off change).

"""
# Find insertion point: after line 3 ("STATUS: ACTIVE") + blank line
out = lines[:4] + entry.split("\n") + lines[4:]
ledger.write_text("\n".join(out))
print("ledger/queue/ticket synced")

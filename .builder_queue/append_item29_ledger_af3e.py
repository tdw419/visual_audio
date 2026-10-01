#!/usr/bin/env python3
"""af3e item-29 landing: sync QUEUE_STATE.json + CURRENT_TICKET.json,
append the ledger entry to PRODUCT_LANE_STATE.md, write RECEIPT_item29.
Run in MAIN tree; canonical queue state lives here."""
import json
from pathlib import Path

Q = Path(".builder_queue")

# 1) QUEUE_STATE.json — item-29 -> landed
qs = json.loads((Q / "QUEUE_STATE.json").read_text())
n = 0
for item in qs["queue"]:
    if item["id"] == "item-29" and item["status"] != "landed":
        item["status"] = "landed"
        item["blocks_on"] = []
        n += 1
qs["updated"] = "2026-09-26T08:55:00-05:00"
qs["updated_by"] = "builder af3e62239ce2 (item-29 landed — CLAIM QUEUE EMPTY)"
assert n == 1, f"item-29 status updates = {n}, expected 1"
(Q / "QUEUE_STATE.json").write_text(json.dumps(qs, indent=2) + "\n")

# 2) CURRENT_TICKET.json — reconcile
ticket = {
    "ticket": "item-29",
    "title": "Per-process spatial containment (bind GO-1 box enforcement to spawn-allocated tiles)",
    "status": "landed",
    "blocker": None,
    "defect_status": None,
    "worktree": "~/zion/worktrees/item29-containment (cacb6449, cherry-picked to main as 59469d20)",
    "attempt": 1,
    "gate": "tests/test_item29_containment.py (10 legs: B1/B1b, B2, B3, B4, P5/P5b, R1, R2, N1 engine-byte guard)",
    "last_gate_result": (
        "GREEN: 10 passed in 34.68s (pre-commit, worktree f94ee177+impl) and 33.81s "
        "(post-commit cacb6449); post-cherry-pick re-gate on main at 59469d20: 42 passed "
        "in 107.58s (= item29 gate + item26 + item25 + png_vfs + box_abi), exit 0. "
        "RED-first: implementation stashed -> collection error ModuleNotFoundError: "
        "tools.glyph_containment, 1 error in 0.08s. Non-vacuity "
        "(dbg_item29_nonvacuity.py): neutered fence (TILE_H=0 + MODE_SUPER restored) "
        "-> out-of-tile store LANDS 0xDEADBEEF at word 164, status 0 — B3 fires; gate "
        "is discriminating."
    ),
    "untrusted_probes": [],
    "notes": [
        "tools/glyph_containment.py NEW: arm_tile (GO-2 tile words + MODE_USER drop, "
        "host-side before first instruction), wrap_with_reaper (tall COPY + HALT "
        "trampoline at col 0 row 30), DEFAULT_REAPER_ROW",
        "spawn(tile=, reaper_pc=, reaper_row=): the fence needs a catcher — the ST "
        "trap path vectors to KFAULT_PC UNCONDITIONALLY (glyph_isa_v2.py:1052-1056, no "
        "kf==0 branch), so KFAULT_PC==0 would trap to (0,0), restart in SUPER, and the "
        "re-executed store LANDS; tiled spawns always arm the reaper trampoline",
        "tile=None keeps the exact item-26 posture (MODE_SUPER, TILE_H==0) — "
        "byte-identical legacy behavior (B1b + R1 pin it)",
        "ZERO new syscall numbers; engine byte-unchanged — N1 leg pins "
        "tools/glyph_isa_v2.py as blob-identical to HEAD",
        "NOT proven: LD is not box-checked (write-only isolation, carried note); "
        "SUPER-mode stores never fenced (kernel immunity by design); no GPU-image "
        "execution (host CPU engine, Phase-2 doctrine); no preemption/timer yield; "
        "the cannot-re-arm-own-fence claim is argument, not proof, for every future "
        "program shape; WGSL twin untouched (host-side arming)"
    ],
    "next_step": "CLAIM QUEUE EMPTY (items 1-29 resolved). Lane returns to supply-wait "
                 "or Phase-1c research on next tick per the empty-queue rules.",
    "updated": "2026-09-26T08:55:00-05:00",
    "updated_by": "builder af3e62239ce2 (item-29 landed)",
}
(Q / "CURRENT_TICKET.json").write_text(json.dumps(ticket, indent=2) + "\n")

# 3) RECEIPT
receipt = """# RECEIPT — item-29: per-process spatial containment (spawn-allocated tiles)

**Builder:** af3e62239ce2 · **Date:** 2026-09-26 ~08:5x CDT
**Worktree commit:** cacb6449 (item29-containment, base f94ee177) · **Main cherry-pick:** 59469d20
**Claim basis:** Phase-1b claim-queue-first, lowest claim_order unblocked
(item-29, blocks_on=[item-26] cleared two ticks ago).

## What landed

- `tools/glyph_containment.py` NEW (119 lines):
  - `arm_tile(cpu, (row,col,h,w))` — writes the GO-2 tile words
    (TILE_ROW/COL/H/W at BOX_MMIO_BASE+0x160..0x16C) in the task's own
    RAM and drops the engine to MODE_USER. Host-side Python stores,
    before the task's first instruction — no ordering hazard. Zero- or
    negative-extent tiles REFUSED (ContainmentError): TILE_H==0 is the
    engine's "inert" encoding, and refusing it means no caller can ask
    for USER mode while silently unfenced.
  - `wrap_with_reaper(image, row, om)` — a TALL COPY of the program
    image with a HALT planted at (col 0, row 30). The copy is
    deliberate: the table never mutates the image a caller passed.
- `tools/glyph_process.py` +58/-2: `spawn(tile=, reaper_pc=,
  reaper_row=)`. tile=None keeps the exact item-26 posture (MODE_SUPER,
  TILE_H==0, byte-identical legacy behavior — B1b + R1 pin it).
- Gate: `tests/test_item29_containment.py` (10 legs, force-added past
  .gitignore): B1/B1b arming contract + inert-super migration, B2
  in-tile store lands, B3 out-of-tile traps + store never lands, B4
  reaper vector + offender-reaped/neighbor-clean, P5 boundary
  semantics (last-in lands at word 195, first-out faults at word 164),
  P5b zero-extent refusal, R1 item-26 contract re-run, R2 item-26 gate
  subprocess re-run, N1 engine-byte guard.

## THE FENCE NEEDS A CATCHER (design finding, measured)

The E-K1 ST trap path vectors to KFAULT_PC UNCONDITIONALLY
(glyph_isa_v2.py:1052-1056 — unlike the LD/PTE paths there is no
kf==0 "disabled" branch). A tile armed with KFAULT_PC==0 traps to
(0,0): the engine restarts the program in SUPER mode, re-executes the
offending store UNCHECKED, and it LANDS. The fence would hold on the
first attempt and silently fail on re-execution. dbg_item29_kf0*.py
probes pinned this; dbg_item29_cases.py enumerates the four
(tile x reaper) spawn shapes. Fix baked into the API: a tiled spawn
ALWAYS arms a reaper trampoline (caller's reaper_pc or the default).

## Gate evidence (RED first, then GREEN)

- RED-first: implementation stashed (`git stash push -u
  tools/glyph_containment.py`) -> collection ERROR,
  `ModuleNotFoundError: No module named 'tools.glyph_containment'`,
  1 error in 0.08s. Restored -> full GREEN.
- GREEN: 10 passed in 34.68s (worktree, pre-commit) and 33.81s
  (post-commit cacb6449). Post-cherry-pick re-gate on main at
  59469d20: **42 passed in 107.58s** = item29 (10) + item26 (8) +
  item25 (8) + png_vfs + box_abi conformance, exit 0.
- Non-vacuity (`dbg_item29_nonvacuity.py`): the arming store neutered
  (TILE_H zeroed + MODE_SUPER restored after arm) -> out-of-tile store
  LANDS 0xDEADBEEF at word 164 with status 0 — B3's breach assert
  fires. The gate is discriminating at the implementation level.
- Migration: test_item26_process.py + test_item25_vfs.py = 16 passed
  in 67.06s unmodified in this tree.

## Honesty (rule 6) — what the PASS does NOT prove

- All asserts structural (words, modes, statuses, fault registers,
  blob hashes) — no rates/latencies, rule-1 floors do not attach;
  check_regime not implicated.
- LD is NOT box-checked (write-only isolation — the honesty note
  carried from R1.2/BOX_ABI_v2 s2 applies unchanged).
- SUPER-mode stores are never fenced (kernel immunity by design); the
  box words live in task RAM by GO-1 architecture. The claim "a task
  that never exits USER mode cannot re-arm its own fence" is ARGUMENT
  from the landed mode-transition enumeration (trap/KJMP/SYSRET/tick),
  not proof for every future program shape.
- No GPU-image execution: host CPU engine (GlyphCPUv2), Phase-2
  doctrine. WGSL twin untouched — host-side arming, zero new syscall
  numbers, engine file byte-unchanged (N1 pins the blob hash).
- No preemption, no timer-yield between tasks, no kernel image: the
  reaper trampoline is a table-owned HALT row, not a guest kernel.
- Containment is per-task-RAM: two tasks' RAMs were already disjoint
  (item-26); item-29 fences a task against ITS OWN RAM plane (its
  program window, stack, VFS staging arguments), not against other
  engines' memory.

## Files touched (git scope check done)

- NEW tools/glyph_containment.py, tests/test_item29_containment.py;
  MODIFIED tools/glyph_process.py. Nothing else. Engine
  (tools/glyph_isa_v2.py) byte-unchanged — asserted in-gate by N1.
"""
(Q / "RECEIPT_item29_containment.md").write_text(receipt)

# 4) Ledger entry
entry = """

### 2026-09-26 ~08:5x CDT — CLAIM QUEUE item 29 (per-process spatial containment: GO-2 tiles bound to spawn) LANDED; CLAIM QUEUE NOW EMPTY (builder af3e62239ce2)

- Provenance re-verified at tick start: HEAD f94ee177 (my item-28
  ledger lineage); tracked tree CLEAN (only the Qoder lane's untracked
  BM000/DOGFOOD artifacts, untouched); monitor CLAIM_PENDING queue=0
  supply=claim item-29; QUEUE_STATE active=null, item-29 unblocked;
  no RULING_* newer than HEAD. Claimed per Phase-1b.
- ADOPTED an in-flight worktree: ~/zion/worktrees/item29-containment
  had an uncommitted implementation (glyph_containment.py + spawn
  extension + 288-line gate, mtimes 08:16-08:17, no live process, no
  lane record). Verified it against the spec myself before adopting:
  read the GO-2 tile predicate (glyph_isa_v2.py:734-747) and the E-K1
  ST trap path (:1041-1056), re-ran the 10-leg gate GREEN, ran the
  non-vacuity probe myself, then stashed/RED-first-proved and
  committed as cacb6449.
- Design finding baked in (THE FENCE NEEDS A CATCHER): the ST trap
  path vectors to KFAULT_PC UNCONDITIONALLY — a tile armed without a
  reaper would trap to (0,0), restart in SUPER, and the re-executed
  store would LAND. Tiled spawns always arm the trampoline.
- Gate: tests/test_item29_containment.py — 10 legs. RED-first
  (implementation stashed -> ModuleNotFoundError at collection).
  GREEN 10 passed in 34.68s / 33.81s; post-cherry-pick main re-gate
  at 59469d20: 42 passed in 107.58s (+item26+item25+png_vfs+box_abi),
  exit 0. Non-vacuity: neutered fence -> B3 breach assert fires.
- ZERO new syscall numbers; engine byte-unchanged (N1 blob-hash guard
  in-gate). tile=None keeps the exact item-26 posture (B1b + R1).
- Honesty (rule 6): all asserts structural — no rates/latencies,
  rule-1 floors do not attach. NOT verified: LD not box-checked
  (carried note); SUPER-mode stores never fenced; no GPU-image
  execution; the cannot-re-arm-own-fence claim is argument, not
  proof, for every future program shape; WGSL twin untouched.
- Queue state: QUEUE_STATE.json item-29 -> landed. **CLAIM QUEUE IS
  EMPTY** (items 1-29 all resolved). CURRENT_TICKET.json reconciled;
  next_step = supply-wait or Phase-1c research per empty-queue rules.
  REPAIR_PENDING_BK27_L5 unchanged (holds; sign-off change).
"""
led = Q / "PRODUCT_LANE_STATE.md"
led.write_text(led.read_text().replace(
    "## Session log",
    "## Session log\n" + entry, 1))

print("item-29 landing synced: queue/ticket/ledger/receipt written")

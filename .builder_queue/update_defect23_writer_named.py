#!/usr/bin/env python3
"""Tick artifact, 2026-09-13 14:2x CDT (builder cron af3e62239ce2).

Appends the UPDATE section to `.builder_queue/REPAIR_PENDING_defect23_paged_flat_memory.md` and
records the same findings in the ticket `.builder_queue/DEFECT-23_paged_flat_memory_growth.json`.
Idempotent: re-running does not duplicate the section.
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOTE = ROOT / ".builder_queue" / "REPAIR_PENDING_defect23_paged_flat_memory.md"
TICKET = ROOT / ".builder_queue" / "DEFECT-23_paged_flat_memory_growth.json"

MARKER = "## UPDATE 2026-09-13 14:2x — the writer is NAMED, and it is an arming-loop typo"

SECTION = """
## UPDATE 2026-09-13 14:2x — the writer is NAMED, and it is an arming-loop typo

**Filed by:** builder cron `af3e62239ce2`, same tick. **This answers option 1's prerequisite and
reclassifies the ticket from "policy decision" to "one-line bake fix awaiting sign-off".**

**Probe (this tick):** `.builder_queue/probe_defect23_pt_slot_writer.py` →
`output/probe_defect23_pt_slot_writer_2026091314.json` (pre-fix / main tree) and
`output/probe_defect23_pt_slot_writer_2026091314_worktree_fixed.json` (fix present).

**Q1 answered — the words are written at RUN TIME, not stamped by the bake.** RAM 1538/1539 read
`0` before any instruction retires in **all three** modes (`baseline`, `admit`, `paged_dispatch`);
no image pixel carries their 24-bit triple either (zero hits in both)). The writer is kernel code
at **pixel pc (16,11), MODE_SUPER**, at steps **181, 195, 209, 223, 237, 251, 265, 279** — a
14-step cadence that matches the arming loop's instruction count exactly.

**Mechanism — `:__g18_ptloop`, `tools/glyph_gpt/baker.py:5210-5225`.** The loop's per-iteration
MOV is written as `ADD r14 r13` and **`r14` is never initialised**, so the "identity" PTE
accumulates:

    r14(n) = ((r14(n-1) << 8) | 7) + n        r14(-1) = 0x150001 (prologue leftover)

| slot | intended `(vpn<<8)|7` | measured pre-fix |
|---|---|---|
| 1536 | `0x007` | `0x15000107` |
| 1537 | `0x107` | `0x0010807` |
| 1538 | `0x207` | `0x01080907` | 
| 1539 | `0x307` | `0x08090A07` |
| 1540 | `0x407` | `0x090A0B07` |
| 1541 | `0x507` | `0x0A0B0C07` |
| 1542 | `0x607` | `0x0B0C0D07` |
| 1543 | `0x707` | `0x0C0D0E07` |

All eight observed values are reproduced **exactly** by that recurrence (arithmetic check this
tick), including the 32-bit truncation that turns `0x15000108 << 8` into `0x00010800`. So the
`pfn` values the walk later used (67,593 / 526,602 ⇒ 17.3M / 117.5M words) are not random
garbage: they are the *tail of an accumulator*, which is why the two growth events are ~7× apart.

**The bake is innocent and the intent is documented in-code.** The comment at
`baker.py:5198-5209` states the contract ("Arm the GH-17 page table with an identity map of the
low 8 pages… Identity PTEs are `(vpn << 8) | flags`"). The code fails its own comment. Compare the
**other** writer of this window: `admit` mode's per-slot arming (`baker.py:5155-5181`) writes
explicit constants and produces exactly `[0x7, 0x107, 0x207, 0x307, 0x407, 0x507, 0x50F, 0x707]`
(slot 6 = `(5<<8)|0xF`, the documented vpn-6 PIX remap). Measured this tick by
`tests/test_defect23_pt_identity.py::leg3`.

**Fix, verified in worktree isolation (AGENTS.md § Blast-Radius Containment):** branch
`defect23-ptloop-init` at `/home/jericho/zion/worktrees/defect23-ptloop`, commit **`6d8ab81`** —
one line, `LDI r14 0` before `ADD r14 r13`, plus a comment naming DEFECT-23, plus the new gate
`tests/test_defect23_pt_identity.py` (L1 falsifier / L2 non-vacuity / L3 discrimination).
**The main branch is untouched** — this is evidence, not a landing.

| leg | command (same on both trees, same instrument) | RED (main, pre-fix) | GREEN (worktree, fix) |
|---|---|---|---|
| gate | `python3 -m pytest tests/test_defect23_pt_identity.py -q` | **2 failed, 1 passed** (`slot 0 must be 0x7, got 0x15000107`) | **3 passed** |
| arc consumer | `/usr/bin/time -v python3 -m pytest tests/test_gh18_syscall_abi.py -q` | 14 passed, `Maximum resident set size: 2,350,292 kB` | 14 passed, `Maximum resident set size: 243,204 kB` |
| probe | `probe_defect23_pt_slot_writer.py` | 8 slots garbage, growth 17.3M then 117.5M words | slots `0x7…0x707`, **growth 0** over 380 steps |

Peak **2,350,292 kB → 243,204 kB (9.7×)**, wall 9.04 s → 3.85 s, 14/14 green on both sides.
Raw tails: `output/defect23_ptloop_gate_red.txt`, `output/defect23_ptloop_gate_green.txt`,
`output/defect23_gh18_main_prefix*.txt`, `output/defect23_gh18_worktree_postfix*.txt`.

**What the GREEN does NOT prove** (stated for the landing note): the WGSL twin is not re-derived;
non-identity maps are untested (this image has none); and **the engine's low-byte-only PTE
validity test is untouched** — option 2 remains un-hardened, so a future writer of `0x…07` into
the PT window is still accepted and still extends `memory` without bound. Option 1 removes the
observed trigger, not the class. Also NOT proven: that the fixed identity map leaves *every*
landed paged_dispatch receipt's status words unchanged — only `tests/test_gh18_syscall_abi.py`
(the one arc consumer named in the ticket) was re-run.

**Hazard found while producing this evidence (worth a line in the loop's discipline):**
`git stash` is **repo-global across worktrees**. A `git stash push <file>` inside a *linked*
worktree silently no-ops when that file is already committed, and the following `git stash pop`
then applies the stack's top entry — which may belong to another session or another branch.
That happened this tick: a pop dragged an unrelated `emulator-v2-baseline` stash into the
worktree (`UU` on three files). Recovered with `git reset --hard HEAD` in the worktree only; the
stash stack was verified intact (5 entries, top entry unchanged) and the correct RED was then
produced by checking out `6d8ab81~1 -- tools/glyph_gpt/baker.py` instead of stashing. No work
from any other session was lost, and the main tree was never touched by the pop.

**Requested decision (Jericho):** land `6d8ab81`'s one-line fix on `glyph-transpiler-autoloop`
(the gate and the branch are ready), or reject it. Option 2 (a pfn ceiling + named fault) is now
a separate, smaller question: with the arming loop fixed, the engine's unbounded extension has no
known live trigger — but it is still one bad word away.
"""


def main() -> int:
    text = NOTE.read_text(encoding="utf-8")
    if MARKER in text:
        print("note already carries the update; skipping append")
    else:
        NOTE.write_text(text.rstrip("\n") + "\n" + SECTION, encoding="utf-8")
        print(f"appended {len(SECTION)} chars to {NOTE.name}")

    d = json.loads(TICKET.read_text(encoding="utf-8"))
    d["writer_named"] = {
        "by": "builder cron af3e62239ce2, 2026-09-13 14:2x CDT",
        "kind": "runtime (NOT bake-stamped; slots read 0 pre-step in baseline/admit/paged_dispatch)",
        "site": "tools/glyph_gpt/baker.py:5210-5225 (:__g18_ptloop, mode paged_dispatch)",
        "pc": [16, 11],
        "mode": "MODE_SUPER",
        "steps": [181, 195, 209, 223, 237, 251, 265, 279],
        "mechanism": "MOV written as ADD with uninitialised r14 -> r14(n) = ((r14(n-1) << 8) | 7) + n, r14(-1)=0x150001; all 8 observed PTE values reproduced exactly",
        "probe": ".builder_queue/probe_defect23_pt_slot_writer.py",
    }
    d["option1_fix_candidate"] = {
        "classification_change": "typo-class bake defect, NOT an engine memory-model or fault-policy question (the loop contradicts its own documented contract, baker.py:5198-5209)",
        "branch": "defect23-ptloop-init (worktree /home/jericho/zion/worktrees/defect23-ptloop)",
        "commit": "6d8ab81",
        "diff": "+12 lines in tools/glyph_gpt/baker.py (LDI r14 0 + comment), +134 lines new gate tests/test_defect23_pt_identity.py",
        "gate": "python3 -m pytest tests/test_defect23_pt_identity.py -q -> RED 2 failed/1 passed pre-fix, GREEN 3 passed with fix",
        "measured": {"gh18_peak_kb_pre_fix": 2350292, "gh18_peak_kb_post_fix": 243204,
                     "wall_s_pre_fix": 9.04, "wall_s_post_fix": 3.85, "instrument": "/usr/bin/time -v"},
        "landed_on_main_branch": False,
        "awaiting": "Jericho sign-off to land 6d8ab81",
        "not_proven": ["WGSL twin not re-derived", "non-identity maps untested",
                       "engine low-byte-only PTE validity test untouched (option 2 still open)",
                       "only the one named arc consumer re-run"],
    }
    d["related_options_note"] = ("option 2 (pfn ceiling + named fault) and option 3 (sparse memory) "
                                 "change classification: with the arming loop fixed, option 2 has no "
                                 "known live trigger but still guards the class; option 3 remains a "
                                 "worktree-isolated round.")
    TICKET.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"ticket updated: {TICKET.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

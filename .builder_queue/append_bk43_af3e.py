#!/usr/bin/env python3
"""append_bk43_af3e.py — BK-43 bookkeeping: RESOLUTION tail on the GLYPH_BACKLOG
row + ledger session entry in PRODUCT_LANE_STATE.md. Idempotent by md5 check."""
import hashlib
from pathlib import Path

REPO = Path("/home/jericho/projects/zion/projects/visual_audio")
BACKLOG = REPO / "systems" / "GLYPH_BACKLOG.md"
LEDGER = REPO / ".builder_queue" / "PRODUCT_LANE_STATE.md"

RESOLUTION = (
    " **RESOLUTION (2026-09-30, builder af3e62239ce2, commit 359711b9 via branch "
    "bk43/run-path on the reused bk40-syscall worktree, merged fast-forward to "
    "mainline at HEAD 359711b9): the RUN path/argv fence guard LANDED (sequenced "
    "fence commit step 5) — (a) the PATH-target half of this row was already "
    "closed by BK-42's landed `_bk42_path_fault` (0x07/0x12 in "
    "`_BK42_PATH_SYSCALLS`): the probe's smuggle shape (in-tile '/tmp/run' NO "
    "NUL, out-of-tile tail 'r5r5\\\\0') now refuses at the dispatch site with "
    "`path_decode_fence` — the gate's L1 pins that landed guard (allowlist "
    "worst-case: both targets on GLYPH_RUN_ALLOW); (b) the ARGV half is NEW: "
    "`GlyphCPUv2._bk43_argv_fault(arg_addr)` consults 0x12 RUN2's argv windows "
    "(r2=arg1_addr, r3=arg2_addr) at the SYSCALL dispatch site BEFORE the "
    "handler runs, delegating to `_bk42_path_fault` (now tag-parametrized, "
    "default behavior byte-identical) with reason tag `argv_decode_fence`; "
    "addr==0 (RUN2's documented none-sentinel) admitted. Refusal = the landed "
    "E-K1 tail via _stack_fence_fault: handler never executes, out-of-tile RAM "
    "can no longer cross execve() as ARGV. Term set identical to every landed "
    "consult: USER + _tile_confinement + _iso_enabled + _addr_in_box; SUPER "
    "(E-K2 dispatch) and unfenced tasks untouched. Gate "
    "tests/test_bk43_run_path_fence.py 7/7 (L1 smuggle-refused pin, L2 "
    "argv-out-of-tile refusal w/ fault_addr=168*4 + no marker, L3 in-tile "
    "0x07/0x12 controls, L4 deny-by-default (rd==-1, no marker), L5 arg-0 "
    "admission + ST trap control, L6 non-vacuity (consult instance-shadowed, "
    "engine md5-pinned, ARG1=[SRC5] lands clean), L7 family BK-42/40/41/39). "
    "RED-first at landing (fix absent, /tmp/bk43_red3.log md5 "
    "7d8b27f2bc4b55c4a434596834e7be94, exit 1): L2 rc=0 clean, '[SYSCALL] RUN2: "
    "executed /tmp/r5 (1 args), exit code 0' — the exact measured defect; "
    "1 failed / 6 passed. Fix applied -> 7/7. GATE-DRAFT DEFECTS caught by the "
    "gate's own legs pre-landing, receipted in the test docstring: (1) L3 ARG "
    "staging at word 200 is OUT of tile (BK-42 run geometry) — first draft "
    "faulted write_arm_fence at word 200; moved to run (224..231); (2) L3 "
    "50-instruction program = 7-row image, and the PARALLEL_ST write-through "
    "pixel mirror maps staging word 192 to image row 6, CLOBBERING the "
    "SYSCALL/HALT at slots 48..55 (halted opcode-None at (0,6) before the "
    "syscall fired) — program shortened to 47 instructions; (3) L4 rd receives "
    "SIGNED -1, not 0xFFFFFFFF; (4) runner fixture needed a shebang. Family on "
    "the committed tree: BK-43 7/7 + fence family BK-39 11/11 + BK-40 8/8 + "
    "BK-41 10/10 + BK-42 7/7 + BK-48-twin 6/6 + BK-49 7/7 + invariants 3/3 "
    "(58 passed, 1 failed = item-29 test_n1 HEAD-pinned drift guard, RED BY "
    "DESIGN pre-commit per BK-76/40/41/42 precedent, green at 359711b9 — "
    "post-commit 17/17 item29+BK43); xv6-nano 13/13; xv6-boot 5p/2s; pre-commit "
    "hook at landing: differential 38/38 + Pillar 2.3 parity 8/8. Engine copies "
    "synced md5 c679537e8c6a668048671fbcb806d38d x2; WGSL twin UNTOUCHED "
    "(syscall handlers oracle-Python-only, no twin surface — BK-40 precedent). "
    "Numbers structural, rule-1 floors do not attach. NOT proved / still open: "
    "BK-44 FS-allow posture (0x03/0x04 root checks, separate row); VFS-attached "
    "legs (no VFS device in this harness; the argv consult covers the VFS arms "
    "structurally at the dispatch site); 0x01 WRITE output window + 0x08/0x09 "
    "AUDIO windows (separate class); BK-45 VFS reroute dests; BK-50 twin door "
    "posture; allowlist CONTENT correctness beyond deny-by-default (L4 pins the "
    "baseline only).** |"
)

LEDGER_ENTRY = """### 2026-09-30 ~23:5x CDT — BK-43 LANDED (RUN path/argv fence guard, step 5 of the sequenced fence commit): 0x12 RUN2's ARGV windows are fenced and the probe's path-smuggle shape is confirmed dead under BK-42's landed consult (builder af3e62239ce2, commit 359711b9 via branch bk43/run-path on the REUSED bk40-syscall worktree — disk constraint precedent, merged fast-forward to mainline; picked at HEAD aadfd35a == monitor fingerprint, tracked dirty set verified = pre-existing monitor-fix files, mailbox rule clean, newest RULING mtime 09-29 09:08 < HEAD 23:18, ledger STATUS ACTIVE, CLAIM QUEUE empty):

- Fix (tools/glyph_isa_v2.py + glyph_dispatch mirror, md5 c679537e8c6a668048671fbcb806d38d x2): GlyphCPUv2._bk43_argv_fault(arg_addr) — 0x12 RUN2's argv windows (r2=arg1_addr, r3=arg2_addr) consulted at the SYSCALL dispatch site BEFORE the handler runs, delegating to _bk42_path_fault (now tag-parametrized; default 'path_decode_fence' byte-identical) with tag `argv_decode_fence`; addr==0 admitted. Refusal = landed E-K1 tail via _stack_fence_fault: handler never runs, out-of-tile RAM can no longer cross execve() as ARGV. PATH target (r1) already fenced by BK-42 — L1 pins it (allowlist worst-case).
- Gate tests/test_bk43_run_path_fence.py 7/7 GREEN. RED-first at landing (fix absent, /tmp/bk43_red3.log md5 7d8b27f2bc4b55c4a434596834e7be94, exit 1): L2 rc=0 clean, '[SYSCALL] RUN2: executed /tmp/r5 (1 args), exit code 0' — the exact measured defect; 1 failed / 6 passed. Fix -> 7/7.
- GATE-DRAFT DEFECTS (receipted in the test docstring): ARG staging at word 200 OUT of tile -> moved to run 224..231; 50-instr program = 7-row image and the PARALLEL_ST write-through mirror maps staging word 192 to image row 6, CLOBBERING SYSCALL/HALT slots 48..55 (opcode-None halt at (0,6) pre-syscall) -> program cut to 47 instrs; L4 rd is SIGNED -1; runner needed a shebang.
- Family on the committed tree: BK-43 7/7 + fence family BK-39 11/11 + BK-40 8/8 + BK-41 10/10 + BK-42 7/7 + BK-48-twin 6/6 + BK-49 7/7 + invariants 3/3 (58p/1f pre-commit; the 1 = item-29 test_n1 HEAD-pinned drift guard, RED BY DESIGN pre-commit per BK-76/40/41/42 precedent; post-commit item29+BK43 17/17); xv6-nano 13/13; xv6-boot 5p/2s; pre-commit differential 38/38 + Pillar 2.3 parity 8/8 at commit. WGSL twin UNTOUCHED (syscall handlers oracle-Python-only). Numbers structural, rule-1 floors do not attach.
- NOT proved / open: BK-44 FS-allow posture, BK-45 VFS reroute dests (argv consult covers VFS arms structurally), VFS-attached device legs, 0x01 WRITE / 0x08/0x09 AUDIO windows (separate class), BK-50 twin door posture, allowlist content beyond deny-by-default.
- Next tick: BK-44 (FS-allow posture guard — extend GLYPH_FS_ALLOW root check to 0x03/0x04) or BK-45 per the row order, unless a new CLAIM QUEUE item or binding RULING appears first.

STATUS: ACTIVE

"""


def main():
    bl = BACKLOG.read_text()
    if "RESOLUTION (2026-09-30, builder af3e62239ce2, commit 359711b9" not in bl:
        lines = bl.split("\n")
        # Row 70 (1-indexed) is BK-43; append the resolution inside the row.
        assert lines[69].startswith("| BK-43 |"), lines[69][:40]
        assert lines[69].endswith("|"), lines[69][-40:]
        lines[69] = lines[69] + RESOLUTION
        BACKLOG.write_text("\n".join(lines))
        print("backlog row updated")
    else:
        print("backlog already updated")

    led = LEDGER.read_text()
    if "commit 359711b9 via branch bk43/run-path" not in led:
        # insert new session entry before the first session entry heading
        marker = "### 2026-09-30 ~23:2x CDT — BK-42 LANDED"
        idx = led.index(marker)
        LEDGER.write_text(led[:idx] + LEDGER_ENTRY + led[idx:])
        print("ledger updated")
    else:
        print("ledger already updated")


if __name__ == "__main__":
    main()

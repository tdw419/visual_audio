#!/usr/bin/env python3
"""append_bk40_resolution.py — append the RESOLUTION tail to the BK-40 row
in systems/GLYPH_BACKLOG.md (line-anchored, idempotent)."""
import re

P = "/home/jericho/projects/zion/projects/visual_audio/systems/GLYPH_BACKLOG.md"
RES = (
    " **RESOLUTION (2026-09-30, builder af3e62239ce2, commit ac80cc10 via "
    "worktree bk40-syscall, merged fast-forward to mainline at HEAD 3e4fc75a): "
    "the syscall-layer fence guard LANDED — GlyphCPUv2._bk40_dest_fault(dest, "
    "length, kind) consults the DATA handlers' dest windows at the SYSCALL "
    "dispatch site BEFORE the handler runs (per-handler window from the "
    "register file: 0x02 (r1,r2), 0x04 (r2,r3), 0x13 (r2,r3), 0x11 (r1,r3, "
    "image plane); ALL FOUR handlers write WORD-granular self.memory[dest+i] "
    "— one byte per word, no byte packing; the first draft assumed "
    "byte-granular and faulted word 42, caught by the gate's own "
    "fault_addr leg). Refusal = the landed E-K1 tail via _stack_fence_fault "
    "(fault_addr=word<<2, packed fault_pc, mode->SUPER, KFAULT_PC vector, "
    "kf==0 stop): handler never executes, nothing lands, no partial copy. "
    "Term set identical to every landed consult: USER + _tile_confinement + "
    "_iso_enabled + _addr_in_box (boxes + GO-2 tile); SUPER (E-K2 handlers) "
    "and unfenced tasks untouched. POSTURE (declared-window, documented in "
    "the gate): the consult judges the DECLARED count (r3), not actual bytes "
    "— actual length is host-data-dependent, unknowable pre-handler; "
    "judging actual = the partial-copy race the refusal forbids. "
    "Over-confinement bites only oversized declared windows, which IS the "
    "attack shape. Path/arg decode (_read_path) deliberately NOT touched — "
    "BK-42/43's separate row. Gate tests/test_bk40_syscall_fence.py 8/8 "
    "(L1 read, L2 file_read, L3 file_list, L4 store_code refusal legs w/ "
    "fault_addr=dest*4 + nothing-landed + mode->SUPER; L5 in-tile controls "
    "read/file_read/store_code; L6 ST trap control; L7 non-vacuity — "
    "consult shadow-neutered per-instance, engine md5-pinned before/after, "
    "L1 shape returns clean; L8 family subprocess BK-41 + BK-39). "
    "RED-first at landing (unfixed tree, /tmp/bk40_red.log md5 "
    "8743c24636a8b45cfe635bbf0f252d76): L1..L4 4 failed / 2 passed with the "
    "exact probe shapes (READ 2/2 bytes to addr 168 clean, store_code pixel "
    "(65,66,67) landed out-of-tile, rc=0, faulted=False); fix applied -> 8/8. "
    "GATE-DRAFT DEFECTS caught by the gate's own legs before any number was "
    "claimed, receipted in test docstrings: (1) L2 passed VACUOUSLY in the "
    "first draft — the 22-byte staged path crossed the tile boundary at "
    "word 168 and the landed BK-39 fence trapped the STAGING PARALLEL_ST, "
    "not the syscall (L5's control failing exposed it); fixed to a short "
    "in-tile path. (2) FR_IN_DEST=176 labeled 'in-tile' — 176=(5,16) is OUT "
    "(cols 0-7); fixed to 162. (3) dbg bare step() loop without "
    "cpu.running=True (BK-52 lesson re-bitten); switched to table.wait(). "
    "Family on the committed tree: BK-40 8/8 + fence family BK-76 8/8, "
    "BK-39 11/11, BK-48-twin 6/6, BK-66 7/7 + invariants 3/3, BK-49 7/7, "
    "BK-62/63 twin 9/9 (59/59 combined); xv6-nano 13/13; xv6-boot 5p/2s; "
    "item-29 10/10 post-landing (test_n1 drift guard RED by design "
    "pre-commit, green at ac80cc10); pre-commit differential 38/38 + "
    "Pillar 2.3 parity 8/8 at landing. Engine copies synced md5 "
    "a3685c39634957a4200411ec1a63e797 x2; WGSL twin UNTOUCHED (syscall "
    "handlers are oracle-Python-only, no twin surface — row's source-read "
    "stand). Numbers structural, rule-1 floors do not attach. NOT proved / "
    "still open: BK-42/43 _read_path out-of-tile decode (0x03/0x04/0x07/"
    "0x12/0x13 path args), BK-44 FS-allow posture, BK-45 VFS reroute dests "
    "(the consult covers the VFS arms structurally by sitting at the "
    "dispatch site, but no VFS-attached device leg ran), BK-50 twin door "
    "posture; live-kernel coverage = the 13-scenario xv6-nano suite.** |"
)
with open(P, "r", encoding="utf-8") as f:
    lines = f.read().split("\n")
if "ac80cc10" in lines[66]:
    print("already appended; no-op")
else:
    assert lines[66].startswith("| BK-40 |"), lines[66][:40]
    assert lines[66].rstrip().endswith("|"), lines[66][-40:]
    body = lines[66].rstrip()
    if body.endswith("| |"):
        body = body[:-3] + "|"
    lines[66] = body[:-1].rstrip() + " " + RES if not body.endswith(" |") else body
    with open(P, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("appended; line 67 now", len(lines[66]), "chars")

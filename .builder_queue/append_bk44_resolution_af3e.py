"""Append the BK-44 RESOLUTION tail to systems/GLYPH_BACKLOG.md row BK-44
(builder af3e62239ce2, commit f3582b11). Appends before the row's closing ' |'.
"""
import re

P = 'systems/GLYPH_BACKLOG.md'
text = open(P).read()

lines = text.split('\n')
for i, ln in enumerate(lines):
    if ln.startswith('| BK-44 |'):
        break
else:
    raise SystemExit('BK-44 row not found')

assert ln.rstrip().endswith('|'), 'row does not end with pipe'
resolution = (
    " **RESOLUTION (2026-10-01, builder af3e62239ce2, commit f3582b11 via branch "
    "bk44/fs-allow on the reused bk40-syscall worktree, merged fast-forward to mainline "
    "at HEAD f3582b11): the FS-allow posture guard LANDED (sequenced fence commit step 6) "
    "— the 0x03 FILE_WRITE and 0x04 FILE_READ HOST arms consult _get_fs_allow_roots() "
    "(realpath under a root or refuse, rc -1, deny-by-default) — exactly the 0x13 arm's "
    "landed BK-15 check, fixing the row's measured inversion in place. Placement AFTER the "
    "item-25 VFS reroute so VFS-attached writes/reads keep the VFS's own containment and "
    "never hit the host check. No new dispatch-site consult: this is handler-posture "
    "parity, not a fence term (the fence consults BK-39/40/42/43 are untouched). "
    "0x07/0x12 keep GLYPH_RUN_ALLOW; 0x08/0x09 AUDIO arms and 0x01 WRITE stay out of scope "
    "(separate class, per the row). Gate tests/test_bk44_fs_allow_roots.py 7/7 (L1 0x03 "
    "env-unset refusal w/ rc -1 in rd + NO host file + clean exit (the 0x13 posture); L2 "
    "0x04 env-unset refusal + guest RAM untouched; L3 0x13 baseline stays green (BK-15 "
    "never weakened); L4 0x03/0x04/0x13 under a leg-scoped allow root all succeed "
    "(roots match realpaths, not raw strings); L5 ST out-of-tile trap control (E-K1 "
    "intact); L6 non-vacuity — the MODULE-level _get_fs_allow_roots monkeypatched (the "
    "handler closes over the module global read at call time), engine file untouched "
    "on disk md5-pinned, L1's exact program writes the host file clean (pre-fix shape "
    "reproduced); L7 family BK-42+40+41+39+15 + engine mirror md5 parity). RED-first at "
    "landing time (engine stashed on this tree): L1 fails (b'WX' lands, rc 0 clean), L2 "
    "fails ('AUTUMN' lands, rc 6), L6 passes pre-fix BY CONSTRUCTION (consult absent == "
    "neutered); L3/L4/L5 green = harness live. Fix applied -> 7/7. FIXTURE MIGRATIONS "
    "(never weakened): tests/test_defect_d_ram_scoped_handlers.py (per-test tmp_path "
    "autouse fixture + the 0x03 historical-leg anchor re-synced to the LIVE handler body "
    "— the old anchor predated both the item-25 VFS reroute block and this landing's "
    "root check, so the first RED run failed with 'anchor stale'; the anchor now pins "
    "path line + VFS reroute + DEFECT-D comment + BK-44 check + data lines, and the "
    "historical revert swaps the WHOLE live body for the pre-migration form), "
    "tests/test_glyph_app_echo.py (autouse tmp_path fixture), tests/test_glyph_file_io.py "
    "(try/finally arming), tests/test_item25_vfs.py (fixture arming), "
    "tests/test_bk42_fw_exfil_fence.py L4/L6 (/tmp arming, /tmp = the same scope BK-40's "
    "L3 uses), experiments/glyph_l1_shell.py (_stamp_path arms the session root via the "
    "shell's existing _arm_fs_allow — the single choke point every file verb stamps "
    "through; append-only, nothing narrowed). Family on the committed tree: BK-44 7/7 + "
    "BK-15 + BK-38 + BK-39 + BK-40 + BK-41 + BK-42 + BK-43 + item-25 VFS + file-io + "
    "app-echo + defect_d = 111/111 combined substantive run; item-26..36 migration chain "
    "(9 suites, 101 tests) all green post-commit incl. every test_n1 engine-byte guard "
    "(RED-by-design pre-commit, the BK-76/40/41/42/43 precedent); xv6-nano 13/13; "
    "pre-commit hook at landing: differential 38/38 + Pillar 2.3 parity 8/8. Engine "
    "copies synced md5 8dd8ce806e07249b570d2539a1260612 x2; WGSL twin UNTOUCHED (0x03/"
    "0x04 honest no-op stubs pinned by test_defect_d; host-FS syscalls are oracle-Python-"
    "only — BK-40 precedent). Numbers structural, rule-1 floors do not attach. NOT proved "
    "/ still open: BK-45 VFS reroute dests (next row); 0x01 WRITE output window + "
    "0x08/0x09 AUDIO windows (separate class); VFS-attached legs beyond the reroute-order "
    "source read (item-25's own gate owns those); symlink-escape content beyond realpath "
    "(roots match realpaths; TOCTOU between the check and open() out of scope — "
    "single-threaded handler); allowlist CONTENT policy beyond deny-by-default (the "
    "operator chooses roots; the gate pins only the mechanism).**"
)
lines[i] = ln.rstrip()[:-1] + resolution + ' |'
open(P, 'w').write('\n'.join(lines))
print('BK-44 row RESOLUTION appended')

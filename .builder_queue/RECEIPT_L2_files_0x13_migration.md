# RECEIPT — L2-FILES sub-step 2: `files`/`ls` verb migration over SYSCALL_FILE_LIST 0x13

Landed: commit 74b746c3, 2026-09-24 ~01:1x CDT, builder af3e62239ce2.
Order source: RECEIPT_L2_files_ls_l.md / BK-15 receipt L2 order line:
`ls -l columns -> files/ls verb migration over 0x13 -> mkdir/rmdir under
allow-scoped root -> >> append (BK-7) -> BK-21`.

## What landed

- `experiments/glyph_l1_shell.py`: `_l2_list()` — the listing is served
  by a baked `LDI/SYSCALL r9 0x13/HALT` program (GlyphAssemblerV2,
  width_instrs=8) run on the session CPU; the dir argv is stamped into
  the program's OWN FS-window pixels (measured: unpadded → rc -1
  not-a-directory; padded + own-pixel stamp is the only working
  combination under fs_pix_enabled). Names parse from the NUL-separated
  RAM blob at dest 2100 (outside the 1024..1280 FS window); the entry
  count from rc truncates the list. rc −1 / 0xFFFFFFFF → ERR text.
  GLYPH_FS_ALLOW is armed with the session root, append-only (the shell
  narrows nothing it did not itself grant). NO host os.listdir fallback
  in the shell. `files` verb added (alias of `ls`); plain `ls` output
  byte-unchanged; `ls -l` columns now stat the 0x13-served names; argv
  dir paths cwd-honoring; >1 positional → ERR.
- `tests/test_l2_files.py`: 4 → 7 legs (M1 files==ls; M2 no shell-side
  host listdir; M3 refusal propagates as ERR text).

## Gate arc (both runs this process, this tick)

- RED (git stash of the implementation, HEAD c37ad1c2 tree):
  `3 failed, 4 passed` — test_m1_files_verb_matches_ls,
  test_m2_listing_survives_poisoned_shell_listdir,
  test_m3_bad_dir_returns_err_text.
  output/l2_step2_gate_red2.txt (landing commit).
- GREEN (implementation restored): `7 passed in 0.10s`, exit 0.
  output/l2_step2_gate_green2.txt (landing commit).
- Regression: test_l1_shell_personality + test_bk15_file_list +
  test_glyph_interactive_shell + test_bk7_fs_grow +
  test_glyph_text_console + test_l2_files → `52 passed in 1.17s`.
- Live pipe: writes via the shell then `ls` →
  `[SYSCALL] FILE_LIST: 2 entries from <root> to addr 2100` with the
  exact names; `ls no_such_dir` → `ERR:NOENT:no_such_dir`
  (output/probe_l2_step2_live.py, in the landing commit).

## Landing-time defect kept (gate caught its own author)

The first M2 draft poisoned `os.listdir` unconditionally and RED'd on
the LANDED tree for the wrong reason: the engine's 0x13 arm
(tools/glyph_isa_v2.py:1735) is the SANCTIONED os.listdir caller — the
poison was catching the engine, not a shell fallback. Narrowed to
caller-frame discrimination (poison only when the frame's file is the
shell module). This is why the RED leg is mandatory: the leg that
cannot fail on the right tree also cannot fail for the right reason.

## What the PASS does NOT prove (honesty)

- ls -l size/mtime are still host `os.stat` facts about files the
  0x03/0x04 arms wrote; engine-side FSTAB created-ts is NOT landed.
- mkdir/rmdir under allow-scoped root and `>>` append (BK-7) are later
  sub-steps; BK-21 after.
- The listing arm runs the Python engine's host-shim 0x13 path; no
  WGSL/shader-path leg is claimed (the BK-15 receipt's twin-exclusion
  contract stands: 19u excluded from the 16u..255u bridge, twin −1
  normative).
- Single host, single process family; no rate claims → floors N/A.
- Scope check: only experiments/glyph_l1_shell.py,
  tests/test_l2_files.py, and output/ gate artifacts changed
  (`.hermes_guest_context/guest_state.json`,
  `.update_proposals.log`, `.venv/bin/*` churn,
  `ubuntu_desktop_pxc1_v3_selfhost/frame_00230.png` were pre-existing
  dirty state from other lanes — untouched, not in the commit).

## Next sub-step

mkdir/rmdir under allow-scoped root (L2 order line 3), then `>>` append
(BK-7), then BK-21.

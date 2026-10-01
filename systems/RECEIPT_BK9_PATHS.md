# RECEIPT: BK-9 — Hierarchical FS Paths (SYS 14)

**Date:** 2026-09-12 (builder cron af3e62239ce2 run)
**Roadmap row:** BK-9 (promoted from GLYPH_BACKLOG at b897009)
**Gate:** `tests/test_bk9_paths.py` — 3/3 GREEN
**Arc regression:** 105 passed, 0 failed (17 suites: GH-4/7/8/8c/11/16/18/25/26 + BK-1/2/3/4/6/7/8 + ENG-1), exit 0 (`output/bk9_arc_regression.txt`)
**RED receipt:** `output/bk9_gate_run1_red.txt` (initial: ImportError, no `paths_kernel_image`; intermediate REDs during bring-up in run history)

## What landed

`tools/glyph_gpt/baker.py`: `paths_kernel_image()` + `_bk9_kernel_program_text()` —
a pixel-resident SUPER path-walk kernel + one USER box task, baked as ONE image
(two-pass label-PC binding, min_rows=80 keeps FS window [1024,1060) clear of text).

### Syscall ABI (extends the GH-14/FS-v2 family)

| SYS | name | args | verdict (word 754) |
|-----|------|------|--------------------|
| 12 | mkdir | a0 = packed name, a1 = parent inode (0=ROOT) | new inode id |
| 14 | resolve | a0 = final component (name / '.' / '..'), a1 = depth (components consumed, max 3) | final inode id; 0xFFFFFFFF = INODE_NOTFOUND |

Path prefix 'dir1/dir2/...' is a bake-time constant (matches the roadmap's
`dir1/dir2/f.txt` example); depth selects how many components the walker consumes.
Missing components return INODE_NOTFOUND cleanly — no fault, execution continues (L3).

### Dirent layout (the gate's pinned oracle contract)

ROOT dirent pair: 1028 = first child's NAME, 1029 = child inode id (mkdir).
Per-inode chain: word INODES+id+3 holds the child's dirent NAME (dir1 → 1048
holds "D2", written by mkdir dir2); dir2's leaf chain pair is 1047 (NAME slot)
+ 1049 (CHILD inode-id slot) — mirror of ROOT's pair. Inode id allocation is a
global sequential counter at word INODES+1 (ROOT=0, dir1=1, dir2=2, leaf=3).

## Defects found & fixed during bring-up

1. **Inode id off-by-one (ROOT collision):** first mkdir allocated id 0,
   colliding with ROOT and contradicting the walker's baked dir1=1.
   Fix: counter = last-allocated (starts 0); new id = counter+1.
2. **ROOT dirent pair incomplete:** mkdir stored only the name at 1028,
   never the child id at 1029 (test asserts the pair).
3. **'..' packed-constant typo:** kernel compared against 11830 (0x2E36)
   instead of 46|46<<8 = 11822 (0x2E2E) — '..' resolves fell through to
   resolve-create.
4. **Step-3 probe/create word mismatch:** walker probed 1048 while create
   wrote 1049 (and vice versa across iterations); final contract: probe
   NAME at 1047, store id at 1049, never clobber 1048 (dir1→D2 name).
5. **Depth-2 exit leg:** originally ended the walk at dir2 unconditionally;
   now the final component is resolved against dir1 ('.' → 1; name-hit in
   1048 → 2; miss → INODE_NOTFOUND) — this is where L3's clean fault lives.
6. **Test-harness plumbing:** `_bake` didn't forward `dots_leg`, so the L2
   test baked the default (leaf) image; fixed in `tests/test_bk9_paths.py`.
7. **`JNZ` doesn't exist in the glyph ISA** (branch-on-CMP-flag is `JZ` +
   inverted flow) — rewrote the depth dispatch as `JZ depth2 / JMP step3`.

## Gate legs (all GREEN)

- **L1** `test_bk9_mkdir_dir1_dir2_and_deep_resolve_creates_leaf`: mkdir dir1
  (ROOT) + mkdir dir2 (dir1) + resolve 'dir1/dir2/f.txt' → verdict = leaf
  inode 3; pixel-resident dirent chain verified via `_pw` reads:
  1028=D1, 1029=1, 1048=D2, 1049=3.
- **L2** `test_bk9_dot_and_dotdot_navigation`: resolve 'dir1/dir2/..' then
  'dir1/.' — both land on dir1 (id 1), '.' and '..' handled by the walker.
- **L3** `test_bk9_missing_leaf_component_faults_clean`: resolve
  'dir1/ghost.txt' → verdict 0xFFFFFFFF (INODE_NOTFOUND), no fault, kernel
  reaches its clean 0xCAFE000E halt, task exit word 0xFEED000E written.

## Notes

- `tests/test_bk9_paths.py` matches `.gitignore:101` (`test_*.py`); force-added
  per the transpiler-skill convention (gate tests are part of the receipt).
- `test_gh26_glass_box.py` excluded from the arc sweep: pre-existing env gap
  (`mcp` module not in .venv py3.11; it runs under the py3.12 MCP venv), not a
  regression of this change.

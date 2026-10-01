# RESEARCH: VFS-attached syscall twins under a contained USER task — path containment REAL, RAM-dest containment ABSENT

**Tick:** Phase 1c research, builder cron af3e62239ce2, 2026-09-27 ~03:1x CDT
**Base:** HEAD 4b0bb0c1 (my BK-44 tick), tracked tree clean at claim
**Probe:** `.builder_queue/probe_vfs_fence_af3e.py` (untracked, landed modules only)
**Backlog row filed:** BK-45 in `systems/GLYPH_BACKLOG.md`

## The question (open in two prior receipts)

- `RESEARCH_fs_allow_asymmetry.md:109-111`: "The VFS-attached twins
  (vfs_write/vfs_read/vfs_list, item-25): the probe ran with no VFS
  attached; whether the VFS layer re-implements or inherits the root
  check is unmeasured."
- `RESEARCH_fw_exfil_path_read.md:111`: "0x07/0x12 RUN and the VFS
  vfs_write twin (source-read inference only)."

Every BK-38..44 probe ran VFS-less. This tick attaches the landed
GlyphVfs (`tools/glyph_vfs.py`) on the SAME item-29 harness
(`GlyphProcessTable.spawn(tile=(5,0,8,8))`, MODE_USER at first
instruction) and measures both containment boundaries of the VFS
reroute arms (`glyph_isa_v2.py:1474-1484` write, `:1520-1531` read,
`:1764-1776` list).

## Method

9 legs (3 runs, byte-identical results, md5 c1ac611a712160654dfddd7ed4be27ee;
verdicts from in-RAM syscall rc parked by the program itself at word 198 +
HOST filesystem state, never handler stdout):

1. **vfswrite_relative** — 0x03 'q1.txt', in-tile data → rc 0, staged
   (overlay dirty, `vfs_write` live).
2. **vfswrite_escape** — 0x03 '../../' → rc **-1 REFUSED** by
   `_guest_rel` (`glyph_vfs.py:316-338`), faulted=False, nothing landed.
3. **vfswrite_hostabs** — 0x03 '/tmp/b8w' → rc 0 but staged as
   `tmp/b8w` INSIDE the staging root; **host /tmp/b8w verified absent
   host-side** (`ls` after every run: No such file).
4. **vfswrite_absolute** — 0x03 '/abs.txt' → rc 0, staged
   (leading '/' stripped, single-root contract).
5. **vfslist_escape** — 0x13 '..' → rc **-1 REFUSED**.
6. **vfslist_root** — 0x13 '/' → rc = entry count (grows as earlier
   legs stage files: 3→4 — the overlay union view is live).
7. **ctl_st_out** — plain ST to out-of-tile word 168 → EXIT_FAULT,
   fault_addr=672=168*4, mode→SUPER (E-K1 intact on the same tree).
8. **vfsread_dest_out** — 0x04 staged 'q1.txt', dest=168
   (**OUT-of-tile**) → rc 2, bytes 'V','W' land at 168/169 clean.
9. **vfslist_dest_out** — 0x13 '/', dest=168 → rc 4, listing bytes
   ('a','b','s','.' = 'abs.txt' prefix) land at 168.. clean.

## Verdict (measured, both directions)

**PATH containment: the VFS layer HAS it.** `_guest_rel` refuses '..',
strips leading '/', resolves under the staging root — a contained USER
task CANNOT escape the disk image through a VFS-routed path, while the
SAME task under the SAME tile reaches arbitrary HOST paths the moment
no VFS is attached (BK-42/44's measured host arms). BK-44's open
question is answered: the root check the host arms lack exists only in
the VFS twin.

**RAM-dest containment: the VFS layer LACKS it.** The 0x03/0x04/0x13
VFS-reroute dest loops (`:1476-1478`, `:1526-1529`, `:1770-1774`) are
the identical fence-blind bounds-only shape BK-40 measured on the host
arms — out-of-tile dest lands clean. BK-40's class EXTENDS to the VFS
layer; BK-40's probe scope note ("ran VFS-less") is now closed as
"same defect, both routes".

Combined posture inversion (speculative framing, not load-bearing): a
guest's FS blast radius is decided by ATTACHMENT STATE, not by any
uniform policy — VFS-attached = path-contained but RAM-uncontained;
VFS-less = path-uncontained (arbitrary host R/W) and RAM-uncontained.

## Probe hygiene + the harness bug that validated the geometry rule

- Draft leg B used a 20-byte path ('../../../../tmp/b8w'): 60
  PARALLEL_STs → 67 instructions → **the write-through mirror
  self-overwrote the program image** (measured: execution died at
  instruction slot 40, image dump showed path bytes stamped over slots
  40+; the SYSCALL never dispatched, so "rc 0" was the harness's own
  tombstone, NOT a containment failure). Caught by re-deriving from
  the instruction dump, fixed to ≤9-byte paths (34 instrs, the
  proven-safe geometry from probe_fs_allow_asym_af3e.py), and the
  self-overwrite itself is documented here as yet another
  PARALLEL_ST-mirror hazard for probe authors.
- Env: no GLYPH_FS_ALLOW interaction (VFS arms never consult it —
  confirmed by source-read `:1474-1484`, and irrelevant: the VFS root
  is the staging dir). Temp dirs cleaned in finally; /tmp/b8w
  asserted absent post-run.
- 3 internal runs byte-identical; determinism check in-probe True.

## Numbers discipline

All quantities structural (return codes, fault_addr, file existence,
entry counts, an md5). No rate/latency/cost claim → rule-1 floors do
not attach. No citation of superseded floors or banned ratios.

## NOT verified

- 0x01 WRITE / 0x08 AUDIO_OUT / 0x09 AUDIO_IN arms (no VFS reroute
  exists for them; unchanged from BK-40's scope note).
- 0x07/0x12 RUN under VFS attachment (RUN has no VFS arm — source-read).
- The ext2-image fallback path of vfs_read (debugfs dump arm) — leg 8
  read the staged overlay, not the image, so the image arm's dest
  behavior is the same code path (`:1526-1529`) but was not separately
  exercised from a synced image.
- PngVfs (PNG transport wrap/unwrap) internals — exercised only
  through GlyphVfs.format().
- WGSL twin (syscall handlers are Python-only; unchanged).
- Whether sync() committing staged out-of-tile-dest content re-exposes
  anything new (sync is host-side and copies staged files into ext2;
  no guest interaction measured).

## Backlog candidate (filed as BK-45, systems/GLYPH_BACKLOG.md)

Gate: `tests/test_bk45_vfs_fence.py` — L1: 0x04 VFS dest out-of-tile
must trap or drop (one posture documented), RED today ('VW' lands);
L2: 0x13 VFS dest out-of-tile same, RED today; L3: in-tile dest
controls stay green; L4: '..'/escape refusals stay green (the path
containment must SURVIVE the fix — never weaken a live guard); L5:
host-absence control (host-shaped path never touches host FS); L6:
non-vacuity — neuter the new consult → L1/L2 fire; L7: family —
BK-38..42 + item-29 + BK-15 gates green; worktree isolation per
AGENTS.md (engine-core file). Prereq: BK-38 + BK-39 + BK-40 + BK-41 +
BK-42 + BK-43 (same sequenced engine commit family — the VFS dest
loops are the same consult-site class).

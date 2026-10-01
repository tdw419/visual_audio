# Pixel Software System — Roadmap

Status snapshot as of 2026-07-29. This reflects what was actually verified
working this session, not aspirational claims — see the "verified" tags.

## What exists today (verified)

- **wordbase.db**: 125,567 words, byte-level RGB24 pixel round-trip via
  `src/pixel_tokenizer.py` (verified byte-exact on real source files).
- **`macros` table**: word/phrase → expansion. Two kinds, distinguished by
  `lang`: `text` (inline code fragment) and `command` (shell command).
- **`tools/macro_expand.py`**: expands text macros; resolves/runs command
  macros with a type guard so a text macro can never be silently executed.
- **`visual_audio.mkv` (VAC1 container)**: single-file store, 126 entries,
  atomic writes as of this session (`tools/va_container.py`'s
  `write_frames()` now encodes to a temp file, verifies frame count, and
  only then renames over the target — a killed/failed encode can no
  longer truncate the container).
- **`tools/pixel_build.py`**: `add` (macro-expand → encode → verify →
  store), `run` (extract → decode → compile-check → execute), `list`,
  `diff`. Proven end-to-end: a program was deleted from disk entirely and
  still ran correctly from its MKV pixel entry alone.
- **`tools/pixel_visualizer.py`**: `visualize` (PNG render), `map`
  (pixel→byte→frequency table), `analyze` (structural analysis of
  decoded source). All three verified against real data this session.
- **`tools/verify_all.sh`**: One-command verification of container integrity
  and pixel entry round-trips. Extracts, decodes, and compile-checks all
  `.pixel` entries. Completed 2026-07-29 (P0-1).
- **`vendor/xv6-riscv/pin_xv6_commit.py`**: Tool for pinning xv6 upstream
  commit to ensure reproducible builds. Pins to `75c46385` as of 2026-07-29.
  `build.sh` now uses pinned commit by default with fallback warning (P0-2).
- **GPU RISC-V emulator** (`tools/RISCV_CPU_MMU.wgsl` +
  `tools/boot_xv6_gpu.py`): booted xv6 to an interactive shell
  on real GPU compute (documented in
  `docs/GPU_RISCV_XV6_BOOT_RECEIPT.md`). Upstream now pinned to known-good
  commit to prevent silent regressions.
- **`semantic_cpu_emulator.py`**: a small (~470-line) hand-written RV64
  interpreter. Runs and exits cleanly after the 4GB memory-size fix, but
  is a toy — no MMU/paging, no virtio, no privileged-mode traps. It
  cannot boot a real kernel or the Ubuntu disk image; treat it as a
  self-modification demo vehicle, not a boot path.

## Known gaps and risks found this session

1. Every `va_container.py add`/`update` re-encodes the **entire**
   container (currently ~900MB, 12,597+ frames) via ffmpeg, taking
   55–90+ seconds and growing linearly with container size. This is what
   caused the two real corruption incidents this session (interrupted by
   an external timeout) before the atomic-write fix. Atomicity now
   prevents corruption, but the cost itself is still there and will keep
   getting worse. **Documented in va_container.py docstring (P0-3).**
2. ~~`vendor/xv6-riscv/build.sh` clones `origin/riscv` **HEAD** with no
   pinned commit.~~ **FIXED** 2026-07-29. Now uses `pin_xv6_commit.py`
   state file. Pinned to `75c46385` with verified boot notes. Build
   warns if pin file is missing and falls back to HEAD.
3. `pixel_build.py` and `pixel_visualizer.py` have inconsistent
   interfaces — one operates on MKV entry names, the other on raw
   extracted pixel files. Minor friction, easy fix.
4. No automated test suite covers the round-trip guarantees this session
   verified by hand every time (encode/decode fidelity, container
   integrity after writes, macro resolution safety). Every "complete"
   claim this session needed manual re-verification to catch false
   positives — that manual process should become a script.
5. `macros` table with `lang='command'` rows are literal shell commands
   executed via `subprocess.call(..., shell=True)` — fine for a
   single-user local tool, but worth being deliberate about, since
   writing to that table is equivalent to granting shell execution.
6. Known, separate pre-existing issue: wordbase.db is missing ~789 words
   present in the original voicebook source (including basics like
   "hello"/"world"), plus some junk test rows. Not touched this session.

## Roadmap

### P0 — Protect what already works
- [x] Add a `tools/verify_all.sh` (or `pixel_build.py verify-all`) that
  runs: `va_container.py verify`, round-trips every `.pixel` entry
  through decode+compile-check, and reports pass/fail — one command to
  run after any change, replacing ad hoc manual verification.
  **COMPLETED** 2026-07-29. See `docs/P0-verification-gate.md`.
- [x] Pin the xv6 upstream commit in `vendor/xv6-riscv/build.sh` /
  `README.md` to whatever commit last reproduced the 2026-07-20 receipt
  (or, if unrecoverable, to today's working commit once re-fixed) so
  "verified working" stops silently expiring.
  **COMPLETED** 2026-07-29. Created `pin_xv6_commit.py` with state file
  `xv6_commit_pin.json`. Pinned to `75c46385` with notes about verified
  boot. `build.sh` now uses pinned commit by default with clear warning.
- [x] Document the real write cost of `va_container.py add`/`update`
  (55–90s+ at current size) directly in its `--help` / docstring, so
  future timeouts are sized correctly instead of getting killed mid-write.
  **COMPLETED** 2026-07-29. Added PERFORMANCE NOTE to `va_container.py`
  docstring with current metrics.

### P1 — Toolchain consistency
- [x] Unify `pixel_visualizer.py` to accept MKV entry names directly
  - COMPLETED 2026-07-30. Added `--mkv-entry` flag to all subcommands (visualize, map, analyze).
  - Extracts pixel data internally via `extract_pixel_data_from_mkv()`, matching `pixel_build.py run` behavior.
  - Backward compatible: still accepts pre-extracted `.pixel` files.
- [x] Generalize `pixel_build.py list`'s version-history view (currently
  works for any entry, but the `.pixel_vN` convention was only ever
  produced by the one self-modification code path) so any pixel-stored
  program can accumulate/inspect/prune versions the same way.
  - COMPLETED 2026-07-30. Added `pixel_build.py version` subcommand with:
    - `pixel_build.py version <name>` — show version history
    - `--create` — create version snapshot (current → vN)
    - `--restore N` — restore from version N
    - `--prune [--keep N]` — remove old versions
- [x] Add `pixel_build.py verify` subcommand for single-entry verification.
  - COMPLETED 2026-07-30. `pixel_build.py verify <name>` extracts, decodes, round-trips, and compile-checks a single entry.
  - Supports `--no-compile` flag for non-Python files.
  - Much faster than full container verify (no FFmpeg re-encode).

### P2 — Container scaling
- [ ] Investigate incremental/multi-frame directory support (the current
  `save_container()` docstring already flags "directory exceeds one
  frame; multi-frame directory not yet implemented" as a hard limit) so
  adding one small entry doesn't require re-encoding gigabytes of
  unrelated frames every time.
- [ ] Consider a write-ahead/staging area: batch several `add`/`update`
  calls and commit them as one re-encode, cutting the per-change cost
  when doing multi-file pixel-software work.

### P3 — Real OS boot (the GPU RISC-V path)
- [ ] Re-diagnose the xv6 stall: diff the freshly-cloned upstream against
  the patches' assumptions, bisect if needed, get back to a shell prompt
  on GPU.
- [ ] Once re-stabilized, wire `bootos`-style macros at the *pixel
  software* layer too — i.e., a command macro that runs
  `boot_xv6_gpu.py` against a kernel that itself was built and stored via
  `pixel_build.py`, closing the loop between the two systems built this
  session.

### P4 — Data quality
- [ ] Backfill the ~789 missing words in `wordbase.db` (tracked
  separately; blocks nothing today but underlies every encode/decode).
- [ ] Clean up known junk test rows (175614–175618).

### Stretch — actual "plain text → new program"
- [ ] Everything above is "plain text/macros → *existing* code,
  expanded/invoked/stored as pixels." True generative plain-text
  programming (a natural-language description producing new code) needs
  an LLM step in front of `macro_expand.py`/`pixel_build.py` — out of
  scope until the above is solid, but the pixel-storage/versioning/
  execution layer built this session is exactly the substrate that step
  would plug into.

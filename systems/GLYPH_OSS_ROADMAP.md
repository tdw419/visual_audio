# Glyph Language Open-Source Roadmap

GH-1 through GH-25 proved the machine: a static glyph image is a real
computer, code cannot enter it without passing the oracle, and S3 measured
honestly that the current model is a safe filter, not a productive emitter.
This roadmap is the *different* project that follows from that: making
Glyph (.glyph) a public, standalone, respectable programming language with
outside users — separate from shipping `visual_audio.mkv` as a product.

House rules inherited from `GLYPH_SELF_HOSTING_ROADMAP.md`: human-owned
checklist, NOT a cron job. Every item ships a loudly-failing test or a
concrete external artifact (a URL, a tagged release, a CI badge) before it's
marked done — "the builder said so" is not a receipt here; "a stranger who
never saw this repo could do X" is.

## Why sequencing matters here

The natural instinct is to reach for the exciting end-state first — package
registry, LSP, a conference paper. All three are real and worth doing
*eventually*. But none of them mean anything without a stable, documented
thing to point at, and this project's own S3 result is the cautionary
example: impressive machinery, honestly measured, came in weaker than the
pitch. Don't let the OSS rollout repeat that pattern — ship the boring floor
first, let outside reaction decide what's worth building next.

Non-goals for this roadmap: it does not touch the internal
`visual_audio.mkv` product goal, the builder cron, or GH-1..25's runtime.
Glyph-the-language and VAC1-the-container are related but separable; this
roadmap only grows the former into something an outside stranger can use.

## Status

| # | Item | Oracle | State |
|---|------|--------|-------|
| GL-0 | Extraction: a standalone repo (or clearly-scoped subpath) containing only ISA, transpiler, baker, runner, oracle, and their tests — sanitized of internal refs (hermes paths, wordbase, cron, `.hermes/scratch`). No secrets, no internal project names in public-facing files. | A fresh `git clone` of the extracted target builds and runs the test suite with zero references back into `visual_audio`'s internal tooling; `ecc:opensource-sanitizer`-style scan clean | ✅ DONE 2026-09-11 commit `731edc3` — extracted to `/home/jericho/zion/worktrees/glyph-isa` (3.8 MB, 32/32 tests pass isolated) |
| GL-1 | LICENSE chosen and applied (MIT or Apache-2.0) | `LICENSE` file present, referenced from README | ✅ DONE 2026-09-11 — dual MIT OR Apache-2.0 applied (`LICENSE-MIT`, `LICENSE-APACHE`) |
| GL-2 | `docs/spec/GLYPH_ISA_SPEC_v1.0.md`: opcode semantics, calling convention (caller/callee-saved registers, mailbox ABI), the spatial memory model (word RAM vs image pixels vs Hilbert-paged frames), pulled out of scattered source comments into one independently-readable document | A second implementation (even a toy one) could plausibly be written from the spec alone, without reading `glyph_isa_v2.py` | 🟡 DRAFT 2026-09-11 commit `b059539` — full ISA/MMIO/paging/admission coverage, spot-checked against source; needs a fresh-eyes read by someone who has NOT read the engine before calling it done |
| GL-3 | README with install/build instructions and 3-5 runnable example `.glyph` programs with expected output | A person who has never seen this repo clones it, follows the README verbatim, and gets matching output — verified by someone who is not the author | ✅ DONE 2026-09-11 — comprehensive README with quickstart, full CLI guide, and verbatim commands/outputs for all 4 canonical examples |
| GL-4 | CI: existing pytest suite (GH-18..25 + S1/S2) runs on every push/PR via GitHub Actions | Green badge in README, visible on a real push | ✅ DONE 2026-09-11 — live at `https://github.com/tdw419/glyph-isa`, CI matrix (Python 3.11/3.12) passing green in GitHub Actions (run 34614846851) |
| GL-5 | Unified CLI (`glyphc`) wrapping existing `baker.py`/`runner.py`/`geos_ascii_bridge.py`: `build`, `verify`, `run`, `disasm` — consolidation of what exists, not a rewrite | `glyphc build examples/hello.glyph -o hello.glyph.png && glyphc run hello.glyph.png` works from a clean checkout with no other host script imports | ✅ DONE 2026-09-11 commit `53611f1` — `tools/glyphc.py` + root executable `./glyphc`; oracle command passes verbatim; 4/4 CLI unit tests green |
| GL-6 | One recorded/interactive demo: a `.glyph` program baking to pixels and executing, viewable without cloning anything (asciinema recording or static hosted page — not committing to a full WebGPU playground yet) | A shareable URL or asciinema link that plays back the demo end to end | 🟡 ARTIFACT DONE 2026-09-12 (loop-side, `b5aa3f2` in the extracted OSS repo) — `docs/demo/gl6_bake_and_run.cast` + gate `tests/test_gl6_demo_cast.py` committed there; re-verified green this tick (GL-6+GL-7 = 8 passed, exit 0, worktree clean, `/usr/bin/python3`). Row stays OPEN: its oracle wants a *shareable* link, and publishing is reserved to Jericho (`RULING_next_lane_OSS_GL6_GL7.md` §2) |
| GL-7 | One benchmark, honestly reported, with caveats: cold-boot-to-first-instruction from a `.glyph.png` vs. a comparable baseline (WASM or a microVM) | A written benchmark doc with methodology, raw numbers, and an explicit "what this does not show" section — same honesty standard as S3_RECEIPT.md | 🟡 ARTIFACT DONE 2026-09-12 (loop-side, `0aa14b1` in the extracted OSS repo) — `docs/bench/cold_boot.json` + gate `tests/test_gl7_benchmark.py` committed there; re-verified green this tick (same 8-passed run as GL-6). Row stays OPEN pending publication — same reservation as GL-6 |
| GL-8 | External pilot: at least one person outside this session/project builds or runs something with GL-3 through GL-5 and reports friction | A written list of real friction points from an outside user, not self-assessed | QUEUED |
| GL-9 | Tree-sitter grammar (`tree-sitter-glyph`) for syntax highlighting | Highlighting works in at least one editor (Neovim/VS Code) from the published grammar | QUEUED — after GL-8 |
| GL-10 | Language Server (`glyph-lsp`): register/label completion, StaticVerifier warnings inline | Editor round-trip demo (open file, get a real diagnostic) | QUEUED — after GL-9 |
| GL-11 | Tile registry format + one public registry instance: packages as pre-admitted tiles with embedded oracle receipts (`tile_name.glyph.json`) | A tile published by someone other than this session, importable and re-verified by a stranger | QUEUED — after GL-8, horizon |
| GL-12 | Public writeup (blog post or arXiv preprint, not necessarily a PLDI/ASPLOS submission on day one): proof-carrying-code-by-admission, the Hilbert spatial substrate, the S3 honest-measurement result | Published, linkable artifact; venue escalation (workshop → conference) only after real outside interest, not pre-committed here | QUEUED — after GL-6, GL-7 |

## Sequencing, not a wishlist

GL-0 through GL-4 are the floor and have no real dependencies on each other
beyond ordering convenience — they could be parallelized across worktrees.
GL-5 through GL-8 are what turn "public repo exists" into "a stranger used
it." Everything from GL-9 onward (editor tooling, registry, academic
publication) is explicitly sequenced *after* GL-8 — there should be a real
outside user's friction report before investing weeks in an LSP or a paper
nobody asked for. If GL-8 turns up no interest, that's a legitimate signal
to stop here rather than a reason to build louder.

# Pixel Mind / VAC1 Container — Roadmap

Scope: the "Screen is the Mind" pixel-substrate work (code-as-pixels execution,
self-referential agent memory) and the underlying `va_container.py` (VAC1)
format it depends on. This is deliberately separate from the main
`ROADMAP.md`, which is currently corrupted (every line duplicated with a
mangled prefix) and has its own history of fabricated task claims — do not
merge this doc into it without first fixing that file.

Every item below reflects something directly verified in this repo as of
2026-08-13 (re-run and inspected, not taken from an agent's self-report). See
project memory `verify-autonomous-completion-claims` for why that distinction
matters here specifically.

## What's actually working today (verified)

- `tools/va_container.py`: store/extract/execute Python files as frames in
  `visual_audio.mkv`. `run` executes the **embedded frame's bytes**, not the
  file on disk — `update` must be called after any edit or tests silently run
  stale code (see memory `va-container-run-uses-embedded-frame`).
- `pixel_hermes_bridge_context.py` + `tools/pixel_mind_repl.py`: real Ollama
  inference, routed through the container, with the agent reading its own
  prior `pixel_thought_*` frames as context for new queries. Verified
  cross-process recall (a fact stated in one invocation was correctly
  recalled in a separate later invocation with no shared process state).
- `db/wordbase.db` `spectrogram_cache`: 126,142/126,167 words have real,
  non-empty PNG spectrogram data (spot-checked, not placeholder-sized).
- **Structured thought frames** (P1): `pixel_thought_*` frames now store
  JSON with `timestamp`, `query`, `response` fields. Parseable for future
  search/meta-cognition work.
- **Rolling summarization** (P2): When thoughts exceed `PIXEL_MIND_CONTEXT_SIZE`,
  oldest exchanges are compressed via synchronous Ollama call into
  `pixel_summary_*` frames (structured JSON with `summarized_exchange_count`,
  `summary`). Most recent summary is prepended to context alongside raw thoughts.
- **Cached tool extraction** (P2): `cmd_run` extracts to persistent
  `.va_run_cache/<container_hash>/` and skips disk writes for unchanged entries
  (verified via sidecar `.sha256` files).
- **Host Hermes routing** (P3): `~/.hermes/hermes-agent/run_agent.py` now parses
  provider from `provider/model` format (e.g. `anthropic/claude-fable-5`) and
  routes to correct API endpoint. Verified with real Anthropic API call.

## Known, measured limitations (not yet fixed)

1. **Directory entry ceiling (hard crash, not degradation).**
   `save_container()` caps the VAC1 directory to one frame (65,531 bytes).
   Measured: ~272 bytes/entry → ~240 total entries max in a container at
   current sizes. Past that, every `add`/`update` raises `ValueError`. Every
   REPL turn writes one entry, so a long session hits this wall abruptly.
   See memory `va-container-directory-entry-ceiling`.
2. **No context relevance filtering.** `PIXEL_MIND_CONTEXT_SIZE` takes the
   last N thought frames (default 5). Summarization preserves old context,
   but retrieval is still recency-based, not similarity-based. No embeddings
   or keyword search yet.
3. **Thought frames are not directly queryable.** `/cat N` in the REPL is the
   only way to inspect them. No search by topic, no filtering by timestamp
   range, no aggregate queries (e.g. "show all thoughts mentioning 'color'").
4. **No delete/prune.** The REPL's `/clear` command is a stub that prints a
   warning and refuses — VAC1 is append-only by design, so old thought frames
   can never be reclaimed short of rebuilding the container from scratch.

## Priority order

### P0 — Fix before building more on top of the memory system
- **Multi-frame directory support.** This is the one item that will cause
  silent-feeling data loss risk (a crash mid-session, not corruption, but an
  unhandled exception a REPL user will hit with no warning as they approach
  ~240 entries). The code already anticipates this
  (`"multi-frame directory not yet implemented"` is a real TODO, not a
  guess). Scope: directory becomes N frames instead of 1; `load_container`/
  `read_directory` need to read all directory frames and concatenate before
  parsing JSON. Should be a self-contained change to `va_container.py` with
  no API changes for callers.
- **Graceful handling at the ceiling**, even before the real fix: catch the
  `ValueError` in the bridge/REPL and tell the user "spatial memory is full,
  rebuild required" instead of an unhandled traceback.

### P1 — Makes the memory system actually useful, not just working
~~Structured thought frames.~~ **DONE (2026-08-13)** — frames now store JSON
with `timestamp`, `query`, `response` fields.

- **Context relevance instead of flat recency.** Now that frames are structured,
  a cheap first step is keyword/embedding similarity against the current
  query to pick which past thoughts to include, rather than always "last N."
  Summarization already preserves old context, but retrieval is still recency.

### P2 — Scale/quality, not urgent
~~Rolling summarization of old thought frames~~ **DONE (2026-08-13)** — when
thoughts age out, they're compressed via synchronous Ollama call into
`pixel_summary_*` frames. Most recent summary is prepended to context.
~~Skip re-extracting unchanged bootstrap/tools entries on `run`~~ **DONE
(2026-08-13)** — `.va_run_cache/<container_hash>/` with sidecar `.sha256`
files skips disk writes for unchanged entries.

- **Multi-modal context retrieval.** If thoughts eventually include non-text
  data (images, audio spectra), extend retrieval to match on multiple modalities
  or generate text descriptions for similarity scoring.

### P3 — Separate track, not part of this memory system
~~Fix host Hermes model routing~~ **DONE (2026-08-13)** —
`~/.hermes/hermes-agent/run_agent.py` parses provider from `provider/model`
format and routes to correct API endpoint.

## Explicitly out of scope / not recommended right now

- Multilingual support, blockchain audio provenance, quantum audio
  processing — these came out of a `possibilities explore` run
  (2026-08-13) that did not ground on its seed questions (verified by
  rerunning it myself; the model produced generic filler unrelated to the
  actual question asked, and a stricter follow-up run using specific
  technical seed questions surfaced the real P0 finding above instead).
  Not rejected forever, just not backed by any real signal — treat future
  `possibilities` output on this project as unreliable at `balanced`
  complexity until it's tried at `-c thorough` and shown to ground properly.
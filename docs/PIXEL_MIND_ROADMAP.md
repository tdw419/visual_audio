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
- **Relevance-based context selection**: `select_context()` in
  `pixel_hermes_bridge_context.py` always keeps the most recent 1-2 thoughts
  for continuity, fills the rest of the context budget by keyword-overlap
  score against the current query (no extra LLM call). Candidate pool for
  scoring/aging-out is wider than the context window
  (`PIXEL_MIND_CANDIDATE_POOL`, default `max(context_size*4, 20)`). Verified
  with a direct unit test proving it actually reorders by relevance, not just
  recency (real production data is currently too small to exercise this path
  in practice).

## Known, measured limitations (not yet fixed)

1. **Directory entry ceiling (hard crash, not degradation).**
   `save_container()` caps the VAC1 directory to one frame (65,531 bytes).
   Measured: ~272 bytes/entry → ~240 total entries max in a container at
   current sizes. Past that, every `add`/`update` raises `ValueError`. Every
   REPL turn writes one entry, so a long session hits this wall abruptly.
   See memory `va-container-directory-entry-ceiling`.
2. ~~No context relevance filtering.~~ **DONE (2026-08-13)** — see
   `select_context()` below. Still no embeddings, just keyword overlap; fine
   for now given the small real corpus.
3. **Thought frames are not directly queryable.** `/cat N` in the REPL is the
   only way to inspect them. No search by topic, no filtering by timestamp
   range, no aggregate queries (e.g. "show all thoughts mentioning 'color'").
4. **No delete/prune.** The REPL's `/clear` command is a stub that prints a
   warning and refuses — VAC1 is append-only by design, so old thought frames
   can never be reclaimed short of rebuilding the container from scratch.

## Priority order

### P0 — Fix before building more on top of the memory system
~~**Multi-frame directory support.**~~ **DONE (2026-08-13)** — The directory now gracefully expands into multiple frames when exceeding 65,531 bytes, correctly shifting absolute indices of payload entries without corrupting historical absolute frame references.
~~**Graceful handling at the ceiling**~~ **DONE (2026-08-13)** — Obsoleted by the actual fix above.

### P1 — Makes the memory system actually useful, not just working
~~Structured thought frames.~~ **DONE (2026-08-13)** — frames now store JSON
with `timestamp`, `query`, `response` fields.

~~Context relevance instead of flat recency.~~ **DONE (2026-08-13)** —
keyword-overlap scoring in `select_context()`, most-recent turns still
guaranteed for continuity.

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

## Known permanent damage (not fixable, low impact)

Two thought frames in the real `visual_audio.mkv` —
`pixel_thought_1786635228` and `pixel_thought_1786635266` — are corrupted and
unreadable. They were written while an earlier, broken relative-offset
directory scheme was briefly live (before it was caught and reverted). The
revert fixed the code but not these two already-written frames. Confirmed via
`va_container.py verify` (FAIL) and content dump (garbage bytes). No tool code
was affected, only two old conversational log entries — not worth a repair
effort, just noted so it isn't mistaken for a live bug.

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
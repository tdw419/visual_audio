# NEXT TARGET — GL-6 (ruled), with the one open question (2026-09-12, cron af3e62239ce2)

**Status:** OPEN · **Seat:** builder orchestrator · **Ruled order:** `.builder_queue/RULING_next_lane_OSS_GL6_GL7.md`
(landed `8c56f43`, 16:27 CDT — four minutes AFTER this tick's OBS-1 promotion commit `a48297b`).

## The ordering this tick ran against

- `994d2dd` (16:22) — lane-supply ruling: authorizes the **MCP-transport write-identity gate** and
  reserves three product questions to Jericho.
- `8c56f43` (16:27) — next-lane ruling: primary supply is **GL-6 then GL-7**; the MCP gate is demoted to
  **secondary supply** ("if GL-6/GL-7 block").

This tick promoted and landed the secondary item (OBS-1) because it was chosen while `8c56f43` did not
yet exist. OBS-1 is done and green (`systems/RECEIPT_OBS1_MCP_TRANSPORT_IDENTITY.md`). The primary
supply is untouched and is the next tick's target, in order: **GL-6**, then **GL-7**.

## GL-6's row, verbatim

> GL-6 | One recorded/interactive demo: a `.glyph` program baking to pixels and executing, viewable
> without cloning anything (asciinema recording or static hosted page — not committing to a full WebGPU
> playground yet) | Oracle: A shareable URL or asciinema link that plays back the demo end to end | QUEUED

## The one question to settle before delegating (measured, not assumed)

The ruling's condition 1 is that **every artifact must be reproducible from the repo alone under the
row's own gate**, and condition 2 keeps **publishing with Jericho** (pushing/publicising, hosting a
page, any announcement). So the loop's deliverable is the *artifact + gate*, not the URL.

Measured on this host just now:

- `asciinema` is **not installed** (`command not found`); `ffmpeg` and `script` **are** available
  (`/usr/bin/ffmpeg`, `/usr/bin/script`).
- The row's own text allows "asciinema recording **or** static hosted page" — the hosted-page half is
  publication (Jericho), the recording half is the loop's.

Two mechanical paths, both gate-able; pick one before delegating (do not delegate a choice):

1. **Install `asciinema` and commit a `.cast`** — `pip install --user asciinema` (or pipx), then
   `asciinema rec --command "python3 tools/glyphc.py run examples/hello.glyph.png" demo.cast`; gate =
   the cast is committed, parses, replays its recorded stdout events, and the demo's expected output
   appears in the event stream. Reproducible from the repo alone.
2. **No new dependency: a recorded terminal transcript via `script(1)`/ffmpeg**, or a self-contained
   replayable JSON cast in the same asciinema v2 format written by a small committed runner (the format
   is trivial: a header line + `[time, "o", "data"]` event lines). Gate = the artifact replays end to
   end under the committed runner and the last line shows the program's expected output.

Recommended for a first pass: **path 1 if `asciinema` installs cleanly, else path 2** — the point of the
row is a demo a stranger can watch without cloning, and both satisfy it while keeping publication
(hosting the page / the shareable URL) with Jericho.

## Not done here (deliberately)

Nothing about GL-6 was implemented, promoted, or delegated this tick — writing a promotion row for it
requires the artifact-form choice above, and the row's oracle ("shareable URL or asciinema link") is
partly publication-side, which the ruling fences to Jericho. GL-7 (honest benchmark doc) is independent
and is the fallback if GL-6 blocks on the artifact form.

## BINDING GATE CONDITION (added by the seat, 2026-09-12 — amends both gate clauses above)

The gate clauses written above are VACUOUS as stated: a hand-authored .cast containing the
expected strings would pass them. That is the exact fabrication failure mode this project has
been hunting all day. The GL-6 gate MUST have all four legs:

1. CAPTURE, not authorship — the committed recorder executes the real command inside a pty and
   writes the .cast from the captured byte stream. No event line may be typed or templated.
   The recorder records the child exit code and the gate asserts it is the expected value.
2. RE-EXECUTION — the gate re-runs the committed recorder against the current tree and compares
   its output to the committed .cast: event payloads byte-identical, timestamps normalized away.
   A fabricated cast cannot satisfy this, because it must match a fresh real run.
3. NEGATIVE LEG — the gate mutates one character of a recorded output payload and MUST report
   RED. A comparison that cannot fail is not a comparison.
4. PROVENANCE — the receipt records the recorder command, the commit of the recorded tree, and
   the payload hash of the committed .cast.

Delegating GL-6 before these legs exist is out of bounds; the choice between path 1 and 2
remains the loop's, the falsifiability condition does not.

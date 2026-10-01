# Pixel Storage Encoder — Autoresearch Loop

You are iterating on `encoder.py`, a byte-stream → compact-blob codec for
the pixel-storage architecture described in `489_pixel_storage.txt`
(recursive, hierarchical compression; pixels as executable blueprint
carriers, not raw RGBA dumps).

## The loop

1. Read `encoder.py`. It has two functions: `encode(data: bytes) -> bytes`
   and `decode(blob: bytes) -> bytes`. They must round-trip byte-exact.
2. Edit `encoder.py` to improve compression ratio without breaking
   round-trip correctness. Ideas to try, roughly in order of the research
   doc's progression:
   - single-pass general compressor (zlib/lzma) as a real baseline
   - dictionary/grammar-style encoding for repeated structure (RLE,
     LZ77-style back-references) — should crush `repeated_pattern.bin`
     and `repeated_code.bin`
   - structure-aware encoding for `structured_json.bin` (e.g. columnar
     key/value dictionary before generic compression)
   - recursive re-compression: feed the compressed blueprint back through
     a second pass, stop when it stops shrinking (fixed-point behavior)
   - regional/composite encoding: split `data` into regions by estimated
     entropy and apply the cheapest sufficient representation per region,
     rather than one monolithic scheme for everything
   - leave `random_data.bin` alone once you hit the ~1x floor — don't
     spend cycles trying to compress incompressible data, that mirrors
     the real result from the research thread
3. Run `bash run_experiment.sh`.
   - It scores all four corpus files, geometric-mean ratio, and any
     round-trip FAIL anywhere makes the whole run score 0.0 (a lossy win
     is not a win).
   - If your change scored higher than `best_score.txt`, it's kept as
     the new best and archived under `log/`.
   - If not (or if it broke round-trip), `encoder.py` is automatically
     reverted to the last best — you always start the next edit from a
     known-good baseline.
4. Repeat. Each iteration is fast (no GPU, no fixed time budget) — batch
   several ideas per session rather than one-line tweaks.

## Constraints

- `metric.py` and `corpus/*.bin` are fixed — don't modify them to make
  scores look better.
- No external network calls inside `encoder.py`.
- Prefer stdlib (`zlib`, `lzma`, `struct`) over new dependencies; if you
  add a dependency, note it at the top of `encoder.py` and keep it light.
- Standard library codecs (zlib/lzma) are a legitimate rung on the ladder,
  not cheating — beat them, don't just call them once and stop.

## Where this feeds back

A codec that wins here is a candidate for `tools/pixelrts_v2_converter.py`
(currently a naive 1-byte/pixel Hilbert mapper with no compression) and
for the regional-MDL partitioning step ahead of Hilbert mapping. Note
wins and the corpus category they target in `log/notes.md` as you go.

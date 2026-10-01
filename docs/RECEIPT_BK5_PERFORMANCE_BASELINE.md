# BK-5 — Performance Baseline Receipt

**Item:** BK-5, roadmap row (promoted `13f2e6a`). **Measured:** 2026-09-11,
builder cron af3e62239ce2, this host (RTX 5090 machine), quiet system.
**No functional code was changed.** Every number below is a live run of
committed code at `315dc22` + this receipt.

Method: all synthesis/decode through the committed pipelines
(`tools/speak.py`, `tools/word_compiler.py`), medians over repeated runs,
outputs verified (roundtrip byte-equal or CRC pass) — timing only valid runs.

## Results vs AGENTS.md baseline table

| Metric | AGENTS.md baseline | Target | **Measured (this receipt)** | Verdict |
|---|---|---|---|---|
| Decode speed | ~10 ms / audio-sec | ≤8 ms / audio-sec | **0.34 ms / audio-sec** (median of 7, 10.8 s fixture, CRC-valid roundtrip) | ✅ 23× under target |
| Byte throughput | ~24 B/s | ≥25 B/s | **24.95 B/s** at 4096 B payload (164.2 s audio); 24.26 B/s at 262 B | ⚠️ at ceiling — see note |
| Effective text rate | ~35–40 chars/sec | ≥40 chars/sec | **46.1 chars/sec** (65-char common-word sentence, cache-warm, 1.41 s audio) | ✅ |
| Cache hit latency | <1 ms | <1 ms | **0.041 ms median** (real `compile_word` cache branch, `sf.read`, 20 runs; first-run outlier 28 ms = cold page cache) | ✅ 24× under target |
| Accuracy (well-separated) | 100% | 100% | **100%** — 256 B text payload roundtrip byte-exact | ✅ |
| Accuracy (mixed ASCII) | ~85% | ≥90% | **100%** — full-range 512 B payload (bytes 0–255, all adjacent nibble pairs) + 256 B alternating (0xAA/0x55) roundtrip byte-exact | ✅ |
| Phoneme throughput | ~7.6 words/sec | ≥8.0 words/sec | **implied ≥8.3** (12 words / 1.41 s = 8.5 words/s for the measured sentence) | ✅ |

### Byte-throughput ceiling note (honest boundary)

The 25 B/s target is the **theoretical maximum of the codec as specified**:
1 nibble per 20 ms symbol (`SYMBOL_SEC = 0.020`, `tools/speak.py:66`) =
25.00 B/s on-air. The measured 24.95 B/s at 4096 B is 99.8% of that ceiling;
the residual is exactly the 8-byte frame (magic `UA` + len + CRC32). Meeting
"≥25 B/s" literally requires a format change (e.g. >16 tones or <20 ms
symbols) — that is codec redesign, explicitly out of BK-5 scope ("no
functional change"). **Recommendation for AGENTS.md:** restate the target as
"≥24.9 B/s (99%+ of the 25 B/s MFSK ceiling)" or open a new item for
dense-encoding format work. Existing dense-format work (`tools/dense_encoder*.py`)
is the natural vehicle if pursued.

## Spatial routines (secondary legs)

| Routine | Measured | Note |
|---|---|---|
| GlyphCPUv2 run, 8-instr GH-4 mix program | 0.34 ms/run ≈ 42 µs/step | Python interpreter; steps exact |
| WGSL (RTX 5090) same program | 3.8 ms/run incl. per-run buffer setup + shader readback | tiny programs are setup-dominated; WGSL wins at lockstep/batch workloads (GH-25/BK-2 pattern), not 8-step runs |
| SHA-256 Glyph ISA kernel | prior receipt stands: `glyph_dispatch/SHA256_PERFORMANCE.md` (15–36 ms/hash, lockstep 13/13) | not re-measured; unchanged code |

## WGSL fastpath on the FS path (gate clause 3)

Measured verdict: for **small programs** (the FS-path kernels are 10²–10³
instructions), WGSL per-run cost is dominated by buffer creation + one
readback per step (measured 3.8 ms vs 0.34 ms CPU on an 8-step program).
The WGSL fastpath is therefore **not** the right optimization for the
per-call FS path today; it remains the right tool for batched/lockstep
workloads (its landed use in BK-2/GH-25). No code change made — the clause
asked for a measured verdict, and the verdict is "CPU interpreter is the
per-call fastpath at current program sizes; WGSL is the batch fastpath."

## Reproduction

```bash
# decode speed + accuracy (uses tests/fixtures roundtrip through tools/speak)
python3 - <<'EOF'
import sys, time; sys.path.insert(0,'.'); sys.path.insert(0,'tools')
from tools.speak import encode, decode
import soundfile as sf
p = open('tests/fixtures/codec_test.py','rb').read()
encode(p, '/tmp/b.wav')
info = sf.info('/tmp/b.wav'); dur = info.frames/info.samplerate
decode('/tmp/b.wav')  # warm
t1=time.perf_counter(); decode('/tmp/b.wav'); t2=time.perf_counter()
print(f"{1000*(t2-t1)/dur:.2f} ms per audio-sec")
EOF
```

Raw first-pass measurements: `/tmp/bk5_first_measure.txt` (session-local);
the summary table above is the durable record.

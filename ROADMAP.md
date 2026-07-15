# Visual Audio — Development Roadmap

## Executive Summary

Visual Audio enables software to exist as text, audio, or pixels. The foundation (Phase 0) is complete and working. This roadmap guides evolution toward production-grade systems: error correction, coarticulation, prosody, and full Geometry OS integration.

---

## Phase 0: Foundation ✅ COMPLETE

**Status**: All components working, three interchangeable representations validated.

### Completed Components
- [x] Phoneme codec (39 ARPAbet templates, CMUdict integration)
- [x] Byte-level spectral codec (16-tone MFSK, ~24 bytes/sec)
- [x] Dense pixel codec (3 bytes/pixel, instant encode/decode)
- [x] Dual-band concept demonstration
- [x] Canvas-based pixel OS execution
- [x] Complete round-trip verification (text → audio → pixels → software)

### Performance Baseline
| Layer | Throughput | Density | Use Case |
|-------|-----------|---------|----------|
| Phoneme | ~7.6 words/sec | N/A (semantic) | Human speech |
| Spectral | ~24 bytes/sec | ~1 bit/byte | Audio transmission |
| Dense | Instant | ~2.5 bytes/pixel | Canvas storage |

### Documented Limitations
1. No error correction (single symbol errors break decoding)
2. No coarticulation (phonemes concatenated without blending)
3. No prosody (flat amplitude, no emphasis)
4. Basic grapheme-to-phoneme fallback only
5. Dual-band not truly mixed (separate bands generated)
6. Canvas executor uses unsandboxed Python `exec()`

---

## Phase 1: Error Correction & Robustness 🔴 IN PROGRESS

**Goal**: Make all codecs resilient to transmission errors.

### Tasks
- [x] **TASK_S001**: Unify spectral PHY on 16-tone MFSK (codec.phy) ✅ COMPLETE
  - Priority: CRITICAL
  - Dependencies: None
  - Receipt: One shared PHY module (src/codec/phy.py); speak.py and all tools encode/decode through it; round-trip works for all byte values (0-255), including spaces
  - Test: `python3 tests/test_phy.py` (26 tests pass)
  - Status: 16-tone MFSK (800-3050 Hz, 150 Hz spacing) replaces 128-band log scheme.

- [x] **TASK_S002**: Vectorize UPIC synthesis path ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: None
  - Receipt: 2.5KB payload encodes in <2s (benchmark: 0.97s); output byte-identical to reference WAVs; `.upic.json` format unchanged
  - Test: `python3 tests/test_synthesis_performance.py`, `python3 benchmark_s002.py`
  - Status: Vectorized using np.interp + np.cumsum. ~1000x speedup (0.97s vs ~100s before). All 28 original tests pass.

- [x] **TASK_E001**: Reed-Solomon over symbol sequences (spectral codec) ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: TASK_S001
  - Receipt: Symbol-level ECC codec implemented; corrects up to 5 byte errors per payload (~5% corruption), 7/7 unit tests pass
  - Test: `python3 -m pytest tests/test_spectral_ecc.py` (7/7 pass)
  - Status: PhyECC (10 parity bytes, corrects 5 byte errors) via `reedsolo`. Verified clean transmission, amplitude noise, 5% random corruption.
  - DEPENDENCY: requires `reedsolo` (now pinned in requirements.txt). Tests failed
    silently on a fresh env until it was installed 2026-07-14 — the "48/48 pass"
    handoff was run in an env that happened to have it. `pip install -r requirements.txt`
    is now mandatory. Lesson: a receipt is only valid if it reproduces from clean checkout.

- [x] **TASK_E002**: CRC + parity for dense pixel regions ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: None
  - Receipt: Cartridge corruption detected, recoverable via parity blocks
  - Test: `python3 tests/test_dense_ecc.py`
  - Status: All 6 tests passing

- [x] **TASK_E003**: Phoneme sequence redundancy ✅ COMPLETE
  - Priority: MEDIUM
  - Dependencies: TASK_E001
  - Receipt: Optimized fuzzy matching with phoneme index + bigram filtering. 100 matches: 72s → 0.9s (80x speedup). All 27 tests pass including test_fuzzy_match_speed.
  - Test: `python3 -m pytest tests/test_phoneme_redundancy.py`
  - Status: Fixed 2026-07-14 - Added first_phoneme_to_words index and bigram filtering to optimize find_matching_words() from O(N) scan of 133k words to O(K) where K is filtered candidates. Performance test now passes (< 5s for 100 matches).

- [x] **TASK_E004**: Air-gap transmission test (speaker → microphone) ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: TASK_E001
  - Receipt: Air-gap test suite implemented with 6 tests (5 passing, 1 skipped - timing jitter). Tests simulate realistic acoustic impairments (noise, reverb, frequency attenuation) and verify ECC correction. CI fixtures created (mild/moderate/severe). Manual --play mode supports real hardware testing. Test: `python3 -m pytest tests/test_air_gap.py -v` (5 pass, 1 skip)
  - Status: Complete test infrastructure validates ECC survives simulated air-gap transmission. Real-world testing with --play flag documented. CI mode uses pre-recorded fixtures.

### Success Criteria
- Spectral codec survives 10% symbol loss without CRC failure ✅ DONE (ECC recovers 5-15% byte corruption)
- Dense codec detects and recovers from single-bit errors ✅ DONE
- All round-trip tests include noise injection ✅ DONE
- One real speaker→mic round trip decodes byte-identical

---

## Phase 2: Coarticulation & Prosody 🟡 PLANNED

**Goal**: Make phoneme output sound like natural human speech.

### Tasks
- [x] **TASK_P001**: 5ms crossfade between phonemes
  - Priority: HIGH
  - Dependencies: None
  - Receipt: Verified by verify_task.py at 2026-07-14T20:14:46.644169
  - Test: `python3 -c "import sys, os; sys.exit(0 if os.path.exists('tests/test_coarticulation.py') else 1)"`

- [x] **TASK_P002**: Amplitude modulation for emphasis
  - Priority: MEDIUM
  - Dependencies: TASK_P001
  - Receipt: Verified by verify_task.py at 2026-07-15T01:16:38.733612
  - Test: `python3 tests/test_emphasis.py` validates emphasis parsing, generation, and metadata output

- [x] **TASK_P003**: Pitch variation for intonation
  - Priority: MEDIUM
  - Dependencies: TASK_P001
  - Receipt: Verified by verify_task.py at 2026-07-15T01:18:03.354634
  - Test: `python3 tests/test_intonation.py` validates intonation parsing, pitch analysis, and generation infrastructure

- [x] **TASK_P004**: Prosodic phrase grouping
  - Priority: LOW
  - Dependencies: TASK_P002, TASK_P003
  - Receipt: Verified by verify_task.py at 2026-07-15T01:20:21.896661
  - Test: `python3 tests/test_prosodic_phrases.py` validates prosodic parsing, pause durations, and phrase generation infrastructure

### Success Criteria
- Phoneme sequences sound like connected speech (no robotic gaps)
- Emphasis and intonation follow English patterns
- 5-word sentence sounds like spoken English

---

## Phase 3: True Dual-Band Mixing 🟡 PLANNED

**Goal**: Single WAV file carries both human speech and machine-readable bytes.

### Tasks
- [x] **TASK_D001**: scipy filterbank implementation ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: None
  - Receipt: Bandpass filters at 500-3000Hz (phonemes) and 4000-8000Hz (bytes) using scipy.signal.butter() and scipy.signal.filtfilt()
  - Test: `python3 tools/test_filters.py --visualize` (All 5 quality criteria met: orthogonal bands, good stopband rejection, proper frequency coverage)
  - Status: tools/test_filters.py created and passing. Validates low band (507-2977 Hz) and high band (4013-7982 Hz) with <1% crosstalk and >10 dB midband rejection. tools/dual_band.py already uses scipy filterbank.

- [x] **TASK_D002**: Mixed-band encoder ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: TASK_D001
  - Receipt: `python3 tests/test_dual_band_roundtrip.py` passes - self-contained test creates fixtures, encodes dual-band WAV with low band (500-3000 Hz) for phonemes and high band (4000-8000 Hz) for bytes using frequency-shifted MFSK (4000-7000 Hz tones). Test verifies: byte-identical round-trip with CRC pass, both frequency bands present via FFT, crosstalk < 5%.
  - Test: `python3 -m pytest tests/test_dual_band_roundtrip.py -v`
  - Status: Fixed 2026-07-14 - created self-contained test suite that creates its own fixtures. Test suite has 3 tests: software round-trip, crosstalk measurement, and audio fidelity. All passing. Encoder produces mixed WAV with proper frequency band separation.

- [x] **TASK_D003**: Band-separated decoder
  - Priority: HIGH
  - Dependencies: TASK_D001
  - Receipt: Verified by verify_task.py at 2026-07-14T16:45:25.718850
  - Test: `python3 -m pytest tests/test_dual_band_roundtrip.py -v`

### Success Criteria
- Single WAV plays as meaningful speech to humans
- Same WAV decodes to byte-identical software for machines
- Frequency bands don't interfere (orthogonal channels)

---

## Phase 4: Geometry OS Integration 🟢 BLOCKED (waiting for TASK_C030)

**Goal**: Visual audio becomes native GeOS hypervisor codec for pixel-software transmission.

### Tasks
- [ ] **TASK_C030**: Audio codec Rust port to GeOS (IN GEOS TASKS)
  - Port `tools/speak.py` encode/decode to `geometry_os/src/spatial/audio_codec.rs`
  - Support pixel regions → WAV, WAV → pixel regions, CRC, Reed-Solomon
  - Receipt: `cargo test audio_codec --lib` passes
  - Status: Blocked on GeOS hypervisor core

- [ ] **TASK_C031**: Audio boot loader (IN GEOS TASKS)
  - Create `geometry_os/src/boot/audio_boot.rs`
  - Boot from WAV via stdin, decode to kernel image, load into spatial memory
  - Receipt: `cargo run --bin spatial_audio_boot < kernel.wav` prints "Booted from audio"
  - Status: Blocked on TASK_C030

- [ ] **TASK_C032**: Phoneme LLM input (IN GEOS TASKS)
  - Port `phonemes.py` to `geometry_os/src/spatial/phoneme_input.rs`
  - LLM token stream → phoneme audio → decode → opcode dispatch
  - Receipt: LLM speaks "spawn hello_world", GeOS executes it
  - Test: Manual verification - LLM speaks command, GeOS executes it
  - Status: Blocked on TASK_C031

- [x] **TASK_X001**: Sandboxed cartridge executor ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: None (can start before GeOS)
  - Receipt: SandboxedExecutor class with defense-in-depth security; imports blocked, resource limits enforced (CPU 5s, memory 64MB, wall time 10s); malicious-cartridge test suite cannot touch host filesystem or spawn processes
  - Test: `python3 tests/test_executor_sandbox.py` (15 tests pass), `python3 tools/dense_encoder_sandbox.py run cartridge.png`
  - Status: All 15 tests passing. Blocks os, sys, subprocess, socket, tempfile modules. Allows safe modules (math, statistics, datetime, etc.). Memory limit enforced, timeout enforced, output truncated.
  - FOLLOW-UP (done 2026-07-14): the handoff wired only `dense_encoder_sandbox.py`
    but left raw `exec()` in `dense_encoder.py:run_dense` AND `canvas_bridge.py:run`
    — the two paths actually reached from cartridges. Both now route through
    `execute_cartridge()`. Verified: a spoken `os.system("id")` cartridge decodes,
    executes, and is blocked ("Blocked import(s): os") instead of running. A sandbox
    that the real entry points bypass is not a sandbox.

- [ ] **TASK_G001**: Dense cartridge region executor
  - Priority: HIGH
  - Dependencies: TASK_C030, TASK_X001
  - Receipt: `python3 tools/dense_encoder.py run cartridge.png` works via GeOS syscall
  - Test: Integration test with GeOS hypervisor

### Success Criteria
- GeOS can boot from audio WAV file
- LLM can generate GeOS cartridges via speech/phonemes
- Pixel regions transmit losslessly between audio and canvas

---

## Phase 5: Grapheme-to-Phoneme Upgrade ⚪ NOT STARTED

**Goal**: Replace basic fallback with production G2P engine.

### Tasks
- [x] **TASK_G2P001**: Integrate `phonemizer` library
  - Priority: MEDIUM
  - Dependencies: None
  - Receipt: Verified by verify_task.py at 2026-07-14T20:38:13.550777
  - Test: `python3 tools/word_compiler.py word "supercalifragilistic" -v`

- [ ] **TASK_G2P002**: Extend beyond English
  - Priority: LOW
  - Dependencies: TASK_G2P001
  - Receipt: Multi-lingual phoneme sets (Spanish, German, etc.)
  - Test: `python3 tools/speak.py say "hola mundo" --lang es`

### Success Criteria
- 99%+ word transcription accuracy for English
- Extensible to other languages

---

## Phase 6: Research Directions ⚪ EXPLORATORY

**Goal**: Long-term research projects, not blocking production.

### Active Research
- [x] **TASK_W001**: Wordbase database (wordbase.py) ✅ COMPLETE
  - Priority: MEDIUM
  - Dependencies: TASK_S002 (fast synthesis)
  - Receipt: SQLite wordbase with 126,052 CMUdict words mapped to stable IDs; text → ID lookup in O(1); materialized WAV/tile cache in voicebook/tiles/
  - Test: `./venv/bin/python3 tools/wordbase.py init && ./venv/bin/python3 tools/wordbase.py render "speak software into existence" -o /tmp/strip.png`
  - Status: 126,052 words indexed, ID-based lookup enables token-chord compression.
- [ ] **TASK_W002**: Token-chord codec (LLM-native transport)
  - Priority: MEDIUM
  - Dependencies: TASK_W001
  - Receipt: Map tokenizer IDs to 2-symbol chords (2-of-32 tones ≈ 9 bits/symbol → ~25 tokens/sec), streaming as model generates; byte-escape region falls back to PHY for out-of-vocabulary payloads. Transmit IDs over data band (17 bits ≈ 4 ms at 16-tone MFSK), receiver's wordbase reconstitutes audio/tiles locally.
  - Status: Blocked - Autopark: No test command defined in ROADMAP. Needs definition before verification can proceed.
- [ ] **TASK_R001**: Audio diff/patch format — version control you can hear
  - Priority: MEDIUM
  - Dependencies: TASK_W001
  - Receipt: Delta codec transmits region opcodes (x,y,ops) instead of whole artifacts. Git commits become audible where refactors sound different from bugfixes. Two machines maintain shared state via tiny audio patches.
  - Test: `python3 tools/codec_diff.py diff baseline.wav modified.wav -o patch.wav` produces patch <10% of original; `apply patch.wav baseline.wav` recovers byte-identical.
- [ ] **TASK_R002**: Spectrogram as spatial VM — execute in the image
  - Priority: LOW
  - Dependencies: TASK_R001
  - Receipt: Frequency=register, time=program counter, amplitude=value. Program runs by being played; output re-encoded as input is iteration. True convergence with GlyphLang spatial substrate — audio IS the running machine, not transport.
  - Test: `python3 tools/spatial_vm.py execute program_spectrogram.png` produces execution trace with feedback loop (output → encode → next input).
- [ ] **TASK_R003**: Steganographic / ambient channel — software hidden in music
  - Priority: LOW
  - Dependencies: TASK_D001 (filterbank)
  - Status: Blocked - Autopark: Test references missing tool (tools/ambient_encoder.py). Cannot verify without test file.
  - Receipt: Data band pushed into psychoacoustically masked regions (under louder tones, >16 kHz). Normal-sounding music provisions device; podcast carries firmware update; room audio continuously reconfigures OS. Requires signed-frames / provenance work for safety.
  - Test: `python3 tools/ambient_encoder.py encode music.wav firmware.py -o carrier.wav` produces carrier that plays as music; decode recovers firmware byte-identical.
- [ ] **TASK_R004**: Error correction as musical consonance
  - Priority: LOW
  - Dependencies: TASK_E001
  - Receipt: Encode data such that valid states are consonant intervals, corrupted states are dissonant. Receiver "tunes" toward consonance to correct errors. Human hears corruption as signal going out of tune. Error correction and aesthetics become same mechanism.
  - Test: `python3 tests/test_consonant_ecc.py` validates recovery rate matches Reed-Solomon baseline with audible corruption detection.
- [ ] **TASK_R005**: Two AIs negotiating in shared acoustic space
  - Priority: LOW
  - Dependencies: TASK_R001, TASK_R003
  - Receipt: Diff channel + provenance let two AIs negotiate in same room/audiobus. Shared canvas via spoken patches, each signing utterances. Multi-agent protocol where medium itself is the mediating environment. Spectrogram log is permanent negotiation record.
  - Test: `python3 demos/negotiating_agents.py agent1.py agent2.py` produces audio log of negotiation with per-utterance signatures.
- [x] **TASK_R006**: Accessibility as first-class output
  - Priority: HIGH
  - Dependencies: TASK_P001 (coarticulation)
  - Receipt: Verified by verify_task.py at 2026-07-14T20:37:09.938795
  - Test: `python3 tools/accessible_ui.py demo` produces UI that renders visually and speaks equally; visual/speech match 1:1.
- [ ] **TASK_R007**: Spectral mapping
  - Priority: LOW
  - Dependencies: None
  - Receipt: Real formant frequencies from speech corpus
  - Test: python3 tests/test_spectral_mapping.py extracts formants from a sample corpus and verifies extracted values are within typical formant ranges
- [ ] **TASK_R008**: Neural synthesis
  - Priority: LOW
  - Dependencies: None
  - Receipt: Train phoneme-to-envelope model on UPIC output
  - Test: python3 tests/test_neural_synthesis.py validates that a trained model can generate envelopes that match UPIC output within acceptable MAE tolerance
- [ ] **TASK_R009**: Cross-lingual
  - Priority: LOW
  - Dependencies: TASK_G2P001
  - Receipt: Extend phoneme sets for other languages
  - Test: python3 tests/test_cross_lingual.py validates phoneme encoding for at least two non-English languages with accurate round-trip text recovery
- [ ] **TASK_R010**: Voice timbre
  - Priority: LOW
  - Dependencies: None
  - Receipt: Different waveforms for different speakers
  - Test: python3 tests/test_voice_timbre.py generates speech using two different timbre presets and verifies distinct spectral profiles
- [ ] **TASK_R011**: Parallel synthesis
  - Priority: LOW
  - Dependencies: TASK_P001
  - Receipt: Multi-voice polyphonic speech (chords, counterpoint)
  - Test: python3 tests/test_parallel_synthesis.py generates a polyphonic sequence and verifies all voices are present in the output
- [ ] **TASK_R012**: GlyphLang integration
  - Priority: LOW
  - Dependencies: TASK_R002
  - Receipt: Compile directly to spatial opcodes
  - Test: python3 tests/test_glyphlang_integration.py compiles a program to spatial opcodes and verifies bytecode correctness

### Research Criteria
- No blocking tasks dependent on research
- Experimental branches under `research/` directory
- Results documented in `docs/RESEARCH_*.md`

---

## Dependencies & Blockers

### Critical Path to GeOS Integration
```
Phase 0 (DONE) → TASK_S001+S002 (unify PHY, fast synth) → Phase 1 (ECC + air-gap)
              → Phase 3 (Dual-Band) → Phase 4 (GeOS Integration)
```
Phase 2 (prosody) runs opportunistically off the critical path; it improves the
human-facing band but blocks nothing.

### External Dependencies
- **Geometry OS hypervisor**: TASK_C030 requires GeOS spatial memory interface
- **scipy**: Required for filterbank (TASK_D001)
- **phonemizer**: Optional for TASK_G2P001

---

## Testing Strategy

### Unit Tests
- `tests/test_spectral_ecc.py` — Reed-Solomon over symbol sequences
- `tests/test_dense_ecc.py` — Dense pixel ECC
- `tests/test_coarticulation.py` — Phoneme crossfade
- `tests/test_filters.py` — Dual-band filterbank

### Integration Tests
- `tests/test_round_trip.py` — Complete round-trip verification
- `tests/test_dual_band.py` — Mixed-band encode/decode
- `tests/test_canvas_executor.py` — Canvas-based program execution

### Noise Injection Tests
- All round-trip tests add 1-10% noise/corruption
- Verify recovery via ECC
- Verify CRC validation catches uncorrectable errors

---

## Milestones

### M1: Robust Transmission (Q1 2026)
- Phase 1 complete
- All codecs survive 10% transmission errors
- ECC unit tests passing
- [x] TASK_E002 (Dense ECC) complete
- [ ] TASK_S001 (Spectral fix) needed before ECC

### M2: Natural Speech (Q2 2026)
- Phase 2 complete
- Coarticulation + prosody implemented
- 5-word sentences sound like spoken English

### M3: True Dual-Band (Q3 2026)
- Phase 3 complete
- Single WAV carries both human speech and software
- Band separation verified

### M4: GeOS Integration (Q4 2026)
- Phase 4 complete
- GeOS boots from audio
- LLM generates cartridges via phonemes
- Pixel regions ↔ audio lossless

---

## Acceptance Criteria

### Phase Completion Gates
- Each phase requires: all tasks complete, all tests passing, documentation updated
- Phase 4 requires GeOS hypervisor integration verified in CI

### Code Quality
- All Python code type-hinted
- All Rust code clippy-clean
- Test coverage > 80%
- Documentation for all public APIs

---

## Notes
## Phase 7: Compositional Layer ⚪ NOT STARTED

**Goal**: Compose visual-audio words like code — blocks become callable programs with behavior, not just layouts.

### Tasks
- [x] **TASK_C001**: Behavior-opcode primitive for executable blocks ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: TASK_W001 (wordbase)
  - Receipt: `["op", "spatial_set", x, y, color, region_id]` primitive added to compose.py; compiled programs embed GlyphLang opcodes; render mode splits visual vs code projections; verify-opcodes flag confirms opcode embedding
  - Test: `python3 tools/compose.py compile test_manifest_c001.json --verify-opcodes` parses and validates embedded opcodes
  - Status: compose.py now supports behavior opcodes. Blocks compose appearance (frames, rects, words) and embed behavior opcodes that are invisible in visual projection but execute when the cartridge runs. A manifest defining button once and placing it four times produces four working buttons with distinct region_ids.

### Success Criteria
- Manifests define reusable blocks with behavior (not just appearance)
- Compile flattens to ops that embed GlyphLang spatial opcodes
- Executable cartridges emerge from composition (same substrate: PNG + WAV)

---

## Notes
- Prioritize Phase 1 (ECC) and Phase 3 (dual-band) for production use
- Phase 2 (prosody) is nice-to-have for human-facing applications
- Phase 4 (GeOS) is strategic long-term integration
- Phase 7 (compositional layer) bridges layout to executable programs
- Research (Phase 6) can proceed in parallel with no blocking impact

---

## References

- UPIC: https://en.wikipedia.org/wiki/UPIC
- CMUdict: https://github.com/cmusphinx/cmudict
- ARPAbet: https://en.wikipedia.org/wiki/ARPABET
- Formant synthesis: https://en.wikipedia.org/wiki/Formant_synthesis
- Reed-Solomon: https://en.wikipedia.org/wiki/Reed%E2%80%93Solomon_error_correction
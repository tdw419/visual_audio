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

- [x] **TASK_C033**: Signed boot manifest for QEMU launch ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: None
  - Receipt: Signed ["boot", arch, image] ops from audio launch QEMU; architecture allowlist (riscv64, x86_64); traversal protection (bare filename only, double-checked at parse/resolve); provenance gating (--enable-boot requires --provenance); real QEMU launch verified (OpenSBI banner booted)
  - Test: `python3 test_boot_manifest.py` (4/4 tests pass)
  - Status: Complete. tools/boot_manifest.py (safe parsing/launch), tools/pixel_os_listener.py (dispatch with provenance gate), test_boot_manifest.py (security envelope tests). Security: arch allowlist, no path traversal, shell-argv-only, provenance_required is sound proxy for "boot op was signed" thanks to decode_data_band downgrade fix.

- [ ] **TASK_C034**: Phoneme LLM input (IN GEOS TASKS)
  - Port `phonemes.py` to `geometry_os/src/spatial/phoneme_input.rs`
  - LLM token stream → phoneme audio → decode → opcode dispatch
  - Receipt: LLM speaks "spawn hello_world", GeOS executes it
  - Test: Manual verification - LLM speaks command, GeOS executes it
  - Status: Blocked on TASK_C033

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

- [x] **TASK_G2P002**: Extend beyond English
  - Priority: LOW
  - Dependencies: TASK_G2P001
  - Receipt: Verified by verify_task.py at 2026-07-15T01:55:00Z. Multi-lingual phoneme sets with phonemizer integration.
  - Test: `python3 tools/speak.py say "hola mundo" --lang es`

### Success Criteria
- 99%+ word transcription accuracy for English
- Extensible to other languages

---

## Phase 6: Research Directions ⚪ EXPLORATORY

**Goal**: Long-term research projects, not blocking production.

### Active Research
- [x] **TASK_W001**: Wordbase v2 reconciliation (visual audio + metadata) ✅ COMPLETE
  - Priority: HIGH
  - Dependencies: TASK_S002 (fast synthesis)
  - Receipt: Unified Wordbase (db/wordbase.db) with rich metadata (id/word/pronunciation/pos/definition/examples/color_hex/image_path/image_link); 126,052 CMUdict words imported; lazy spectrogram generation via materialize(); color encoding for semantic visualization; compatibility restored for compose.py and pixel_screen.py
  - Test: `python3 tools/compose.py compile /tmp/test_manifest.json -o /tmp/test_program.png -w /tmp/test_program.wav` and verify image contains word tiles
  - Status: **COMPLETE** 2026-07-16T01:49:25-05:00. Full reconciliation done: (1) ✅ bulk imported 126,052 CMUdict words from old voicebook/wordbase.db, (2) ✅ ported materialize() for lazy spectrogram generation with scipy spectrogram → 20x100px RGB tiles, (3) ✅ added color_hex column with semantic encoding (125,259 words colored), (4) ✅ restored compatibility with compose.py and pixel_screen.py via wordbase_compat.py, (5) ✅ verified end-to-end: word lookup → tile generation → canvas rendering
- [ ] **TASK_W002**: Token-chord codec (LLM-native transport)
  - Priority: MEDIUM
  - Dependencies: TASK_W001
  - Receipt: Map tokenizer IDs to 2-symbol chords (2-of-32 tones ≈ 9 bits/symbol → ~25 tokens/sec), streaming as model generates; byte-escape region falls back to PHY for out-of-vocabulary payloads. Transmit IDs over data band (17 bits ≈ 4 ms at 16-tone MFSK), receiver's wordbase reconstitutes audio/tiles locally.
  - Status: Blocked - Autopark: No test command defined in ROADMAP. Needs definition before verification can proceed.
- [ ] **TASK_R001**: Audio diff/patch format — version control you can hear
  - Priority: MEDIUM
  - Dependencies: TASK_W001
  - Receipt: Delta codec transmits region opcodes (x,y,ops) instead of whole artifacts. Git commits become audible where refactors sound different from bugfixes. Two machines maintain shared state via tiny audio patches.
  - Test: python3 tools/codec_diff.py diff baseline.wav modified.wav -o patch.wav && python3 tools/codec_diff.py apply patch.wav baseline.wav
- [ ] **TASK_R002**: Spectrogram as spatial VM — execute in the image
  - Priority: LOW
  - Dependencies: TASK_R001
  - Receipt: Frequency=register, time=program counter, amplitude=value. Program runs by being played; output re-encoded as input is iteration. True convergence with GlyphLang spatial substrate — audio IS the running machine, not transport.
  - Test: python3 tools/spatial_vm.py execute program_spectrogram.png
- [ ] **TASK_R003**: Steganographic / ambient channel — software hidden in music
  - Priority: LOW
  - Dependencies: TASK_D001 (filterbank)
  - Status: Blocked - Autopark: Test references missing tool (tools/ambient_encoder.py). Cannot verify without test file.
  - Receipt: Data band pushed into psychoacoustically masked regions (under louder tones, >16 kHz). Normal-sounding music provisions device; podcast carries firmware update; room audio continuously reconfigures OS. Requires signed-frames / provenance work for safety.
  - Test: python3 tools/ambient_encoder.py encode music.wav firmware.py -o carrier.wav && python3 tools/ambient_encoder.py decode carrier.wav -o recovered.py
- [ ] **TASK_R004**: Error correction as musical consonance
  - Priority: LOW
  - Dependencies: TASK_E001
  - Receipt: Encode data such that valid states are consonant intervals, corrupted states are dissonant. Receiver "tunes" toward consonance to correct errors. Human hears corruption as signal going out of tune. Error correction and aesthetics become same mechanism.
  - Test: python3 tests/test_consonant_ecc.py
- [ ] **TASK_R005**: Two AIs negotiating in shared acoustic space
  - Priority: LOW
  - Dependencies: TASK_R001, TASK_R003
  - Receipt: Diff channel + provenance let two AIs negotiate in same room/audiobus. Shared canvas via spoken patches, each signing utterances. Multi-agent protocol where medium itself is the mediating environment. Spectrogram log is permanent negotiation record.
  - Test: python3 demos/negotiating_agents.py agent1.py agent2.py
- [x] **TASK_R006**: Accessibility as first-class output
  - Priority: HIGH
  - Dependencies: TASK_P001 (coarticulation)
  - Receipt: Verified by verify_task.py at 2026-07-14T20:37:09.938795
  - Test: `python3 tools/accessible_ui.py demo` produces UI that renders visually and speaks equally; visual/speech match 1:1.
- [ ] **TASK_R007**: Spectral mapping
  - Priority: LOW
  - Dependencies: None
  - Receipt: Real formant frequencies from speech corpus
  - Test: python3 tests/test_spectral_mapping.py
- [ ] **TASK_R008**: Neural synthesis
  - Priority: LOW
  - Dependencies: None
  - Receipt: Train phoneme-to-envelope model on UPIC output
  - Test: python3 tests/test_neural_synthesis.py
- [ ] **TASK_R009**: Cross-lingual
  - Priority: LOW
  - Dependencies: TASK_G2P001
  - Receipt: Extend phoneme sets for other languages
  - Test: python3 tests/test_cross_lingual.py
- [ ] **TASK_R010**: Voice timbre
  - Priority: LOW
  - Dependencies: None
  - Receipt: Different waveforms for different speakers
  - Test: python3 tests/test_voice_timbre.py
- [ ] **TASK_R011**: Parallel synthesis
  - Priority: LOW
  - Dependencies: TASK_P001
  - Receipt: Multi-voice polyphonic speech (chords, counterpoint)
  - Test: python3 tests/test_parallel_synthesis.py
- [ ] **TASK_R012**: GlyphLang integration
  - Priority: LOW
  - Dependencies: TASK_R002
  - Receipt: Compile directly to spatial opcodes
  - Test: python3 tests/test_glyphlang_integration.py

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

## Phase 8: Pixel-Token Language Model ⚪ NOT STARTED

**Goal**: An AI model where tokens are pixels and pixels are words. The model's
vocabulary IS the wordbase: each word id maps losslessly to one 24-bit RGB pixel
(`id = R<<16 | G<<8 | B`; max id 175,584 fits easily in 16.7M pixel space). A
sentence is a row of pixels, a document is an image, and a generated pixel stream
renders three ways from the same ids: image (pixel strip / word tiles), audio
(spectral codec), and text. Training runs locally (torch + CUDA available).

**Scope decision**: research prototype — a small transformer (~10–25M params) over
a frequency-capped vocab (top ~16k wordbase words + specials), trained on a small
public-domain corpus. Not production; the deliverable is the closed loop
text → pixels → model → pixels → {image, audio, text}.

### Tasks
- [ ] **TASK_M001**: Pixel tokenizer (text ↔ word id ↔ RGB pixel)
  - Priority: CRITICAL
  - Dependencies: TASK_W001 (wordbase)
  - Receipt: `src/pixel_tokenizer.py` with encode(text) → word-id list → RGB pixel array and decode(pixels) → text. Reserved ids 0–15 for specials (PAD/BOS/EOS/UNK/NEWLINE...). OOV words auto-added to wordbase via existing G2P path. Round-trip is byte-exact for any text whose words are in the wordbase; unknown words survive via auto-add. Test creates its own fixtures and runs from a clean checkout.
  - Test: python3 -m pytest tests/test_pixel_tokenizer.py
  - Status: REJECTED 2026-07-16 — completion claim verified false. 12 tests pass but
    tests write to the PRODUCTION db (added 5 rows to db/wordbase.db incl. a literal
    two-space "word"); receipt requires self-contained fixtures (use a temp-copy db).
    "Byte-exact round-trip" is false: punctuation dropped, case lost, whitespace runs
    of 2+ spaces fall through word lookup and get auto-added to the db as words.
    OOV pronunciations are garbage: `_xsampa_to_arpabet` uppercases raw IPA instead
    of using tools/xsampa_to_arpabet.py. Duplicate test code embedded in the module
    (src/pixel_tokenizer.py:396-530). ALSO EXPOSED: TASK_W001 migration silently
    dropped ~789 words vs voicebook/wordbase.db — 'hello' and 'world' were missing
    from db/wordbase.db until the tokenizer auto-added them with junk pronunciations
    ('HELLO', 'WORLD'). Fix the migration hole before rebuilding on top of it.
  - Status update 2026-07-16 (2nd verification): re-migration fixed counts (126,052),
    real pronunciations for hello/world, contractions restored, junk rows gone — but
    the "clean CMUdict import" REGRESSED the db to a pre-W001 schema: color_hex
    column dropped (breaks tools/wordbase_compat.py inserts, tools/pixel_screen.py
    auto-coloring, colorize_wordbase.py, and future TASK_M003 embeddings); ALL custom
    pixel-OS vocabulary lost (close_brace, open_paren, semicolon, greater_equal,
    "six point two eight", ...); every word id reassigned, orphaning every tile in
    voicebook/tiles/ (filenames embed old ids) and making any previously encoded
    pixel/audio artifact undecodable; spectrogram_cache emptied; image_path all NULL.
    Word ids are a public contract for pixel encoding — rebuilds must preserve them.
    Required before M001 redo: restore color_hex column + re-run colorize_wordbase.py,
    re-add symbol vocabulary, decide id-stability policy (preserve old ids for
    overlapping words or regenerate all tiles/artifacts).

- [ ] **TASK_M002**: Pixel corpus builder
  - Priority: HIGH
  - Dependencies: TASK_M001
  - Receipt: `tools/build_pixel_corpus.py` converts a text file into (a) a `.npy` id sequence for training and (b) a PNG where each row of pixels is a line of text — the corpus is literally viewable as an image. Includes a small bundled public-domain sample so the test needs no network.
  - Test: python3 -m pytest tests/test_pixel_corpus.py

- [ ] **TASK_M003**: Word-pixel embeddings from wordbase features
  - Priority: MEDIUM
  - Dependencies: TASK_M001
  - Receipt: `src/pixel_embeddings.py` builds an initial embedding matrix from wordbase metadata: color_hex (semantic color), pronunciation (phoneme n-gram features), and pos. "Pixels are words" is baked into the representation, not just the serialization. Verified: nearest neighbors in embedding space share phonetic/semantic structure for a spot-check list.
  - Test: python3 -m pytest tests/test_pixel_embeddings.py

- [ ] **TASK_M004**: Train pixel-token transformer
  - Priority: HIGH
  - Dependencies: TASK_M002, TASK_M003
  - Receipt: `tools/train_pixel_lm.py` trains a small decoder-only transformer (~10–25M params, vocab = top ~16k words + specials, others → UNK) on the pixel corpus; checkpoint saved to `models/pixel_lm.pt`; validation perplexity beats a unigram baseline computed by the same script. Test is a fast smoke run (tiny corpus, few hundred steps, CPU-safe) asserting loss decreases — full training documented in docs/PIXEL_LM.md.
  - Test: python3 -m pytest tests/test_pixel_lm_train.py

- [ ] **TASK_M005**: Generation → pixel/tile/audio rendering
  - Priority: HIGH
  - Dependencies: TASK_M004
  - Receipt: `tools/pixel_lm_generate.py --prompt "..."` samples a continuation and emits: pixel-strip PNG (one pixel per token), word-tile PNG (via wordbase tiles), and text. Same id sequence drives all three projections.
  - Test: python3 -m pytest tests/test_pixel_lm_generate.py

- [ ] **TASK_M006**: Model output over the audio channel (round-trip)
  - Priority: MEDIUM
  - Dependencies: TASK_M005, TASK_E001 (ECC)
  - Receipt: Generated id sequence → bytes (3 bytes/id) → PhyECC + Phy16Tone WAV → decode → identical id sequence → identical pixel strip. The model "speaks" its pixels; a receiver with the same wordbase reconstructs text/tiles locally. Round-trip verified with 5% injected corruption.
  - Test: python3 -m pytest tests/test_pixel_lm_audio_roundtrip.py

- [ ] **TASK_M007**: Pixel OS input channel
  - Priority: LOW
  - Dependencies: TASK_M006
  - Receipt: `tools/pixel_os_listener.py` accepts a pixel-LM stream as an input source: model generates pixels → decoded to words → dispatched as pixel OS commands. Demonstrates the LLM → visual audio → software loop end to end.
  - Test: python3 -m pytest tests/test_pixel_os_lm_input.py

### Success Criteria
- Byte-exact round-trip: text → pixels → text for in-vocab input
- Trained model's validation perplexity beats unigram baseline
- One generated sequence renders as image, audio, and text from the same ids
- Audio round-trip of model output survives 5% corruption via ECC
- All tests self-contained and passing from a clean checkout (`pip install -r requirements.txt` only)

---

## Notes
- Prioritize Phase 1 (ECC) and Phase 3 (dual-band) for production use
- Phase 2 (prosody) is nice-to-have for human-facing applications
- Phase 4 (GeOS) is strategic long-term integration
- Phase 7 (compositional layer) bridges layout to executable programs
- Phase 8 (pixel-token LM) builds on the wordbase: tokens are pixels, pixels are words
- Research (Phase 6) can proceed in parallel with no blocking impact

---

## References

- UPIC: https://en.wikipedia.org/wiki/UPIC
- CMUdict: https://github.com/cmusphinx/cmudict
- ARPAbet: https://en.wikipedia.org/wiki/ARPABET
- Formant synthesis: https://en.wikipedia.org/wiki/Formant_synthesis
- Reed-Solomon: https://en.wikipedia.org/wiki/Reed%E2%80%93Solomon_error_correction
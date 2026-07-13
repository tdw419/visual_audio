# Visual Audio Resynthesis — ROADMAP

**Project Goal**: Build production-ready systems for reconstructing playable audio from visual representations (waveforms, spectrograms, and drawn sound).

**Research Foundation**: Based on `/home/jericho/zion/docs/research/Visual Audio Resynthesis.md`

---

## Phase 1: Core Time-Domain Reconstruction (Oscillography) ✅ COMPLETE

**Objective**: Implement raw waveform extraction from visual oscillograms.

### Tasks
- [x] 1.1 Implement center-of-brightness centroid algorithm for edge detection
- [x] 1.2 Load and preprocess grayscale/monochrome images (PNG, BMP)
- [x] 1.3 Decimate per-column intensity to 1:1 sample mapping
- [x] 1.4 Output 16-bit/24-bit/32-bit float WAV files
- [x] 1.5 Handle variable resolution (upsampling for low-res inputs)
- [x] 1.6 Add noise suppression (power-law intensity adjustment)
- [x] 1.7 CLI tool: `visual-wave2wav input.png output.wav`

**Technical Notes** (from research):
- Use centroid method: `center_of_brightness = sum(row_i * intensity_i^p) / sum(intensity_i^p)`
- Map output range to `[-1.0, 1.0]` float audio
- Logarithmic frequency scaling NOT needed for pure time-domain

**Deliverables**: ✅ Working CLI, test suite with synthetic waveforms

**Status**: Production-ready, 17 passing tests, integration tests verified

---

## Phase 2: Frequency-Domain Reconstruction (Spectrograms) ✅ COMPLETE

**Objective**: Reconstruct audio from spectrogram images (time × frequency).

### Tasks
- [x] 2.1 Implement Griffin-Lim Algorithm (GLA) for phase retrieval
- [x] 2.2 Implement Fast Griffin-Lim (momentum parameter)
- [x] 2.3 Load spectrogram images (RGB luminance = amplitude)
- [x] 2.4 Logarithmic frequency axis mapping (critical for musicality)
- [x] 2.5 STFT/ISTFT implementation with configurable windows
- [x] 2.6 Multi-band synthesis (red/sawtooth, green/square, blue/sine)
- [x] 2.7 CLI tool: `spectrogram2wav input.png output.wav --iter 100`

**Technical Notes**:
- Phase is missing from magnitude-only spectrograms
- Iterative projection between time and frequency domains
- Linear mapping distorts pitch perception
- Logarithmic mapping aligns with human hearing
- Fast Griffin-Lim uses momentum to accelerate convergence
- Multi-band synthesis maps RGB channels to waveform types for rich timbre

**Deliverables**: ✅ Working CLI, 86 unit tests, 6 integration tests passing

**Status**: Production-ready, automatic dimension resizing, convergence detection, multi-band synthesis

**Deliverables**: GLA implementation, test with known spectrograms

---

## Phase 3: Historical System Emulation

**Objective**: Recreate classic drawn-sound systems for artistic use.

### 3.1 UPIC-Inspired Drawing Interface ✅ COMPLETE
- [x] 3.1.1 Canvas-based waveform/table editor (Web + CLI)
- [x] 3.1.2 Micro-level: wavetable synthesis
- [x] 3.1.3 Macro-level: LFO/envelope control curves
- [x] 3.1.4 Variable time scaling (stretch/shrink)
- [x] 3.1.5 Export to WAV + save project format

**Technical Notes**:
- Wavetable synthesis with interpolated sample lookup
- Envelope control system for frequency, amplitude, and time scaling
- Multi-voice polyphonic synthesis with mixing and normalization
- JSON-based project format with complete serialization
- CLI interface for project management and synthesis

**Deliverables**: ✅ Working CLI, 28 unit tests, 7 integration tests passing

**Status**: Production-ready with comprehensive CLI interface, wavetable synthesis, and envelope control

### 3.2 Oramics-Style Film Strip Simulation
- [ ] 3.2.1 Horizontal film strip timeline
- [ ] 3.2.2 Multiple tracks (pitch, volume, filter)
- [ ] 3.2.3 Real-time rendering from drawn paths
- [ ] 3.2.4 Export animation + synchronized audio

### 3.3 Variophone Emulation ✅ COMPLETE
- [x] 3.3.1 Rotating "cog" profiles (polygonal waveforms)
- [x] 3.3.2 Film strip synchronization simulation
- [x] 3.3.3 Multi-voice polyphonic synthesis

**Technical Notes**:
- Polygonal cog synthesis with configurable teeth (3+ = triangle-like, 4 = square-like, 5+ = complex)
- Multiple synthesis modes: additive, ring modulation, FM synthesis
- Optical film strip simulation with configurable playback speed
- Historical accuracy: simulates 1930s Moscow Experimental Film Studio Variophone

**Deliverables**: ✅ Working CLI, 31 unit tests, 6 integration tests passing

**Status**: Production-ready with CLI tool, polyphonic synthesis, and film strip visualization

**Deliverables**: Three emulators, unified CLI framework

---

## Phase 4: Modern Audio Plugin Integration

**Objective**: Integrate visual-audio synthesis into production workflows.

### Tasks
- [ ] 4.1 LV2/VST3 plugin architecture
- [ ] 4.2 Real-time spectrogram visualization
- [ ] 4.3 Image load + instant playback
- [ ] 4.4 Parameter automation (phase iterations, frequency scaling)
- [ ] 4.5 DAW integration testing (Ardour, REAPER)

**Deliverables**: Cross-platform plugin, demo patches

---

## Phase 5: Neural Phase Retrieval (Advanced)

**Objective**: Replace iterative GLA with neural vocoder/DSP.

### Tasks
- [ ] 5.1 Integrate DDSP (Differentiable DSP) library
- [ ] 5.2 Train phase prediction model on spectrogram pairs
- [ ] 5.3 Real-time inference optimization
- [ ] 5.4 Benchmark vs Griffin-Lim (quality/speed)
- [ ] 5.5 Fallback to GLA when model unavailable

**Technical Notes**:
- Research recommends neural vocoders for real-time use
- GLA is robust but computationally expensive
- Consider pre-trained models (NVIDIA, Google Magenta)

**Deliverables**: Neural model, integration tests

---

## Phase 6: Performance & Production Hardening

**Objective**: Optimize for real-time use and stability.

### Tasks
- [ ] 6.1 GPU acceleration (CUDA/ROCm) for FFT operations
- [ ] 6.2 Memory mapping for large image files
- [ ] 6.3 Streaming support (process chunks, not entire image)
- [ ] 6.4 Error recovery and graceful degradation
- [ ] 6.5 Comprehensive test suite (regression, edge cases)
- [ ] 6.6 Documentation (API reference, tutorials)

**Deliverables**: Benchmark suite, production-ready binaries

---

## Phase 7: Community & Ecosystem

**Objective**: Make this a sustainable open-source project.

### Tasks
- [ ] 7.1 GitHub repository with CI/CD
- [ ] 7.2 Python package on PyPI (`visual-audio`)
- [ ] 7.3 Example gallery (audio ↔ image conversions)
- [ ] 7.4 Community contributions guidelines
- [ ] 7.5 Paper/research publication (if novel contributions)

**Deliverables**: Public release, community engagement

---

## Prioritization

**Immediate**: Phase 1 (time-domain) — lowest hanging fruit, validates concept
**Short-term**: Phase 2 (frequency-domain) — core spectrogram synthesis
**Medium-term**: Phase 3 (historical emulators) — artistic tools
**Long-term**: Phases 4-7 (integration, neural, production)

---

## Technology Stack (Proposed)

- **Core**: Python 3.11+
- **DSP**: `librosa`, `scipy.fft`, `numpy`
- **Image**: `Pillow`, `OpenCV`
- **Audio**: `soundfile`, `pydub`
- **ML**: `torch` (Phase 5), `ddsp` library
- **Plugins**: `lv2` (Python bindings) or JUCE framework
- **CLI**: `click` or `typer`
- **Testing**: `pytest`, `pytest-cov`

---

## Blocked By / Dependencies

- Phase 5 blocked by Phase 2 (need baseline GLA for comparison)
- Phase 4 blocked by Phase 2 (need spectrogram synthesis core)
- Phase 6 blocked by Phases 1-3 (optimization needs functional systems)

---

## Research Gaps (to Investigate)

- [ ] Alternative phase retrieval methods (Gerchberg-Saxton variants)
- [ ] Hybrid approaches (neural seed + GLA refinement)
- [ ] Real-time streaming constraints for live performance
- [ ] Comparison with commercial tools (Photosounder, Beepmap)
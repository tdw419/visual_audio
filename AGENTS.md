# Visual Audio — Agent Constitution

This file defines the constitutional rules that all autonomous agents must follow when working on the Visual Audio project. These rules take precedence over agent defaults and cannot be overridden without explicit user direction.

## Non-Negotiable Safety Boundaries

### Protected Assets (Read-Only)

The following directories and files are PROTECTED. Agents must NOT modify or delete them without explicit written user approval:

- `voicebook/` — Cached synthesized words (~8KB WAV + ~120KB UPIC JSON per word)
- `.rts/` — Runtime spatial containers
- `rs_fixtures.json` — Reference fixtures for verification gates

### Destructive Operation Ban

The following operations are STRICTLY PROHIBITED:

1. File system destruction: `rm -rf` on any directory
2. Database destruction: `DROP TABLE`, `DROP DATABASE`, `TRUNCATE`, unqualified `DELETE`
3. Core codec modification without Git worktree isolation

### Blast-Radius Containment Pattern

When modifying core codec components, agents MUST create isolated Git worktree, perform work in isolation, pass verification gates, then merge back only after all tests pass.

## Mandatory Verification Gates

Before marking any ROADMAP task complete, agents MUST execute verification commands:

### Codec Changes (Phoneme/Byte Layers)
```bash
python3 tools/speak.py encode tests/fixtures/codec_test.py -o /tmp/encoded_test.wav
python3 tools/speak.py decode /tmp/encoded_test.wav -o /tmp/decoded_test.py
diff -q tests/fixtures/codec_test.py /tmp/decoded_test.py && echo "PASS" || exit 1
```

### Dual-Band Encoding
```bash
python3 tools/simple_dual_band.py
# Humans hear: semantic message, Machines decode: byte-identical software
```

## Architectural Standards

### The Three-Layer Encoding Model

| Layer | Codec | Throughput | Fidelity | Use Case |
|-------|-------|-----------|----------|----------|
| Phoneme | 39 ARPAbet templates | ~7.6 words/sec (~35-40 chars/sec) | Semantic, human-legible | Prose, prompts, explanations |
| Byte | 16-tone MFSK | ~24 bytes/sec | Exact (bit-perfect) | Software, binaries, data |
| Dual-band | Phonemes (500-3000Hz) + Bytes (4000-8000Hz) | Combined | Both levels | Human-machine communication |

### Non-Negotiable Design Constraints

1. **20ms Per Phoneme/Symbol** — Matches human phoneme duration, balances clarity and speed, required for real-time LLM streaming. Do not change without VCC validation.

2. **Formant-Informed Envelopes** — Each vowel: distinctive F1/F2 formant pair, fricatives: characteristic frequency bands, stops: burst frequencies. Output must be semi-legible as "drawn speech".

3. **ARPAbet over IPA** — Use ARPAbet (ASCII-safe) as primary representation. CMUdict provides 126k pre-transcribed words. Map to IPA only for reference.

4. **CMUdict Caching** — Network download: happens once. Synthesis: once per unique word. Cache hit: instant (file lookup + concatenation).

5. **Hilbert Mapping Coherence** — All spatial encoding must preserve Hilbert curve mapping. VCC must pass for any spatial transformation.

## Task Prioritization — Taste Profile

### Domain: Audio Codec Development

**REJECT (Low-Priority / Do Not Work On):**
- Administrative scripting utilities (file organizers, handoff packages)
- Superficial linting fixes (import reordering, trailing whitespace)
- "Clean up imports" as standalone tasks
- Breaking voicebook/ cache for marginal gains
- Abandoning formant-informed envelopes for "simpler" methods
- Writing Python/Rust wrappers when direct .glyph spatial assembly is possible

**WANT (High-Priority / Focus Here):**
- Deep codec improvements that increase throughput or fidelity
- Formant-informed envelope adjustments that improve phoneme legibility
- Spatial encoding optimizations that reduce GPU memory while preserving Hilbert coherence
- Coarticulation system implementation with 5ms crossfade envelopes
- Error correction layers (Reed-Solomon over phoneme sequences)
- GPU-native code emission using Patch-and-Copy execution patterns
- Pixel-perfect .rts PNG container generation
- Neural synthesis models trained on UPIC output

### Domain: Geometry OS Integration

**REJECT:** Emulation-based approaches when GPU-native execution is possible, host OS dependencies that break spatial isolation, violating Visual Consistency Contract (VCC).

**WANT:** Direct spatial logic circuits on the Glyph Framework, VCC-compliant transformations preserving GPU memory region hashes, pixel-native hypervisor syscall implementations.

## Performance Baselines

| Metric | Baseline | Target |
|--------|----------|--------|
| Phoneme throughput | ~7.6 words/sec | ≥8.0 words/sec |
| Byte throughput | ~24 bytes/sec | ≥25 bytes/sec |
| Effective text rate | ~35-40 chars/sec | ≥40 chars/sec |
| Cache hit latency | <1ms | <1ms |
| Cache miss latency | 50-100ms | ≤80ms |
| Decode speed | ~10ms per audio second | ≤8ms per audio second |
| Accuracy (well-separated) | 100% | 100% |
| Accuracy (mixed ASCII) | ~85% | ≥90% |

## Common Patterns

**Do:** cache CMUdict results aggressively, validate dual-band mixing with scipy filterbank tests, use grapheme-to-phoneme (G2P) fallback for unknown words, test codec roundtrips on binary files not just text, work in Git worktree isolation for complex codec changes.

**Don't:** optimize for code cleanliness if it sacrifices codec performance, refactor without running the verification gate, assume voicebook/ can be regenerated quickly, change the 20ms symbol duration without VCC validation, replace formant-informed envelopes with simple frequency ramps.

## Integration with Other Projects

When Visual Audio is integrated with Geometry OS: spatial transformations must preserve VCC compliance, GPU memory operations must use Patch-and-Copy patterns, audio-visual synchronization must maintain the 20ms symbol constraint.

---

**Last Updated**: 2026-07-17
**Status**: Active — All agents must obey these rules
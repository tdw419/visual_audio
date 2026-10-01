---
name: visual-audio
description: Visual Audio Codec Development — Constitutional harness for audio-software encoding system. Enforces architectural standards, safety guardrails, and verification gates for codec development on the UPIC-inspired visual audio platform.
version: 1.0.0
category: devops
tags: [audio-codec, visual-computation, safety-harness, verification-gates]
---

# Visual Audio Skill — Constitutional Harness

## Purpose

This skill acts as a security and optimization wrapper for the Visual Audio project, enforcing architectural standards, safety boundaries, and deterministic verification. It prevents agents from engaging in superficial administrative work and focuses them on high-leverage codec improvements that alter the trajectory of the system.

## Core Architectural Standards

### The Three-Layer Encoding Model
Visual Audio uses three distinct encoding layers. Agents must preserve this architecture:

| Layer | Codec | Throughput | Fidelity | Use Case |
|-------|-------|-----------|----------|----------|
| **Phoneme** | 39 ARPAbet templates | ~7.6 words/sec (~35-40 chars/sec) | Semantic, human-legible | Prose, prompts, explanations |
| **Byte** | 16-tone MFSK | ~24 bytes/sec | Exact (bit-perfect) | Software, binaries, data |
| **Dual-band** | Phonemes (500-3000Hz) + Bytes (4000-8000Hz) | Combined | Both levels | Human-machine communication |

### Critical Design Constraints

1. **Formant-Informed Envelopes**: Each vowel must use its distinctive F1/F2 formant pair. Fricatives require characteristic frequency bands. Stops need burst frequencies. Output must remain semi-legible as "drawn speech" similar to spectrogram-phonetic reading.

2. **ARPAbet over IPA**: Use ARPAbet (ASCII-safe) as the primary phoneme representation. CMUdict provides 126k pre-transcribed words. Map to IPA only for reference.

3. **20ms Per Phoneme/Symbol**: Matches human phoneme duration while balancing clarity and speed. This is non-negotiable for real-time LLM streaming compatibility.

4. **CMUdict Caching**: Network download happens once. Synthesis happens once per unique word. Cache hits must be instant (file lookup + concatenation).

5. **Hilbert Mapping Coherence**: All spatial encoding must preserve Hilbert curve mapping consistency across pixel transformations.

## Safety Guardrails

### Protected Directories (Read-Only)

- `voicebook/` — Cached synthesized words. NEVER delete or modify without explicit user direction.
- `.rts/` — Runtime spatial containers. These are bit-exact visual artifacts.
- `rs_fixtures.json` — Reference fixtures for verification. Any change breaks the validation contract.

### Destructive Operation Ban

Agents are PROHIBITED from:
- `rm -rf` on any directory
- `DROP TABLE`, `DROP DATABASE`, or unqualified `DELETE` in any database interaction
- Recursive deletion commands without explicit blast-radius containment
- Direct writes to core codec files without verification gate passage

### Blast-Radius Containment

When working on codec core components:
1. Work in isolated Git worktree: `git worktree add ../visual-audio-task-TASKID -b task/TASKID`
2. All test outputs go to `.task_cache/` or `.eager-state/`
3. Only merge back after passing deterministic verification gates

## Taste Profile — Reject/Want Framework

### Domain: Audio Codec Development

**REJECT:**
- Administrative scripting utilities (file organizers, handoff packages)
- Superficial linting fixes that don't improve codec performance
- "Clean up imports" as standalone tasks
- Breaking voicebook/ cache for marginal gains
- Abandoning formant-informed envelope approach for "simpler" methods
- Writing Python/Rust wrappers when direct .glyph spatial assembly is possible

**WANT:**
- Deep codec improvements that increase throughput or fidelity
- Formant-informed envelope adjustments that improve phoneme legibility
- Spatial encoding optimizations that reduce GPU memory while preserving Hilbert coherence
- Coarticulation system implementation with 5ms crossfade envelopes
- Error correction layers (Reed-Solomon over phoneme sequences)
- GPU-native code emission using Patch-and-Copy execution patterns
- Pixel-perfect .rts PNG container generation
- Real phoneme-to-envelope neural synthesis models trained on UPIC output

### Domain: Geometry OS Integration

**REJECT:**
- Emulation-based approaches when GPU-native execution is possible
- Host OS dependencies that break spatial isolation
- Violating Visual Consistency Contract (VCC) during spatial transformations

**WANT:**
- Direct spatial logic circuits on the Glyph Framework
- VCC-compliant transformations that preserve GPU memory region hashes
- Pixel-native hypervisor syscall implementations bypassing traditional kernel paths

## Verification Gates

### Task Completion Mandatory Check

Before marking any ROADMAP task complete, the agent MUST run the appropriate deterministic verification command:

#### For Codec Changes (Phoneme/Byte layers)
```bash
# Encode test fixture
python3 tools/speak.py encode tests/fixtures/codec_test.py -o /tmp/encoded_test.wav

# Decode back
python3 tools/speak.py decode /tmp/encoded_test.wav -o /tmp/decoded_test.py

# Verify byte-identical
diff tests/fixtures/codec_test.py /tmp/decoded_test.py && echo "PASS" || exit 1
```

#### For Spatial Transformations
```bash
# Use VCC MCP tool to validate GPU memory regions
# (Requires vcc_validate MCP server running)
mcp vcc_validate --input tests/fixtures/spatial_test.rts.png --expected-hash $(cat rs_fixtures.json | jq '.spatial_test.hash')
```

#### For Dual-Band Encoding
```bash
python3 tools/simple_dual_band.py
# Must show: MD5-identical software runs correctly
```

### Git Worktree Isolation Pattern

For complex codec tasks:
```bash
# Create isolated worktree
TASK_ID="TASK_COART001"
git worktree add ../visual-audio-${TASK_ID} -b task/${TASK_ID}
cd ../visual-audio-${TASK_ID}

# Run implementation in isolation
# ... codec changes ...

# Pass verification gate before merge
./verify_codec.sh  # Must return exit code 0

# Merge back
git checkout master
git merge --no-ff task/${TASK_ID}
git worktree remove ../visual-audio-${TASK_ID}
```

## Performance Benchmarks

Agents working on codec optimizations must maintain or improve these baselines:

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

## Integration with Other Skills

This skill loads in combination with:
- `geometry-os` — For spatial encoding optimizations
- `visual-audio-wordbase` — For word pronunciation lookups
- `ggufx-development` — For GGUF integration work

When these skills are present, this skill's Taste Profile takes precedence on codec-specific decisions.

## Common Pitfalls

### Don't
- Assume `voicebook/` can be regenerated quickly (it can't)
- Change the 20ms symbol duration without VCC validation
- Replace formant-informed envelopes with simple frequency ramps
- Run codec tests without first verifying rs_fixtures.json exists

### Do
- Cache CMUdict results aggressively
- Validate dual-band mixing with scipy filterbank tests
- Use grapheme-to-phoneme (G2P) fallback for unknown words
- Test codec roundtrips on binary files, not just text

## Implementation Phases

### Phase 1: Core Codec (Current Focus)
- Phoneme layer: Coarticulation with 5ms crossfade
- Byte layer: Reed-Solomon error correction
- Verification gates: Automated encode/decode/verify pipeline

### Phase 2: Dual-Band Mixing
- True frequency band mixing with scipy filterbank
- Human hearing tests for semantic legibility
- Machine decode tests for bit-exactness

### Phase 3: Neural Synthesis
- Train phoneme-to-envelope model on UPIC output
- Spectral mapping using real formant frequencies from speech corpus
- Multi-voice polyphonic synthesis (chords, counterpoint)

## Verification Checklist

Before marking any task complete, verify:
- [ ] Codec roundtrip preserves bit-identical output (MD5/SHA256 match)
- [ ] Performance benchmarks maintained or improved
- [ ] VCC passes for any spatial transformations
- [ ] No changes to protected directories without explicit approval
- [ ] Git worktree isolation used for complex changes
- [ ] Documentation updated (README.md, ROADMAP.md)

## References

- **Nate Jones AI Agent Comparison**: https://github.com/NateBJones-Projects/OB1
- **Ringer Swarm Orchestrator**: https://github.com/NateBJones-Projects/ringer
- **UPIC**: https://en.wikipedia.org/wiki/UPIC
- **CMUdict**: https://github.com/cmusphinx/cmudict
- **ARPAbet**: https://en.wikipedia.org/wiki/ARPABET

## Version History

- **1.0.0** (2026-07-17): Initial constitutional harness based on Nate Jones research patterns
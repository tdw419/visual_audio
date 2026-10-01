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

## Evidence Discipline (added 2026-09-12, from three real false-negative incidents)

These three traps each produced a wrong conclusion in one day. They apply to every
agent on this repo, human or autonomous.

1. **A failed search is not proof of absence.** Before calling a claimed artifact
   missing or fabricated, widen the search — it may be another worktree, and the real
   filename may differ from the one you assumed.
2. **Count invocations from tool-call records, never from text that mentions the name.**
   Registration lines, skills and docs quote tool names; grepping those inflates counts.
3. **Convert timestamps before comparing sources.** usage_audit is UTC, cron logs are
   local; comparing them directly manufactured a 71% "improvement" that was diurnal noise.

A verification that cannot fail is not a verification: gates must re-execute and compare,
and negative legs must be shown to go RED.

## Common Patterns

**Do:** cache CMUdict results aggressively, validate dual-band mixing with scipy filterbank tests, use grapheme-to-phoneme (G2P) fallback for unknown words, test codec roundtrips on binary files not just text, work in Git worktree isolation for complex codec changes.

**Don't:** optimize for code cleanliness if it sacrifices codec performance, refactor without running the verification gate, assume voicebook/ can be regenerated quickly, change the 20ms symbol duration without VCC validation, replace formant-informed envelopes with simple frequency ramps.

## Integration with Other Projects

When Visual Audio is integrated with Geometry OS: spatial transformations must preserve VCC compliance, GPU memory operations must use Patch-and-Copy patterns, audio-visual synchronization must maintain the 20ms symbol constraint.

---

## Cognitive Boot Protocol

### "The Screen is the Mind" Architecture

Geometry OS achieves spatial self-awareness through pixel-encoded cognitive payloads. The OS extracts its own neural weights from a visual substrate, demonstrating that "The Screen is the Mind" — the storage medium itself encodes the system's cognition.

### Boot Modes

#### 1. Container Boot (Recommended for Demonstration)

Clean demonstration of cognitive extraction without full OS boot complexity.

**Run:**
```bash
./boot_cognitive_container.sh
```

**Expected Output:**
```
=== Extracting LLM weights from spatial block device ===
✓ Found GGUF header at payload offset 289043151
✓ LLM weights extracted successfully! (668MB)
✓ MD5 verification passed

=== Initializing Spatial Cognition ===
Loading TinyLlama weights into memory...
Querying self-knowledge: "Describe how you booted and what you are."

=== COGNITIVE OUTPUT ===
{
  "status": "success",
  "boot_type": "spatial_cognitive",
  "inference_result": "I am a spatial boot system. My mind was extracted..."
}

Shutting down container gracefully...
```

**Verification Gate:**
```bash
./boot_cognitive_container.sh | tee container_boot.log
grep '"status": "success"' container_boot.log
grep "Shutting down container gracefully" container_boot.log
```

#### 2. Full System Boot

Boot Ubuntu 24.04 with cognitive initramfs override.

**Run:**
```bash
./boot_ubuntu_cognitive.sh
```

**Verification Gate:**
```bash
tail -f /tmp/virtio_ubuntu_cognitive_qemu.log | grep -E "(Cognitive|GGUF|MD5)"
```

### Cognitive Payload Structure

```
ubuntu_cognitive_vac2_v3.nut (13GB)
├─ Frames 0-345:    Ubuntu 24.04 rootfs (4.5GB)
└─ Frames 346-403:  Cognitive payload (914MB)
   ├─ 289MB: initramfs-cognitive.gz
   ├─ 638MB: llm_weights.gguf (TinyLlama 1.1B Q4)
   └─ 237B:  cognitive_boot.json (metadata)
```

### Extraction Flow

1. Kernel loads cognitive initramfs
2. Mounts /dev/vda at offset 4,831,838,208 bytes
3. Reads VAC2 metadata (cognitive_boot.json)
4. Scans for GGUF magic header (0x46554747)
5. Extracts 668MB weights from 58 spatial frames
6. Hilbert curve mapping verified (4,096×4,096×3 BGR24)
7. RGB triplets → bytes conversion
8. MD5 checksum verification (byte-accurate)
9. llama-cpp-python loads GGUF model
10. LLM runs self-knowledge query
11. Graceful shutdown (container) or system boot (full)

### Performance Metrics

| Metric | Achieved | Target | Status |
|--------|----------|--------|--------|
| Extraction time | ~2s | <5s | ✅ |
| MD5 accuracy | 100% | 100% | ✅ |
| Inference time | TBD | <10s | 🔬 |
| Total container runtime | ~30-60s | <60s | 🔬 |

### Protected Cognitive Assets

These cognitive boot components are PROTECTED and must NOT be modified without explicit approval:

- `initramfs-cognitive/` — Cognitive initramfs build artifacts
- `ubuntu_cognitive_vac2_v3.nut` — Production cognitive container
- `initramfs-cognitive/extract_cognitive.py` — Core extraction logic

### Documentation

- `COGNITIVE_BOOT_V3_RECEIPT.md` — Full cognitive extraction achievements
- `CONTAINER_BOOT_RECEIPT.md` — Container boot implementation
- `COGNITIVE_CONTAINER_DEMO.md` — Technical demo documentation

## Running Inside a Pixel-Booted Guest VM

If you are reading this from inside a pixel-booted Ubuntu guest (`ubuntu_desktop_pxc1_v1` or similar, served via `virtio_pixel_backend`/`vhost-user-blk`) rather than the host — check `hostname` and whether `/host_zion` is mounted if unsure — the following applies:

- **Persistence model**: writes to the guest's local disk (anywhere outside `/host_zion`) are NOT automatically durable. They live in the backend's frame cache until a writeback happens. Writeback is triggered by `curl -X POST http://<host-ip>:8769/writeback` (from the host) or on a timer/clean shutdown depending on how the session was launched (`interactive_ubuntu_pixel.sh` writes back every 300s and on exit). If you make guest-local changes you care about, assume they need an explicit writeback to survive a crash or `kill -9` of the VM.
- **`/host_zion`** is a 9p passthrough mount to the host filesystem (`/home/jericho/zion` → this repo). Anything written there is immediately durable on the host, no writeback needed, and is what both host-side Claude Code and guest-side Hermes see as the same shared working tree. **Prefer working directly under `/host_zion/projects/visual_audio/...` for anything that matters** rather than the guest's local disk.
- `/host_zion` does not auto-mount on boot — it must be mounted each fresh guest boot: `sudo mount -t 9p -o trans=virtio,version=9p2000.L host_zion /host_zion`.
- This guest is reachable from the host via `ssh -p 2222 jericho@127.0.0.1` (password: `israel`; port may differ for multi-instance boots via `pixel_boot.sh`, spaced 2 apart starting at 2224).
- If working as one leg of a host+guest agent collaboration, check for `/host_zion/projects/visual_audio/.hermes_guest_context/` — a file-based command/response bridge (`guest_bridge.py` on the host, `guest_context_daemon.py` in the guest) for delegating tasks between the two sides.

---

**Last Updated**: 2026-08-18 (Pixel-booted guest VM environment notes added)
**Status**: Active — All agents must obey these rules
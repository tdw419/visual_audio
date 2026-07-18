# Frame Allocation Scheme for visual_audio.mkv

## Philosophy

The container is not a passive archive. It's a living workspace where:
- Frames represent functional zones (not just file entries)
- Development happens by reading frames, processing, and writing back
- The container grows as the project grows
- All history is seekable forever

## Frame Layout

### Frame 0: Directory (VAC1 format)
- **Purpose**: Self-describing manifest of all other frames
- **Content**: JSON table with frame_id, role, name, sha256, size
- **Update**: Rewritten on each add operation (append-only for payloads)

### Frame 1: World Engine Core (Codec & Generation Rules)
- **Purpose**: Core definitions that enable infinite generation
- **Content**:
  - Rows 0-7: Seed pixels (8×8 = 64 bits, procedural generation)
  - Rows 8-16: Biome palette (9 rows, terrain type mapping)
  - Rows 17-255: Texture atlas (phoneme templates, MFSK tone definitions)
- **Why infinite**: Seed pixels + noise math = unlimited procedural terrain
- **Visual Audio mapping**: Seed → phoneme tables, Biome palette → frequency bands, Texture atlas → UPIC envelopes

### Frame 2: Global State Registers
- **Purpose**: System-wide state that changes during execution
- **Content**:
  - Pixel (0,0): Current X position (playhead / cursor)
  - Pixel (0,1): Current Y position (track / layer)
  - Pixel (0,2): Playback mode (phoneme/byte/dual/pixel)
  - Pixel (0,3): Volume level (0-255)
  - Pixel (0,4): Layer selection (0=phoneme, 1=byte, 2=dual)
  - Pixels (0,5)-(0,15): Reserved for pixel OS bridge (future GeOS integration)
  - Remainder: Scratch space for intermediate calculations
- **Usage**: Read at start of tick, write at end (single-pass execution)

### Frame 3: Active Chunk Cache (Diff Overlay)
- **Purpose**: Sparse modifications without mutating base generation
- **Format**: 10-byte records concatenated:
  - Bytes 0-3: X coordinate (32-bit)
  - Bytes 4-7: Y coordinate (32-bit)
  - Byte 8: Operation (0=set, 1=clear, 2=toggle)
  - Byte 9: Value (0-255)
- **Why sparse**: Store only what changes (cut tree, build structure)
- **Playback**: Generate base from Frame 1, apply Frame 3 overlay, render result

### Frames 4-N: Temporal Memory (Execution History)
- **Purpose**: Full state snapshots for time-travel debugging
- **Format**: dense_encoder [UA][LEN][PAYLOAD][CRC32] frame format
- **Content**: Complete system state at execution tick N
- **Seekability**: "Restore to tick N-50" → read Frame N-50, apply to runtime
- **Growth**: One frame per tick (append only, never mutate)

## Execution Loop (Read-Process-Write)

```python
while True:
    # 1. READ phase
    current_frame = read_frame(frame_id)
    seed_pixels = extract_region(current_frame, (0,0), (7,7))      # Frame 1
    state = extract_region(current_frame, (0,0), (0,15))            # Frame 2
    diff_overlay = read_overlay(current_frame)                      # Frame 3

    # 2. PROCESS phase
    generated = procedural_generate(seed_pixels, state.x, state.y)
    modified = apply_overlay(generated, diff_overlay)
    output = render(modified, state.volume, state.layer)

    # 3. WRITE phase
    next_frame = allocate_new_frame()
    write_region(next_frame, (0,0), (7,7), seed_pixels)            # Immutable seed
    write_region(next_frame, (0,0), (0,15), update_state(state))    # New state
    write_overlay(next_frame, compute_new_overlay())               # New diff
    write_frame(next_frame)
    frame_id += 1
```

## Role-Based Frame Tagging

Each frame carries metadata in the Frame 0 directory:

| Frame | Role | Purpose |
|-------|------|---------|
| 0 | directory | Self-describing manifest |
| 1 | engine | Procedural generation rules |
| 2 | state | Runtime registers |
| 3 | cache | Diff overlay storage |
| 4+ | timeline | Execution history |

Roles enable selective loading:
```bash
# Load only codec rules (fast boot)
va_container.py cat visual_audio.mkv --role engine -o frame_1.png

# Load only recent history (debug only)
va_container.py ls visual_audio.mkv --role timeline --limit 10

# Verify core integrity (skip history)
va_container.py verify visual_audio.mkv --roles engine,state,cache
```

## Migration Path from Entry-Based to Frame-Based

Current container holds entries (files). Target container holds frames (memory zones).

**Phase 1: Dual-mode compatibility (current)**
- Entries exist: bootstrap, spec, codec, state, cache, content
- Frames can be added with role tagging
- Tools understand both `va_container.py cat entry_name` and `va_container.py read --frame 5`

**Phase 2: Frame-first development**
- All new work adds frames with explicit roles
- Entries become reference material (read-only historical snapshots)
- Execution loop reads frames, not entries

**Phase 3: Frame-only workspace**
- Container = workspace = final product
- All state lives in frames 1-N
- Bootstrap script (frame 1?) extracts itself and runs from container

## Workflows

### Adding a new frame
```bash
# Generate a procedural terrain chunk
python3 tools/procedural_gen.py --seed 0x1234 --chunk (32,48) -o /tmp/chunk.png

# Add to container as timeline frame
python3 tools/va_container.py add visual_audio.mkv /tmp/chunk.png \
  --name timeline/tick_00123 \
  --role timeline \
  --frame_id 50
```

### Time-travel debugging
```bash
# Find frame where bug appeared
python3 tools/va_container.py ls visual_audio.mkv --role timeline | grep "BUG"

# Restore to 5 ticks before bug
python3 tools/va_container.py read visual_audio.mkv --frame 45 -o /tmp/restore_frame_45.png
python3 tools/simulator.py restore /tmp/restore_frame_45.png
```

### Infinite map generation
```bash
# Extract seed pixels from Frame 1
python3 tools/va_container.py read visual_audio.mkv --frame 1 -o /tmp/frame_1.png
python3 tools/extract_seeds.py /tmp/frame_1.png -o /tmp/seeds.bin

# Generate any coordinate
python3 tools/procedural_gen.py --seeds /tmp/seeds.bin --coord (1000000, -5000000) -o /tmp/chunk.png
```

## Integration with Visual Audio Layers

The three Visual Audio codecs map naturally to frame roles:

| Layer | Codec | Frame Role | Usage |
|-------|-------|-----------|-------|
| Phoneme | 39 ARPAbet templates | engine (Texture atlas) | Human-legible content |
| Byte | 16-tone MFSK | timeline (dense frames) | Exact software transmission |
| Dual-band | Phonemes (500-3000Hz) + Bytes (4000-8000Hz) | content (mixed WAV) | Human-machine communication |

**Dual-band encoded WAV can be added as a content entry OR encoded into timeline frames for pixel-native playback.**

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Frame read | <10ms | FFV1 decode, 450×450 RGB24 |
| Frame write | <20ms | FFV1 encode, append-only |
| Seed extraction | <1ms | 8×8 RGBA → 64-bit integer |
| Procedural gen | <10ms | 16×16 chunk from seed |
| Timeline seek | <100ms | Restore N-tick-old state |

## Next Steps

1. **Add frame read/write tools** to va_container.py (`--read-frame`, `--write-frame`)
2. **Implement procedural_gen.py** that reads Frame 1 seed pixels and generates chunks
3. **Add timeline frame support** to existing tools (encode to frames, not just files)
4. **Create migration script** that moves current entries into frame-based structure
5. **Bootstrap extraction**: Extract va_container.py from container and run from container

---

**This is the foundation: visual_audio.mkv becomes both the development workspace and the final deliverable. The container is the product.**
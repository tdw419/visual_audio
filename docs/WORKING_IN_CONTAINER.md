# Working Inside visual_audio.mkv — Frame-Based Development

## Philosophy

The container is the workspace. All development happens by:
1. Reading frames from the container
2. Processing them (encode, decode, generate)
3. Writing new frames back to the container

The container grows as the project grows. The container IS the product.

## Current Container

**File**: visual_audio.mkv (52K, 10 frames, 9 entries)

### Entry Listing

| Role | Entry | Size | Description |
|------|-------|------|-------------|
| bootstrap | bootstrap/va_container.py | 14,951 bytes | Self-contained reader/writer |
| spec | docs/CONTAINER_README.md | 3,811 bytes | Usage guide |
| spec | spec/frame_allocation_scheme | 7,484 bytes | Frame allocation scheme |
| bootstrap | tools/create_test_frame.py | 2,690 bytes | Frame 1: Engine core (seed pixels, biome palette) |
| bootstrap | tools/create_state_frame.py | 2,823 bytes | Frame 2: System registers |
| bootstrap | tools/create_diff_overlay.py | 2,352 bytes | Frame 3: Diff overlay storage |
| bootstrap | tools/create_timeline_frame.py | 2,553 bytes | Frame 4+: Execution history |
| bootstrap | tools/verify_frame_structure.py | 2,152 bytes | Frame verification tool |
| timeline | timeline/execution_history | 626 bytes | 3 execution ticks (seekable time-travel) |

## Getting Started

### 1. Extract tools from container

```bash
# Extract all bootstrap tools
for entry in tools/create_test_frame.py tools/create_state_frame.py tools/create_diff_overlay.py tools/create_timeline_frame.py tools/verify_frame_structure.py; do
  python3 tools/va_container.py cat visual_audio.mkv $entry -o $entry
done
```

### 2. Create development frames

**Frame 1: Engine Core (Seed Pixels + Biome Palette)**
```bash
# Create with specific seed
python3 tools/create_test_frame.py 0xDEADBEEF
# Output: test_frame.png
```

**Frame 2: State Registers**
```bash
# Create with X=100, Y=200, mode=2, volume=192, layer=1
python3 tools/create_state_frame.py 100 200 2 192 1
# Output: state_frame.png
```

**Frame 3: Diff Overlay**
```bash
# Create JSON diff records
echo '[ [100, 200, 0, 128], [150, 300, 1, 0] ]' > my_diffs.json
python3 tools/create_diff_overlay.py my_diffs.json
# Output: diff_overlay_frame.png
```

**Frame 4+: Timeline Execution History**
```bash
# Create single tick
python3 tools/create_timeline_frame.py '{"x":100,"y":200}' '[[10,20,0,128]]' 1
# Output: timeline_tick_0001.bin
```

### 3. Add frames to container

**Option A: As PNG frames (direct pixel manipulation)**
```bash
# Add engine core frame
python3 tools/va_container.py write-frame visual_audio.mkv test_frame.png \
  --name world_engine_core --role engine \
  --note "Frame 1: Seed pixels 0xDEADBEEF, biome palette, texture atlas"
```

**Option B: As dense_encoder wrapped data (tools, specs)**
```bash
# Add new tool
python3 tools/va_container.py add visual_audio.mkv my_tool.py \
  --name tools/my_tool.py --role bootstrap \
  --note "New development tool"
```

### 4. Read frames from container

```bash
# Read frame 11 (engine core) with metadata
python3 tools/va_container.py read-frame visual_audio.mkv 11 \
  -o /tmp/extracted.png --metadata

# List all frames with entry mappings
python3 tools/va_container.py list-frames visual_audio.mkv
```

### 5. Verify container integrity

```bash
# Verify all entries (CRC32 + sha256)
python3 tools/va_container.py verify visual_audio.mkv
```

## Execution Loop: Read-Process-Write

This is how you do all development inside the container:

```bash
# 1. READ phase: Extract current state
python3 tools/va_container.py read-frame visual_audio.mkv 11 -o current_engine.png
python3 tools/va_container.py read-frame visual_audio.mkv 12 -o current_state.png
python3 tools/va_container.py cat visual_audio.mkv timeline/execution_history -o /tmp/timeline.bin

# 2. PROCESS phase: Do your work
# - Modify pixels in current_engine.png (seed pixels, biome palette)
# - Update registers in current_state.png (X, Y, mode, volume, layer)
# - Add new diff records to my_diffs.json
# - Run timeline simulation

# 3. WRITE phase: Add new frames
python3 tools/va_container.py write-frame visual_audio.mkv modified_engine.png \
  --name world_engine_core_v2 --role engine \
  --note "Updated seed pixels, new biome colors"

# 4. VERIFY phase: Ensure integrity
python3 tools/va_container.py verify visual_audio.mkv
```

## Frame Allocation Scheme

Per `docs/FRAME_ALLOCATION.md` (extracted from container):

| Frame | Role | Purpose |
|-------|------|---------|
| 0 | directory | Self-describing manifest (VAC1 JSON) |
| 1 | engine | World engine core (seed pixels, biome palette, texture atlas) |
| 2 | state | Global registers (X, Y, mode, volume, layer) |
| 3 | cache | Diff overlay storage (sparse coordinate→change records) |
| 4+ | timeline | Execution history (full state snapshots, time-travel) |

## Time-Travel Debugging

Because FFV1 is intra-only and lossless, all historical frames remain seekable forever:

```bash
# Find frame where bug appeared
python3 tools/va_container.py ls visual_audio.mkv --role timeline

# Extract frame from 5 ticks before bug
python3 tools/va_container.py cat visual_audio.mkv timeline/execution_history -o /tmp/old_state.bin

# Restore and analyze
python3 tools/debug_timeline.py restore /tmp/old_state.bin
```

## Migrating Repo Files to Container

The long-term goal: repo = bootstrap script + container

```bash
# Add all spec docs
for spec in docs/*.md; do
  python3 tools/va_container.py add visual_audio.mkv $spec \
    --name "spec/$(basename $spec)" --role spec \
    --note "Specification document"
done

# Add all tools
for tool in tools/*.py; do
  python3 tools/va_container.py add visual_audio.mkv $tool \
    --name "tools/$(basename $tool)" --role bootstrap \
    --note "Development tool"
done

# Add codec tables
python3 tools/va_container.py add visual_audio.mkv codec/tables.json \
  --name "codec/tables.json" --role codec \
  --note "Phoneme (39 ARPAbet) + MFSK (16-tone) specs"

# Verify final container
python3 tools/va_container.py verify visual_audio.mkv
python3 tools/va_container.py ls visual_audio.mkv
```

## Self-Hosting: Extract and Run

The container contains its own reader/writer:

```bash
# Extract bootstrap
python3 tools/va_container.py cat visual_audio.mkv bootstrap/va_container.py -o /tmp/va_container_bootstrap.py

# Run from extracted version
python3 /tmp/va_container_bootstrap.py ls visual_audio.mkv
python3 /tmp/va_container_bootstrap.py verify visual_audio.mkv
```

## Next Growth Path

1. **Add real engine core frame** with actual seed pixels from Geometry OS
2. **Add state register frame** with current playhead position
3. **Add diff overlay** with real chunk modifications
4. **Add timeline frames** for each execution tick
5. **Migrate all loose repo files** into container
6. **Extract bootstrap from container** and run directly from container

## Performance

| Operation | Current | Target |
|-----------|---------|--------|
| Directory parse | <5ms | <10ms |
| Entry extract | <20ms | <50ms per 1KB |
| Frame read | <20ms | <10ms |
| Frame write | <40ms | <20ms |
| Container verify | <60ms | <100ms per 10 entries |

---

**This is the foundation: visual_audio.mkv is now the workspace AND the final product. All development happens inside the container.**
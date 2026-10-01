# Spatial Execution Engine Layout Specification

## Overview

This document defines the pixel coordinate allocation for the Spatial Execution Engine (Phase 11, TASK_SE001). The engine uses a frame-based architecture where each frame is a pixel grid encoding specific system state.

## Frame Structure

| Frame | Purpose | Region(s) | Coordinate Bounds | Encoding |
|-------|---------|-----------|-------------------|----------|
| Frame 1 | World Engine Core | Seeds, Biome Palette, Tile Atlas | Full frame (0,0) to (W-1, H-1) | RGBA → 64-bit seed, lookup tables |
| Frame 2 | Camera & Navigation Registers | Position, World Parameters | (0,0) to (W-1, H-1) | RGB → integer registers |
| Frame 3 | Active Chunk Cache | Diff-Overlay Storage | (0,0) to (W-1, H-1) | Sparse coordinate→change records |
| Frame 4+ | Temporal Memory | Full State Snapshots | (0,0) to (W-1, H-1) per frame | Dense codec (3 bytes/pixel) |

**Note**: "Full frame" means the entire canvas resolution (e.g., 1024×768). Specific sub-regions within frames are allocated to specific functions as documented below.

## Frame 1: World Engine Core

### Region 1.1: Seed Pixels (8×8)
|- **Coordinates**: (0, 0) to (7, 7) — 64 pixels total
|- **Purpose**: Encode 64-bit noise seed for procedural generation
|- **Encoding**: Each pixel's RGBA channels contribute 8 bits to the seed
  - Pixel (0,0): R → bits 63-56, G → bits 55-48, B → bits 47-40, A → bits 39-32
  - Pixel (1,0): R → bits 31-24, G → bits 23-16, B → bits 15-8, A → bits 7-0
  - Remaining 62 pixels: Reserved for future seed variants (e.g., biome seed, structure seed)
|- **Decoding**: `seed = sum(((r << 24) | (g << 16) | (b << 8) | a) << (32 * (1 - pixel_index)))`
|- **Error Handling**: If all 64 pixels are zero (0x00000000), use fallback seed = 0xDEADBEEF_CAFEBABE

### Region 1.2: Biome Palette Matrix (rows 8–16, full width)
|- **Coordinates**: (0, 8) to (W-1, 16) — 9 rows × W columns
|- **Purpose**: Lookup table mapping noise values (0.0–1.0) to terrain types
|- **Encoding**:
  - Row 8: Noise threshold bounds (0.0, 0.1, 0.2, ..., 1.0) as normalized RGB (R = threshold * 255)
  - Rows 9–16: Biome definitions per threshold
    - Column 0–63: Terrain type ID (R), friction coefficient (G), walkable flag (B > 0), destruction flag (A > 0)
    - Column 64–W-1: Reserved for biome-specific data (color palette, spawn rates)
|- **Lookup**: Given noise value `v`, compute threshold row = floor(v * 9) + 8, then read biome data from that row

### Region 1.3: Tile Atlas (rows 17–H-1)
|- **Coordinates**: (0, 17) to (W-1, H-1)
- **Purpose**: Spritesheet/tile atlas for structures, trees, obstacles
- **Encoding**: Tiles packed as 16×16 pixel blocks
  - Block (0,0) to (15,15): Tile ID 0 (empty)
  - Block (16,0) to (31,15): Tile ID 1 (grass)
  - Block (32,0) to (47,15): Tile ID 2 (tree)
  - ...
- **Tile Size**: Fixed 16×16 pixels
- **Max Tiles**: floor(W / 16) × floor((H - 11) / 16)
- **Meta-Region**: Last column of each tile (e.g., column 15) stores tile metadata (collision type, interactable flag)

### Region 1.4: Reserved Zone (rows 0–1, columns 8–W-1)
- **Coordinates**: (8, 0) to (W-1, 1)
- **Purpose**: Reserved for future expansion (multi-layer terrain, height maps)
- **Encoding**: All pixels set to RGB(255, 0, 255) (magenta) — reserved marker

## Frame 2: Camera & Navigation Registers

### Region 2.1: Position Registers (2 pixels)
- **Coordinates**: (0, 0) and (1, 0)
- **Encoding**:
  - (0, 0): Camera X position as 32-bit signed integer (RGBA channels combined)
    - X = (R << 24) | (G << 16) | (B << 8) | A
  - (1, 0): Camera Y position as 32-bit signed integer
- **Range**: -2³¹ to 2³¹-1 (supports infinite coordinate plane)

### Region 2.2: World Parameters (pixels 2–5, row 0)
- **Coordinates**: (2, 0) to (5, 0)
- **Encoding**:
  - (2, 0): Time-of-day (0–23 hours) in R channel (0–255 maps to 0–23)
  - (3, 0): Global threat level (0–100) in R channel
  - (4, 0): Chunk load radius (1–32) in R channel
  - (5, 0): Reserved (set to magenta RGB(255, 0, 255))

### Region 2.3: System Control Registers (pixels 6–7, row 0)
- **Coordinates**: (6, 0) and (7, 0)
- **Encoding**:
  - (6, 0): Flags byte (bitfield)
    - Bit 0 (A > 0): Paused/running state
    - Bit 1 (B > 0): Debug mode enabled
    - Bit 2 (G > 0): Diff overlay rendering enabled
    - Bit 3 (R > 0): Temporal logging enabled
  - (7, 0): Current tick count (32-bit unsigned integer, RGBA combined)

### Region 2.4: Entity Pointer Table (rows 1–H-1)
- **Coordinates**: (0, 1) to (W-1, H-1)
- **Purpose**: List of active entity IDs and their positions
- **Encoding**:
  - Each row represents one entity (max H-1 entities)
  - Column 0: Entity ID (RGBA combined 32-bit)
  - Column 1: Entity X position (RGBA combined 32-bit)
  - Column 2: Entity Y position (RGBA combined 32-bit)
  - Column 3–W-1: Reserved for entity-specific data (type, state, inventory)

## Frame 3: Diff-Overlay Storage

### Region 3.1: Sparse Coordinate→Change Records (full frame)
- **Coordinates**: (0, 0) to (W-1, H-1)
- **Purpose**: Store modifications to procedural terrain without mutating base
- **Encoding**: Each non-black pixel represents one modification
  - RGB(0, 0, 0): No modification (empty)
  - RGB(r, g, b) with (r | g | b) > 0: Modification record
    - X coordinate encoded in R channel (0–255) → actual X = R × 256 + G_low
    - Y coordinate encoded in G channel (0–255) → actual Y = G_high × 256 + B_low
    - Change type encoded in B channel
      - 1: Destroy tree/structure
      - 2: Build structure
      - 3: Dig hole
      - 4: Place tile
      - 5–255: Reserved
    - Additional data (e.g., structure ID) in A channel (0–255)
- **Lookup**: Hash map keyed by (X, Y) tuple, value = (change_type, data)
- **Sparse Optimization**: Only non-black pixels are stored; black pixels are skipped

### Region 3.2: Overlay Metadata (last row)
- **Coordinates**: (0, H-1) to (W-1, H-1)
- **Encoding**:
  - Column 0: Modification count (RGBA combined 32-bit)
  - Column 1: Oldest modification timestamp (RGBA combined 32-bit)
  - Column 2–W-1: Reserved for future expansion (undo stack, batch operations)

## Frames 4+: Temporal Memory

### Region 4+.1: Full State Snapshots (per frame)
- **Coordinates**: (0, 0) to (W-1, H-1) per frame
- **Purpose**: Complete system state at each execution tick
- **Encoding**: Dense codec (3 bytes/pixel) via Visual Audio
  - Frame header: 'UA' magic + uint16 payload length + CRC32 (see tools/speak.py)
  - Payload: Serialized state of Frames 1–3 (seed, registers, diff overlay)
- **Format**: PNG sequence (one frame per tick) or `.rts.png` spatial container
- **Seek Operation**: "Load frame N" → decode PNG N, deserialize Frames 1–3, restore state

### Region 4+.2: Timestamp Metadata (PNG text chunk)
- **Encoding**: Store tick number and Unix timestamp in PNG tEXt chunk
  - Key: `tick`, Value: "N"
  - Key: `timestamp`, Value: "Unix timestamp in ISO 8601 format"

## Cartridge Integration

### Spatial MMIO Regions (from TASK_G001)
- **Registry Address**: 0x8009_0000 (R/W) → dispatch spatial opcodes
- **Bytecode Corridor**: 0x8009_2000 → bytecode buffer for execution
- **Mapping**:
  - Frame 1 regions → MMIO registers 0x8009_1000–0x8009_10FF
  - Frame 2 registers → MMIO registers 0x8009_1100–0x8009_11FF
  - Frame 3 diff overlay → MMIO region 0x8009_1200–0x8009_12FF (sparse access)

### Bytecode Generation (from TASK_G001)
- **Format**: Length prefix (4 bytes) + payload + HALT opcode
- **Payload Encoding**: Each opcode reads/writes to specific MMIO regions (e.g., `READ_REGISTER 0x8009_1100` reads camera X)

## Non-Overlap Guarantees

All regions above are guaranteed non-overlapping within their respective frames:
- Frame 1: Seed pixels (0,0–7,7) ≪ Biome Palette (0,2–W-1,10) ≪ Tile Atlas (0,11–W-1,H-1)
- Frame 2: Position registers (0,0–1,0) ≪ World parameters (2,0–5,0) ≪ Control registers (6,0–7,0) ≪ Entity pointers (0,1–W-1,H-1)
- Frame 3: Full frame used for sparse diff overlay (no sub-region conflicts)
- Frames 4+: Full frame per tick (no internal conflicts)

## Error Handling

- **Corrupted Seed Pixels**: If all 64 pixels are zero, use fallback seed = 0xDEADBEEF_CAFEBABE
- **Invalid Palette Lookup**: If noise value v < 0 or v > 1, clamp to [0, 1] before lookup
- **Out-of-Bounds Coordinates**: If camera X/Y outside [-2³¹, 2³¹-1], clamp to valid range
- **Diff Overlay Corruption**: If diff overlay pixel is RGB(0, 0, 0), treat as "no modification" (safe default)
- **Temporal Seek Error**: If frame N doesn't exist, return last available frame with timestamp ≤ requested tick

## Performance Considerations

- **Seed Decode**: 64 pixels → 64-bit integer via bitwise operations (<1ms)
- **Palette Lookup**: O(1) per noise value (array indexing)
- **Diff Overlay Lookup**: O(1) per coordinate via hash map
- **Temporal Seek**: Decode PNG + deserialize Frames 1–3 (<100ms target)
- **Nested Frame Blit**: Blit operation (copy pixels) to display zone (<16ms target for 60 FPS)

## References

- Research document: `/home/jericho/zion/docs/research/485_visual_audio_to_software123.txt`
- Visual Audio ROADMAP Phase 11: TASK_SE001–SE006
- Geometry OS integration (TASK_G001): Spatial MMIO and bytecode generation
- Dense codec (3 bytes/pixel): `tools/dense_encoder.py`
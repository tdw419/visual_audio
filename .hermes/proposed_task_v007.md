# MKV to Memory Palace Bridge — Proposed Roadmap Task

## Context

**Phase 10 (VAMP)** currently has:
- ✅ TASK_V001: Dense encoder bridge (COMPLETE)
- ✅ TASK_V002: Audio knowledge export (COMPLETE)
- ⏳ TASK_V003-V005: Verification tests pending

The container system (TASK_VAC001-007) is COMPLETE and working. Both systems use **3 bytes/pixel density** via `dense_encoder.py`—the bridge is straightforward.

## Proposed Task: TASK_V007 — MKV Container → Memory Palace

**Status**: 🟡 READY TO START  
**Priority**: MEDIUM  
**Dependencies**: TASK_V001, TASK_VAC001-007  
**Unblocks**: TASK_V006 (GeOS memory palace visualization update)

### Description

Extract Visual Audio container entries as Memory Palace PNG tiles, enabling spatial knowledge visualization in Geometry OS. The container holds project state; the Palace makes it walkable.

### Deliverable

`tools/mkv_to_palace.py` — CLI tool that:

1. **Extract** entries from `visual_audio.mkv` via `va_container.py`
2. **Encode** each entry as dense PNG tile via `dense_encoder.py`
3. **Assemble** tiles into Palace PNG with Hilbert coordinate metadata
4. **Generate** coordinate manifest for GeOS import

### Acceptance Criteria

```bash
# Extract entire container as single Palace PNG
python3 tools/mkv_to_palace.py visual_audio.mkv visual_audio_palace.png

# Extract specific entries as tiled Palace PNG
python3 tools/mkv_to_palace.py visual_audio.mkv \
  --entries ROADMAP.md,codec/tables.json \
  --tile-size 512 \
  --output visual_audio_tiles.png

# Verify lossless round-trip
python3 tools/verify_palace_bridge.py visual_audio_palace.png
# Expect: All entries verified (SHA256 match)
```

### Technical Details

**Coordinate Mapping:**
- Each entry gets assigned (ring, slot) in Palace
- Directory entry → `ring=0` (inner ring, hot data)
- Spec entries → `ring=1` (middle ring)
- Content entries → `ring=2` (outer ring)
- Hilbert curve ensures spatial locality

**Tile Format:**
- Per-entry PNG: 512x512 tiles (configurable)
- Dense encoder: `[UA][LEN][PAYLOAD][CRC32]` format
- Alpha channel: 255 (fully opaque)

**Manifest Format:**
```json
{
  "format": "VAMP-TILES",
  "version": 1,
  "tile_size": 512,
  "entries": {
    "spec/ROADMAP.md": {"ring": 1, "slot": 0},
    "codec/tables.json": {"ring": 1, "slot": 1},
    "bootstrap/va_container.py": {"ring": 0, "slot": 0}
  }
}
```

### Test

`tests/test_mkvpalace_bridge.py`:
- Extract container → Palace PNG → verify SHA256 round-trip
- Verify coordinate mapping respects ring priorities
- Verify tile assembly produces valid Palace format
- Stress test: container with 100+ entries

### Time Estimate

2 hours focused development

### Impact

- Unblocks TASK_V006 (GeOS visualization needs Palace data)
- Creates concrete path from working container to spatial knowledge
- Enables "walk through your project state" in GeOS
- Demonstrates VAMP multi-modal extension

## Integration Path

```
TASK_VAC001-007 ✅ (container working)
  ↓
TASK_V007 (this task) → Palace PNG generation
  ↓
TASK_V006 🟡 (GeOS visualization needs Palace data)
  ↓
Phase 10 complete: Multi-modal Memory Palace extension
```

---

**Verdict:** YES — add TASK_V007 to Phase 10. It's the missing link between your working container and the spatial Memory Palace vision.
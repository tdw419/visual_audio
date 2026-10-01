# PDB Format Specification (Pixel Database)

## Overview

A `.pdb` frame is a spatially-encoded database table stored as RGBA pixels.
Each table occupies a 2D bounding box within the frame. Row data is laid out
along the Hilbert curve to preserve spatial locality for indexed queries.

**Design Goal**: SQLite is the compiler, Pixel DB is the executable.
Author schemas/rows in SQLite, compile to `.pdb`, query natively in Geometry OS.

---

## Frame Layout

```
.pdb.png (RGBA, power-of-2 dimensions)
├─ Header Region (top-left 128×128 pixels)
│  ├─ Magic: "PDB1" at (0,0)-(3,0) RGBA
│  ├─ Version: u8 at (4,0)
│  ├─ Table count: u8 at (5,0)
│  ├─ Table metadata (32 bytes per table):
│  │  ├─ Name: 16 bytes (null-terminated UTF-8)
│  │  ├─ Bounding box: (x_min, y_min, x_max, y_max) as u32 LE each
│  │  ├─ Row count: u32 LE
│  │  └─ Row byte length: u32 LE
│  └─ Reserved: padding to 128×128
│
└─ Table Regions (Hilbert-ordered rows)
   ├─ Table 0 region (x_min,y_min)-(x_max,y_max)
   │  └─ Rows encoded as RGB bytes (A=255)
   └─ Table 1 region ...
```

### Header Encoding

| Offset (pixels) | Field | Type | Description |
|-----------------|-------|------|-------------|
| (0,0) | Magic | "PDB1" | Bytes P(80), D(68), B(66), "1"(49) in RGB |
| (4,0) | Version | u8 | Format version (0x01) |
| (5,0) | Table count | u8 | Number of tables (max 255) |
| (6,0)-(21,0) | Table 0 name | 16 bytes | Null-terminated UTF-8 |
| (22,0)-(25,0) | Table 0 x_min | u32 LE | Bounding box minimum X |
| (26,0)-(29,0) | Table 0 y_min | u32 LE | Bounding box minimum Y |
| (30,0)-(33,0) | Table 0 x_max | u32 LE | Bounding box maximum X |
| (34,0)-(37,0) | Table 0 y_max | u32 LE | Bounding box maximum Y |
| (38,0)-(41,0) | Table 0 row count | u32 LE | Number of rows |
| (42,0)-(45,0) | Table 0 row length | u32 LE | Bytes per row (fixed) |
| ... | Table N | ... | Repeated for each table |

### Table Region Encoding

Each row is encoded as consecutive RGB triplets along the Hilbert curve:
```
Row N: [byte0, byte1, byte2, byte3, byte4, byte5, ...]
       ^ R    ^ G    ^ B    ^ R    ^ G    ^ B    (A=255)
```

Rows are stored in Hilbert distance order (0, 1, 2, ... N-1).

---

## Constraints

1. **Power-of-2 dimensions**: Frame width/height must be 2^n (e.g., 512×512, 4096×4096)
2. **Fixed row length per table**: All rows in a table have the same byte length
3. **Bounding boxes must not overlap**: Tables are allocated disjoint regions
4. **Hilbert mapping**: All spatial transforms use `geos_pixel::HilbertCurve`
5. **VCC integrity**: Per-table hash computed as SHA-256 of bounding box pixels

---

## Verification Gates

### Round-Trip Test
```bash
# Create SQLite DB
sqlite3 test.db "CREATE TABLE users (id INTEGER, name TEXT, status TEXT); INSERT INTO users VALUES (1, 'alice', 'active');"

# Compile to .pdb
cargo run --bin sqlite_to_pdb -- test.db test.pdb.png

# Decode back to bytes
cargo run --bin pdb_decode -- test.pdb.png users /tmp/users.bin

# Verify: bytes match original SQLite export
diff -q <(sqlite3 test.db ".dump users") <(hexdump -C /tmp/users.bin)
```

### VCC Hash Test
```bash
# Compute VCC hash for table region
cargo run --bin pdb_vcc_hash -- test.pdb.png users

# Output: SHA-256 checksum of bounding box pixels
# Expected: deterministic for same table data
```

---

## Future Extensions (Phase 2+)

1. **Columnar layout**: Map each column to separate bounding box for GPU column scans
2. **Index mipmap**: Quadtree structure as LOD levels for accelerated range queries
3. **GPU compute shader**: WGPU scanner for parallel pattern matching
4. **Incremental updates**: PNG delta encoding for partial re-encode

---

**Version**: 0.1.0  
**Status**: Phase 1 Skeleton (implementation pending)
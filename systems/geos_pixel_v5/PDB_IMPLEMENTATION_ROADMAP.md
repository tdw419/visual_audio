# PDB Implementation Roadmap

## Phase 1: SQLite-to-PDB Compiler (Minimal Working System)

**Goal**: Round-trip SQLite → `.pdb.png` → decoded bytes with VCC integrity checks.

### Step 1: SQLite Introspection & Schema Parsing
**File**: `geos_v5/src/pdb/compiler.rs`

**Tasks**:
1. Add `rusqlite` dependency to `Cargo.toml`
2. Open SQLite database connection in `SqliteToPdb::compile()`
3. Query table names: `SELECT name FROM sqlite_master WHERE type='table'`
4. For each table, query schema: `PRAGMA table_info(table_name)`
5. Calculate fixed row byte length from schema types
   - INTEGER: 8 bytes (i64)
   - TEXT: variable (max 255 bytes, null-terminated)
   - REAL: 8 bytes (f64)
   - BLOB: variable (max 255 bytes, length-prefixed)

**Acceptance Criteria**:
- Compiler can open SQLite file and enumerate all tables
- Row byte length calculated correctly for known schema

### Step 2: Bounding Box Allocation
**File**: `geos_v5/src/pdb/compiler.rs`

**Tasks**:
1. Allocate bounding boxes for each table (non-overlapping)
2. Start from `(0, HEADER_SIZE)` and allocate sequentially
3. Calculate bounding box size from row count × row length
   - 1 row = 3 pixels (RGB) for `row_length` bytes
   - Pixels needed = ceil(`row_count * row_length / 3`)
4. Store `BoundingBox` in `TableMetadata`

**Acceptance Criteria**:
- Tables allocated to disjoint regions
- Bounding box contains enough pixels for all rows
- Header metadata updated correctly

### Step 3: Hilbert-Ordered Encoding
**File**: `geos_v5/src/pdb/encoder.rs`

**Tasks**:
1. Replace placeholder `encode_table()` with real implementation
2. Iterate row data in chunks of 3 bytes
3. For each chunk:
   - Calculate Hilbert distance `d = start_distance + chunk_index`
   - Map to `(x, y)` via `HilbertCurve::d2xy(grid_size, d)`
   - Write RGB bytes at `(x, y)`, A=255
4. Encode table metadata to header region
   - Table name at calculated offset
   - Bounding box as u32 LE (4 pixels each)
   - Row count and row length as u32 LE

**Acceptance Criteria**:
- `encode_header()` writes all metadata correctly
- `encode_table()` encodes rows along Hilbert curve
- Output PNG has valid PDB magic + version

### Step 4: Hilbert-Ordered Decoding
**File**: `geos_v5/src/pdb/decoder.rs`

**Tasks**:
1. Replace placeholder `decode_table()` with real implementation
2. Parse table metadata from header region
   - Read name, bounding box, row count, row length
3. Decode table region:
   - Iterate pixels in bounding box
   - For each pixel at `(x, y)`:
     - Calculate linear distance `d = HilbertCurve::xy2d(grid_size, x, y)`
     - Extract RGB bytes, ignore Alpha
     - Place in output buffer at `d * 3`
4. Return concatenated row bytes

**Acceptance Criteria**:
- `decode_header()` parses all metadata correctly
- `decode_table()` reconstructs original byte stream
- Round-trip test passes: `bytes_in ≈ bytes_out`

### Step 5: VCC Integrity Hashing
**File**: `geos_v5/src/pdb/vcc.rs`

**Tasks**:
1. Implement `VccIntegrity::compute_table_hash()`:
   - Extract pixels from bounding box
   - Flatten to byte array (RGBA for each pixel)
   - Compute SHA-256 hash via `sha2::Sha256`
   - Store and return hash
2. Add VCC verification test
3. Print hashes during compilation

**Acceptance Criteria**:
- VCC hash computed for each table
- Hash deterministic for same table data
- Verification fails on corrupted bounding box

### Step 6: Round-Trip Verification Gate
**File**: `examples/sqlite_to_pdb.rs`

**Tasks**:
1. Create test SQLite database with 2 tables (users, sessions)
2. Insert sample data (10 rows each)
3. Compile to `.pdb.png`
4. Decode both tables
5. Compare decoded bytes to original SQLite export
6. Compute VCC hashes and verify

**Acceptance Criteria**:
- Round-trip test passes with 0 byte differences
- VCC hashes match between encode and decode
- CLI tool runs without errors

---

## Verification Commands

### Compile Test Database
```bash
# Create test database
sqlite3 test.db <<EOF
CREATE TABLE users (id INTEGER, name TEXT, status TEXT);
INSERT INTO users VALUES (1, 'alice', 'active');
INSERT INTO users VALUES (2, 'bob', 'inactive');
CREATE TABLE sessions (id INTEGER, user_id INTEGER, token TEXT);
INSERT INTO sessions VALUES (1, 1, 'abc123');
INSERT INTO sessions VALUES (2, 2, 'def456');
EOF

# Compile to PDB
cargo run --example sqlite_to_pdb -- test.db test.pdb.png 512
```

### Decode and Verify
```bash
# Decode tables (Phase 1 Step 4 implementation)
# (Placeholder: will implement decode CLI)

# VCC hash check (Phase 1 Step 5 implementation)
# (Placeholder: will implement vcc_hash CLI)
```

---

## Phase 2: GPU Query Execution (Future)

- WGSL compute shader for parallel pattern matching
- Quadtree mipmap indexing
- Spatial range queries
- Zero-copy texture sampling

---

## Status

**Phase 1 Skeleton**: ✅ Complete
**Phase 1 Implementation**: ⏳ Pending (Steps 1-6)
**Phase 2 GPU Queries**: ⏸️ Deferred

---

**Last Updated**: 2026-08-21
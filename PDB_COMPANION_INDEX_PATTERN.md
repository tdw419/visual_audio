# PDB Companion Index Pattern

**Purpose**: Debugging/diagnostic data as companion metadata alongside PDB PNG data.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     PDB (pixel-native)                   │
│  ┌──────────────────────────────────────────────────┐   │
│  │ kernel.pdb.png | initramfs.pdb.png | rootfs.pdb.png │   │
│  │ - Byte-perfect binary data                        │   │
│  │ - Addressed spatially via Hilbert curve            │   │
│  │ - Queryable by GPU during execution                │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                              ↕ companion metadata
┌─────────────────────────────────────────────────────────┐
│              SQLite Companion Index                     │
│  ┌──────────────────────────────────────────────────┐   │
│  │ fault_frequency | pixel_regions | kernel_symbols  │   │
│  │ - Host-side diagnostic queries                     │   │
│  │ - Symbol tables, fault statistics                 │   │
│  │ - Not accessed by GPU during execution            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## When to Use Companion Index

**Use SQLite companion** when:
- Data is diagnostic/investigative (not runtime-critical)
- Schema is still evolving during investigation
- Data size is small (trace summaries, symbol tables)
- Queries are ad-hoc and complex (joins, aggregations)

**Use PDB pixel tables** when:
- Data must be addressable by GPU during execution
- Data is part of the execution path (code, filesystems, config)
- Schema is stable and architectural
- Access pattern is spatial/pixel-addressed

## RV64I Stall Investigation

**PDB data**:
- `kernel.pdb.png` - Alpine kernel binary (spatially encoded)
- `initramfs.pdb.png` - Initial ramdisk
- `rootfs.pdb.png` - Root filesystem

**Companion index** (`rv64i_stall_semantic.db`):
- `fault_frequency` - PC fault counts from trace
- `pixel_regions` - PC ranges → pixel tile mapping
- `kernel_symbols` - Synthetic symbol names (for visualization)

## Queries

### Find top faulting PCs
```bash
sqlite3 rv64i_stall_semantic.db \
  'SELECT pc, fault_count FROM fault_frequency ORDER BY fault_count DESC LIMIT 10'
```

### Find PCs with zero UART output (stall detection)
```bash
sqlite3 rv64i_stall_semantic.db \
  'SELECT COUNT(*) FROM fault_frequency WHERE uart_bytes_at_fault = 0'
```

### Find pixel regions with high fault density
```bash
sqlite3 rv64i_stall_semantic.db \
  'SELECT tile_x, tile_y, fault_count FROM pixel_regions ORDER BY fault_count DESC LIMIT 10'
```

## Migration Path to PDB

When the semantic layer stabilizes and proves useful beyond this investigation:

1. **Define stable schema** for diagnostic tables
2. **Add PDB table encoding** for companion data
3. **Update V4.1/ROADMAP.md** to include pixel-native diagnostic storage
4. **Deprecate SQLite companion** (keep for historical queries only)

## Examples of Suitable Companion Indexes

- Boot trace summaries
- Fault/crash statistics
- Symbol resolution tables
- Performance profiling data
- Memory usage histograms

## Examples Better Suited for PDB

- Kernel/initramfs binary payloads
- Filesystem contents
- Configuration files (read during boot)
- Device trees / FDT
- Runtime executable code

## Naming Convention

Companion index files:
- `<pdb_basename>_semantic.db` (diagnostic data)
- `<pdb_basename>_trace.jsonl` (raw trace data)

Example:
- `rootfs.pdb.png` → `rootfs_semantic.db`
- `kernel.pdb.png` → `kernel_semantic.db`

## Verification Gate

Companion index must satisfy:
- [ ] Queries complete in < 1 second on trace of ≤ 500M steps
- [ ] Schema allows JOINs between fault data and symbol tables
- [ ] PC → pixel tile mapping is bijective (no lost addresses)
- [ ] Compatible with existing PDB tools (doesn't require changes)

**Status**: Companion index pattern accepted for RV64I stall investigation.
**Future work**: Migrate to PDB pixel tables when schema stabilizes.
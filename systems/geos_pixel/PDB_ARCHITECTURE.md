# Geometry OS: Pixel Database (PDB) Architecture

**"SQLite is the Compiler. Pixel DB is the Executable."**

The Pixel Database (PDB) is a core sub-system of Geometry OS that bridges the gap between traditional structured data and spatial, visual-first computation. By translating relational databases into dense, spatially-aware 2D images, PDB allows the GPU to execute massive parallel queries using native texture sampling and compute shaders.

---

## 1. Core Philosophy & Design

In standard operating systems, databases are parsed, serialized, and queried sequentially by the CPU. In Geometry OS, the visual frame *is* the memory layout. 

PDB operates on the following principles:
1. **Authoring (CPU)**: Standard `sqlite3` databases are used to define schemas and insert data.
2. **Compilation (CPU)**: A Rust compiler (`sqlite_to_pdb`) reads the SQLite tables, calculates fixed byte-lengths, allocates 2D bounding boxes in a frame, and maps the rows into RGBA pixels along a **Hilbert Curve**.
3. **Execution (GPU)**: The resulting `.pdb.png` frame is loaded directly into VRAM as a `wgpu::Texture`. WGSL compute shaders perform highly parallel scans over the texture to find exact byte patterns without ever copying the data back to the CPU.

---

## 2. Frame Layout & Spatial Topology

A `.pdb.png` frame is a power-of-2 (e.g., 512×512) RGBA texture.

### The Header Region
The top-left of the image (first row of pixels) serves as the allocation table.
- **Magic & Version**: First 5 pixels contain "PDB1" and version flags.
- **Table Metadata**: Each table gets a 32-pixel metadata block specifying its Name, Bounding Box (`x_min, y_min, x_max, y_max`), Row Count, and Row Byte Length.

### The Table Regions & Bounding Boxes
Unlike traditional 1D file formats, tables in PDB are 2D bounding boxes.
- To ensure dense packing without wasting pixels, the compiler allocates non-overlapping rectangular blocks.
- The size of the block is calculated based on the total bytes: `Pixels = ceil((Row_Count * Row_Length) / 3)`. (Alpha channel is currently set to 255 and ignored for data).

### The Hilbert Curve Data Mapping
Rows are not written strictly left-to-right. To preserve **spatial locality**—ensuring that data which is conceptually close together remains physically close in VRAM—bytes are encoded along a 2D Hilbert Curve.

**Crucial Topologic Constraint**: Because the bounding box is rarely a perfect square that matches a Hilbert grid, the encoder iterates the Hilbert curve over the *entire frame size*, but **skips any coordinates that fall outside the table's bounding box**. This ensures the table data remains densely packed, but it means that the linear `chunk_index` (the Nth valid pixel) does not cleanly translate to the Hilbert distance without counting.

---

## 3. The WGSL Multi-Byte Pattern Scanner

To execute queries (e.g., `SELECT * FROM users WHERE name = 'alice'`), Geometry OS dispatches a WGSL compute shader.

### The Challenge of the Bounding Box
Because valid pixels are not necessarily continuous in Hilbert space (due to bounding-box boundaries), a GPU thread can't simply increment its spatial index `global_idx + 1` to find the next byte of a multi-byte pattern.

### The Shader Implementation
1. **Thread Assignment**: Each compute thread is assigned a global invocation ID, which maps to a specific Hilbert distance `i`.
2. **Bounds Checking**: The thread evaluates `hilbert_d2xy(i)` and adds the bounding box offsets. If the pixel is outside the box, the thread exits immediately.
3. **Multi-Byte Matching**: If the pixel is valid, the thread assumes this pixel could be the start of a pattern. It loops through the `vec4<u32>` pattern buffer passed via uniform bindings.
4. **Hilbert Continuity Tracing**: If the pattern spans into the next pixel, the WGSL thread internally steps its Hilbert distance `i` forward, recalculating the `(x, y)` coordinate until it finds the *next valid pixel* inside the bounding box.
5. **Atomic Readback**: If a full match is found, the thread atomically writes its starting **Spatial Offset** (the Hilbert distance × 3 + channel offset) into an SSBO (Shader Storage Buffer Object).

---

## 4. Spatial-to-Linear Inverse Mapping

Once the GPU finishes scanning (in ~5-10ms for millions of pixels), it returns an array of matching spatial offsets.

To be useful to the OS, these spatial coordinates must be translated back into standard row/column data. The CPU performs an inverse mapping:
1. It extracts the matching `global_idx` (Hilbert distance).
2. It re-simulates the Hilbert curve from `0` to `global_idx`, counting exactly how many valid pixels fell inside the table's bounding box.
3. This count is the exact linear `chunk_index`.
4. The linear byte offset is calculated: `linear_byte = chunk_index * 3 + channel`.
5. The row is isolated: `row_index = linear_byte / row_length`.

### End-to-End Pipeline
```
[SQLite Rows] -> (Compiler) -> [Hilbert Spatial PNG] -> (WGSL Shader) -> [Spatial Offset] -> (Inverse Mapping) -> [Matched Row]
```

---

## 5. Future Architectural Tracks

With Phase 1 (CPU Compiler) and Phase 2 (WGSL Spatial Queries) complete, the PDB architecture is primed for expansion:

- **Quadtree Mipmap Spatial Indexing**: Precomputing a spatial index (`chunk_index` -> `hilbert_distance`) in a storage buffer to allow O(1) Columnar Scans directly on the GPU without simulating the curve inside the shader.
- **Visual Consistency Contract (VCC)**: Using SHA-256 hashes of the exact pixel regions for each table to verify that the spatial database hasn't been corrupted.
- **Hardware-Native Execution**: Booting PDB querying logic on bare-metal Vulkan substrates as a dedicated Geometry OS driver.

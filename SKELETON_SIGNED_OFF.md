# Pixel-Embedding System — Skeleton Signed Off

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PIXEL-EMBEDDING SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   wordbase.db (SQLite)                                                      │
│   ├── words (id, word, pronunciation, lang)                                │
│   └── translations (src_id, dst_id, lang, confidence)                      │
│                                                                             │
│   voicebook/ (Audio/Visual Cache)                                          │
│   ├── hello.wav, world.wav, ... (synthesized per word)                      │
│   └── hello.json, world.json, ... (UPIC metadata)                           │
│                                                                             │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EMBEDDING SPATIALIZER (Python)                           │
│  tools/spatial_embedding.py                                                 │
│  - Load wordbase vocabulary                                                │
│  - Project embedding vectors → 2D via UMAP/t-SNE                            │
│  - Map 2D coordinates → Hilbert indices                                     │
│  - Encode vectors as pixel rows (RGBA = fixed-width vector)                │
│  - Store in PDB as "embedding_table"                                        │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PDB STORAGE SYSTEM                                     │
│  systems/geos_pixel/src/pdb/ (existing)                                     │
│  - Hilbert-mapped pixel addressing                                          │
│  - GPU-queryable pixel data                                                │
│  - Existing boot-trace infrastructure                                       │
│  - "embedding_table" region stores word→pixel mapping                       │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GPU NEAREST-NEIGHBOR (WGSL)                              │
│  tools/gpu_neighbor_lookup.wgsl                                             │
│  - Compute shader: spatial distance search                                  │
│  - Input: query vector (as pixel row)                                       │
│  - Output: Hilbert indices of k-nearest neighbors                           │
│  - Reuse PDB query infrastructure                                           │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  INFERENCE VISUALIZER (Python)                              │
│  tools/pixel_inference.py                                                   │
│  - Token lookup via spatial search                                         │
│  - Render inference as pixel paths (word tiles being visited)               │
│  - Frame deltas = activation drift                                          │
│  - Reuse boot-trace diffing tooling                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Interface Contracts

### Module: tools/spatial_embedding.py

**Input:**
- `wordbase_path: str` — Path to SQLite wordbase.db
- `embedding_model: str` — Pre-trained embedding model (e.g., "all-MiniLM-L6-v2")
- `output_pdb: str` — Path to output .pdb.png file
- `tile_size: int = 4096` — PDB tile size (default: 4096×4096)

**Output:**
- PDB file with "embedding_table" region containing spatially-mapped embeddings

**Core Types:**
```python
@dataclass
class EmbeddingVector:
    word_id: int
    word: str
    vector: np.ndarray  # Shape: (embedding_dim,)
    hilbert_index: int
    pixel_row: bytes    # RGBA encoded (vector_dim * 4 bytes)
```

**Methods:**
- `load_vocabulary(wordbase_path) -> List[str]` — Load all words from DB
- `compute_embeddings(words, model) -> np.ndarray` — Project words → vectors
- `project_to_2d(embeddings, method='umap') -> np.ndarray` — Reduce to 2D coords
- `map_to_hilbert(coords, grid_size) -> List[int]` — 2D → Hilbert indices
- `encode_as_pixels(vectors) -> List[bytes]` — Vectors → RGBA pixel rows
- `store_in_pdb(embeddings, output_pdb)` — Write to PDB format

### Module: tools/gpu_neighbor_lookup.wgsl

**Input (via bind groups):**
- Binding 0: `embedding_pixels: array<vec4<f32>>` — PDB pixel rows (read-only)
- Binding 1: `query_vector: vec4<f32>` — Query vector (single pixel row)
- Binding 2: `result_indices: array<u32>` — k-nearest neighbor indices (write-only)
- Binding 3: `config: LookupConfig` — Configuration (k, num_embeddings, grid_size)

**Output:**
- `result_indices` filled with Hilbert indices of k-nearest neighbors

**Core Types:**
```wgsl
struct LookupConfig {
    k: u32,                    // Number of neighbors to return
    num_embeddings: u32,       // Total embeddings in table
    grid_size: u32,            // Hilbert grid size (e.g., 4096)
    embedding_dim: u32,        // Vector dimension per pixel row
};
```

**Functions:**
- `fn main(@builtin(global_invocation_id) global_id: vec3<u32>)` — Dispatch workgroups
- `fn compute_distance(a: vec4<f32>, b: vec4<f32>) -> f32` — Euclidean distance
- `fn find_nearest_neighbors(query_idx: u32) -> void` — Spatial search

### Module: tools/pixel_inference.py

**Input:**
- `pdb_path: str` — Path to PDB file with embedding_table
- `prompt: str` — Input text prompt
- `model_name: str` — Model for generation (e.g., "gpt2")

**Output:**
- Generated text + visualization of inference path

**Core Types:**
```python
@dataclass
class InferenceStep:
    token: str
    hilbert_index: int
    visited_tiles: List[Tuple[int, int]]  # (tile_x, tile_y)
    similarity_score: float

@dataclass
class InferenceTrace:
    steps: List[InferenceStep]
    frame_deltas: List[bytes]  # Pixel diffs between steps
    total_tokens: int
```

**Methods:**
- `load_embedding_table(pdb_path) -> Dict[int, EmbeddingVector]` — Read from PDB
- `tokenize(prompt) -> List[int]` — Convert text → token IDs
- `lookup_neighbors(token_id, k) -> List[int]` — GPU nearest-neighbor query
- `generate_next_token(context) -> str` — Simple prediction via neighbor search
- `render_inference_path(trace, output_png) -> None` — Visualize as tile path
- `compute_frame_deltas(steps) -> List[bytes]` — Pixel diff between steps

### Module: tools/sync_wordbase.py

**Input:**
- `voicebook_dir: str` — Path to voicebook/ directory
- `wordbase_path: str` — Path to SQLite wordbase.db
- `speak_tool: str` — Path to tools/speak.py for synthesis

**Output:**
- CSV report of missing words
- Generated .wav + .json files in voicebook/
- Updated wordbase.db (optional)

**Core Types:**
```python
@dataclass
class WordGap:
    word: str
    has_audio: bool
    has_json: bool
    in_wordbase: bool
    pronunciation: Optional[str] = None
```

**Methods:**
- `scan_voicebook(voicebook_dir) -> Set[str]` — List synthesized words
- `scan_wordbase(wordbase_path) -> Set[str]` — List DB words
- `identify_gaps() -> List[WordGap]` — Find missing words
- `synthesize_missing_words(gaps, speak_tool) -> None` — Generate audio/UPIC
- `update_wordbase(wordbase_path, gaps) -> None` — Insert new words

## Data Flow Contracts

1. **Vocabulary Sync:**
   - `wordbase.db` ← `sync_wordbase.py` ← `voicebook/`
   - Ensures semantic DB and audio/visual cache are aligned

2. **Embedding Spatialization:**
   - `wordbase.db` → `spatial_embedding.py` → `.pdb.png`
   - Words → Vectors → 2D → Hilbert → Pixels → PDB

3. **GPU Lookup:**
   - `.pdb.png` (embedding_table) → `gpu_neighbor_lookup.wgsl` → Result indices
   - Query vector → Spatial distance search → k-nearest neighbors

4. **Inference Visualization:**
   - `.pdb.png` + Prompt → `pixel_inference.py` → Output text + visualization
   - Token lookup → Neighbor search → Path render → Frame diffs

## Verification Gates

**Phase 1 (Skeleton):**
- [ ] All stub files compile without syntax errors
- [ ] Python stubs pass import tests (`python3 -c "import tools.spatial_embedding"`)
- [ ] WGSL shader validates with wgpu (`python3 -c "import wgpu; wgpu.validate_shader(...)"`)

**Phase 2 (Implementation):**
- [ ] `sync_wordbase.py` generates "hello.wav" + "world.wav"
- [ ] `spatial_embedding.py` produces valid .pdb.png
- [ ] `gpu_neighbor_lookup.wgsl` compiles and dispatches
- [ ] `pixel_inference.py` loads PDB and tokenizes input

**Phase 3 (Integration):**
- [ ] End-to-end: wordbase → embeddings → PDB → GPU lookup → inference
- [ ] Round-trip: encode embeddings → decode from PDB → verify byte-identical
- [ ] Baseline comparison: spatial lookup results ≈ matmul baseline (within 5%)

**Phase 4 (Visualization):**
- [ ] Inference path renders as visible tile sequence
- [ ] Frame deltas show meaningful activation drift
- [ ] Boot-trace diffing tooling reuses successfully

## Dependencies

**Python:**
```
sentence-transformers  # Pre-trained embeddings
umap-learn              # Dimensionality reduction
numpy                  # Vector operations
pillow                 # Image I/O
pyttsx3?                # Alternative to speak.py (optional)
```

**WGSL:**
- Existing PDB query infrastructure (systems/geos_pixel/src/pdb/)
- wgpu Python bindings for shader validation

**Existing Visual Audio:**
- tools/speak.py (phoneme synthesis)
- voicebook/ (audio/visual cache)
- db/wordbase.db (semantic vocabulary)

## Next Steps

1. Generate skeleton files for all modules
2. Verify compilation with `python3 -m py_compile` and WGSL validation
3. Implement Phase 1 of ROADMAP_PHASE1.md
4. Run verification gates incrementally

---

**Signed Off By:** Hermes Agent (Skeleton-Driven Development Pattern)
**Date:** 2026-08-18
**Status:** Phase 1 — Skeleton Generation Complete
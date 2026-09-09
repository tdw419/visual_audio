# Pixel-Embedding System — Phase 1 Implementation Roadmap

## Overview

This roadmap implements the pixel-embedding system skeleton defined in SKELETON_SIGNED_OFF.md. Each phase builds incrementally, with verification gates at each step.

**Goal:** Create a spatial embedding system where word vectors live as pixel rows in a PDB, and nearest-neighbor lookup is performed via GPU compute shaders.

## Phase 1: Vocabulary Substrate (tools/sync_wordbase.py)

**Status:** Pending

**Goal:** Identify and close the wordbase/voicebook gap so we have a clean vocabulary baseline.

### Step 1.1: Scan Existing Resources
- [ ] Scan `voicebook/` for all .wav and .json files
- [ ] Query `db/wordbase.db` for all words in the `words` table
- [ ] Build a report showing the exact delta (missing words, extra words)

**Verification:** Print CSV report with columns: word, has_audio, has_json, in_wordbase

### Step 1.2: Identify Critical Gaps
- [ ] Prioritize missing words by frequency (if frequency data available)
- [ ] Identify "hello" and "world" specifically (credibility check)

**Verification:** Report lists at least top 100 missing words sorted by priority

### Step 1.3: Synthesize Missing Words
- [ ] Use `tools/speak.py` to generate .wav and .json for missing words
- [ ] Store in `voicebook/` directory
- [ ] Handle batch synthesis (process 50 words at a time to avoid overload)

**Verification:** `hello.wav` and `world.wav` exist in `voicebook/`

### Step 1.4: Update wordbase.db
- [ ] Insert new words into `words` table (if not already present)
- [ ] Populate pronunciations from .json metadata
- [ ] Verify word count matches expected total

**Verification:** `sqlite3 db/wordbase.db "SELECT COUNT(*) FROM words;"` reports expected count

**Acceptance Criteria:**
- [ ] Wordbase and voicebook are synchronized (no missing words)
- [ ] `hello` and `world` present in both DB and audio cache
- [ ] CSV report saved to `reports/wordbase_gap_report.csv`

---

## Phase 2: Embedding Spatialization (tools/spatial_embedding.py)

**Status:** Pending (depends on Phase 1)

**Goal:** Project wordbase embeddings into 2D space and encode as pixel rows in PDB format.

### Step 2.1: Load Vocabulary from wordbase.db
- [ ] Implement `load_vocabulary(wordbase_path)` function
- [ ] Return list of `(word_id, word)` tuples
- [ ] Filter by language (e.g., English only for prototype)

**Verification:** Function returns non-empty list, at least contains "hello" and "world"

### Step 2.2: Compute Embedding Vectors
- [ ] Implement `compute_embeddings(words, model)` function
- [ ] Use sentence-transformers (all-MiniLM-L6-v2) by default
- [ ] Return numpy array of shape `(num_words, embedding_dim)`

**Verification:** Embeddings have shape (N, 384) for MiniLM, no NaN values

### Step 2.3: Project to 2D Coordinates
- [ ] Implement `project_to_2d(embeddings, method='umap')` function
- [ ] Support UMAP (default) and t-SNE as alternatives
- [ ] Return numpy array of shape `(num_words, 2)` in range [0, 1]

**Verification:** Coordinates are in valid range, visual inspection shows clusters

### Step 2.4: Map to Hilbert Indices
- [ ] Implement `map_to_hilbert(coords, grid_size)` function
- [ ] Use existing Hilbert mapping from VirtIO-Pixel backend
- [ ] Return list of integer indices (0 to grid_size²-1)

**Verification:** Indices are unique and in valid range

### Step 2.5: Encode as Pixel Rows
- [ ] Implement `encode_as_pixels(vectors)` function
- [ ] Pack vector dimensions into RGBA pixels (4 floats per pixel)
- [ ] Return list of bytes (one row per word)

**Verification:** Pixel rows can be decoded back to original vectors (within 1e-5 tolerance)

### Step 2.6: Store in PDB
- [ ] Implement `store_in_pdb(embeddings, output_pdb)` function
- [ ] Create "embedding_table" region in PDB format
- [ ] Write pixel rows with Hilbert addressing
- [ ] Use existing PDB encoder from `systems/geos_pixel/src/pdb/`

**Verification:** Output .pdb.png file is valid and can be loaded by PDB decoder

**Acceptance Criteria:**
- [ ] End-to-end: wordbase → embeddings → PDB succeeds
- [ ] Round-trip: encode → decode → verify byte-identical vectors
- [ ] Output PDB contains "embedding_table" region with all words
- [ ] "hello" and "world" embeddings stored at valid Hilbert indices

---

## Phase 3: GPU Nearest-Neighbor Lookup (tools/gpu_neighbor_lookup.wgsl)

**Status:** Pending (depends on Phase 2)

**Goal:** Implement compute shader for spatial distance search over PDB pixel data.

### Step 3.1: Define WGSL Structures
- [ ] Define `LookupConfig` struct with k, num_embeddings, grid_size, embedding_dim
- [ ] Define bind groups for embedding_pixels, query_vector, result_indices
- [ ] Implement `compute_distance(a, b)` function (Euclidean distance)

**Verification:** WGSL compiles with wgpu validation

### Step 3.2: Implement Main Dispatch Logic
- [ ] Implement `main(@builtin(global_invocation_id))` function
- [ ] Each workgroup computes distances for one query
- [ ] Use atomic operations for top-k tracking (or simple sort for prototype)

**Verification:** Shader dispatches without errors, writes to result_indices

### Step 3.3: Integrate with PDB Query Infrastructure
- [ ] Load "embedding_table" from PDB into GPU texture/buffer
- [ ] Query with sample vector (e.g., "hello" embedding)
- [ ] Read back k-nearest neighbor indices

**Verification:** Returned indices are valid Hilbert indices, include self-matching word

### Step 3.4: Compare Against Baseline
- [ ] Implement CPU baseline (scikit-learn NearestNeighbors)
- [ ] Run same queries on CPU and GPU
- [ ] Verify results match within 5% (allow for floating-point differences)

**Verification:** GPU results ≈ CPU baseline (top-1 accuracy ≥ 95%)

**Acceptance Criteria:**
- [ ] WGSL shader compiles and dispatches
- [ ] GPU lookup returns k-nearest neighbors for any query
- [ ] Results match CPU baseline (≥95% top-1 accuracy)
- [ ] Performance: GPU lookup < 10ms for 100k embeddings

---

## Phase 4: Inference Visualizer (tools/pixel_inference.py)

**Status:** Pending (depends on Phase 3)

**Goal:** Visualize inference as a path across labeled word tiles in pixel-space.

### Step 4.1: Load Embedding Table from PDB
- [ ] Implement `load_embedding_table(pdb_path)` function
- [ ] Decode pixel rows back to vectors
- [ ] Map Hilbert indices back to word IDs
- [ ] Return `Dict[int, EmbeddingVector]`

**Verification:** Successfully loads "embedding_table" region, contains all words

### Step 4.2: Tokenize Input Prompt
- [ ] Implement `tokenize(prompt)` function
- [ ] Convert text to token IDs (use wordbase word IDs for simplicity)
- [ ] Handle out-of-vocabulary words gracefully

**Verification:** Tokenization works for "hello world", returns valid word IDs

### Step 4.3: GPU Neighbor Lookup Integration
- [ ] Implement `lookup_neighbors(token_id, k)` function
- [ ] Load query vector from embedding table
- [ ] Dispatch GPU shader via wgpu
- [ ] Return k-nearest Hilbert indices

**Verification:** Returns indices, nearest neighbor includes self (distance = 0)

### Step 4.4: Generate Next Token
- [ ] Implement `generate_next_token(context)` function
- [ ] Simple prediction: choose nearest neighbor with highest confidence
- [ ] Context window: maintain last N tokens (N = 5 for prototype)

**Verification:** Generates plausible next tokens (not random garbage)

### Step 4.5: Render Inference Path
- [ ] Implement `render_inference_path(trace, output_png)` function
- [ ] Draw 2D grid with word labels at Hilbert coordinates
- [ ] Highlight visited tiles in sequence (path visualization)
- [ ] Color-code by similarity score

**Verification:** Output PNG shows visible path, tiles are labeled

### Step 4.6: Compute Frame Deltas
- [ ] Implement `compute_frame_deltas(steps)` function
- [ ] Compute pixel diff between consecutive inference steps
- [ ] Store deltas as bytes for animation

**Verification:** Deltas are non-zero when activations change, zero otherwise

**Acceptance Criteria:**
- [ ] End-to-end inference: prompt → tokenize → lookup → generate → visualize
- [ ] Output PNG shows labeled word tiles and inference path
- [ ] Frame deltas capture activation drift between steps
- [ ] Reuse existing boot-trace diffing tooling (verification)

---

## Phase 5: Integration Testing

**Status:** Pending (depends on Phase 4)

**Goal:** End-to-end verification of the entire pixel-embedding pipeline.

### Step 5.1: Wordbase → Embeddings → PDB Round-Trip
- [ ] Run Phase 1 (sync_wordbase.py)
- [ ] Run Phase 2 (spatial_embedding.py)
- [ ] Verify PDB can be decoded back to byte-identical vectors

**Verification:** `diff <(encode) <(decode)` returns zero

### Step 5.2: GPU Lookup Baseline Comparison
- [ ] Run Phase 3 queries on GPU and CPU
- [ ] Compare top-k results for 100 random queries
- [ ] Report accuracy and latency

**Verification:** Top-1 accuracy ≥ 95%, GPU latency < 10ms

### Step 5.3: Inference Path Visualization
- [ ] Run Phase 4 with sample prompt ("The quick brown fox")
- [ ] Verify path is plausible (follows semantic neighborhoods)
- [ ] Check frame deltas show meaningful drift

**Verification:** Path visits semantically related tiles, deltas non-zero

### Step 5.4: Performance Benchmarking
- [ ] Measure embedding projection time (Phase 2)
- [ ] Measure GPU lookup latency (Phase 3)
- [ ] Measure inference end-to-end time (Phase 4)

**Verification:** All targets met per project standards

**Acceptance Criteria:**
- [ ] All verification gates pass
- [ ] Round-trip accuracy = 100% (byte-identical)
- [ ] GPU lookup accuracy ≥ 95% vs CPU baseline
- [ ] Inference visualization is interpretable by human
- [ ] Performance targets met (see below)

---

## Phase 6: Performance Targets & Optimization

**Status:** Pending (depends on Phase 5)

**Goal:** Meet or exceed project performance baselines.

### Metrics and Targets

| Metric | Baseline | Target | Status |
|--------|----------|--------|--------|
| Embedding projection (10k words) | ~5s | ≤3s | ⏳ TBD |
| GPU lookup latency (100k embeddings, k=10) | ~50ms | ≤10ms | ⏳ TBD |
| Inference end-to-end (5 tokens) | ~100ms | ≤50ms | ⏳ TBD |
| PDB encode/decode round-trip | ~1s | ≤500ms | ⏳ TBD |
| Memory usage (100k embeddings) | ~500MB | ≤1GB | ⏳ TBD |

### Optimization Strategies

1. **Embedding Projection:**
   - Batch UMAP projection (avoid per-word overhead)
   - Cache intermediate results
   - Consider PCA for faster 2D projection (lower quality)

2. **GPU Lookup:**
   - Use shared memory for query vector broadcast
   - Implement GPU radix sort for top-k (vs atomic ops)
   - Consider approximate nearest neighbor (FAISS-style) for scale

3. **Inference:**
   - Batch token lookups (dispatch once for multiple queries)
   - Cache neighbor results for repeated tokens
   - Parallelize path rendering (GPU compositing)

**Verification:** Run performance benchmarks, compare against targets

**Acceptance Criteria:**
- [ ] All performance targets met or exceeded
- [ ] Bottleneck analysis complete (if any targets missed)
- [ ] Optimization plan documented (if needed for Phase 7)

---

## Phase 7: Optional Extensions (Future Work)

**Status:** Not started

### Possible Extensions

1. **Attention as Territory Contention:**
   - Model multi-head attention as faction competition for Hilbert territory
   - Visualize attention weights as territory claim intensity

2. **Context Window as Physical Border:**
   - Extend cartridge size = larger context window
   - Cost model: pixel budget = context budget

3. **Training as Boot-Trace Diffing:**
   - Represent weight updates as frame deltas
   - Reuse verification tooling for training metrics

4. **Multilingual Support:**
   - Extend to wordbase multilingual translations
   - Visualize cross-lingual semantic neighborhoods

5. **Integration with Visual Audio Codec:**
   - Store embeddings in VAC containers instead of PDB
   - Use dual-band encoding (semantic + byte layers)

**Acceptance Criteria:** None (optional extensions)

---

## Verification Gates Summary

| Phase | Verification Gate | Command / Test |
|-------|-------------------|----------------|
| 1 | Wordbase/voicebook sync | `python3 tools/sync_wordbase.py --verify` |
| 2 | Embedding round-trip | `python3 tools/test_embedding_roundtrip.py` |
| 3 | GPU lookup accuracy | `python3 tools/test_gpu_lookup_accuracy.py` |
| 4 | Inference visualization | `python3 tools/pixel_inference.py "The quick brown fox" --verify` |
| 5 | End-to-end integration | `python3 tools/test_integration.py` |
| 6 | Performance benchmarks | `python3 tools/bench_performance.py` |

---

**Next Phase:** Phase 1 — Vocabulary Substrate
**Entry Point:** `tools/sync_wordbase.py`
**Dependencies:** None (standalone utility)
**Estimated Time:** 1-2 hours

---

**Last Updated:** 2026-08-18
**Status:** Planning Complete — Ready for Phase 1 Implementation
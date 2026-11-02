#!/usr/bin/env python3
"""
Pixel-Embedding Spatializer

This module projects voicebook word embeddings into 2D space and encodes them as
pixel rows in PDB format for GPU-native nearest-neighbor lookup.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import numpy as np
from pathlib import Path
import json
import struct

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("WARNING: sentence-transformers not installed. Using random embeddings.")

try:
    import umap
except ImportError:
    print("WARNING: umap-learn not installed. Using random projection.")

@dataclass
class EmbeddingVector:
    word: str
    vector: np.ndarray  # Shape: (embedding_dim,)
    hilbert_index: int
    pixel_row: bytes    # RGBA encoded (vector_dim * 4 bytes)


def xy2d(n: int, x: int, y: int) -> int:
    """Hilbert curve inverse mapping (x,y -> d)"""
    d = 0
    s = n // 2
    while s > 0:
        rx = (x & s) > 0
        ry = (y & s) > 0
        d += s * s * ((3 * rx) ^ ry)
        x, y = rot(s, x, y, rx, ry)
        s //= 2
    return d

def rot(n: int, x: int, y: int, rx: bool, ry: bool) -> Tuple[int, int]:
    if not ry:
        if rx:
            x = n - 1 - x
            y = n - 1 - y
        x, y = y, x
    return x, y

class EmbeddingSpatializer:
    def __init__(
        self,
        voicebook_path: str = "voicebook",
        embedding_model: str = "all-MiniLM-L6-v2",
        output_pdb: str = "embedding_table.pdb.png",
        tile_size: int = 4096,
    ):
        self.voicebook_path = Path(voicebook_path)
        self.embedding_model_name = embedding_model
        self.output_pdb_path = Path(output_pdb)
        self.tile_size = tile_size
        self.embedding_model = None

    def load_vocabulary(self) -> List[str]:
        words = []
        for p in self.voicebook_path.glob("*.wav"):
            stem = p.stem.split('_')[0].strip("?.!,").lower()
            if stem.isalpha():
                words.append(stem)
        return list(set(words))

    def compute_embeddings(self, words: List[str]) -> np.ndarray:
        try:
            self.embedding_model = SentenceTransformer(self.embedding_model_name)
            print("Computing embeddings...")
            return self.embedding_model.encode(words)
        except NameError:
            print("[STUB] Using random embeddings")
            return np.random.randn(len(words), 384).astype(np.float32)

    def project_to_2d(self, embeddings: np.ndarray) -> np.ndarray:
        try:
            print("Projecting to 2D using UMAP...")
            reducer = umap.UMAP(n_components=2, metric='cosine', random_state=42)
            coords = reducer.fit_transform(embeddings)
            # Normalize to [0, 1]
            coords -= coords.min(axis=0)
            coords /= coords.max(axis=0)
            return coords.astype(np.float32)
        except NameError:
            print("[STUB] Using random 2D projection")
            return np.random.rand(len(embeddings), 2).astype(np.float32)

    def map_to_hilbert(self, coords: np.ndarray) -> List[int]:
        print("Mapping to Hilbert curve...")
        indices = []
        n = self.tile_size
        for i in range(coords.shape[0]):
            x = int(coords[i, 0] * (n - 1))
            y = int(coords[i, 1] * (n - 1))
            d = xy2d(n, x, y)
            indices.append(d)
        return indices

    def encode_as_pixels(self, vectors: np.ndarray) -> List[bytes]:
        print("Encoding as pixels...")
        rows = []
        for vec in vectors:
            row_bytes = b''
            for val in vec:
                # Store as 32-bit float (4 bytes per float, acts as RGBA pixel)
                row_bytes += struct.pack('<f', val)
            rows.append(row_bytes)
        return rows

    def store_in_pdb(self, embeddings: List[EmbeddingVector]) -> None:
        print(f"Storing {len(embeddings)} words in PDB format at {self.output_pdb_path}")
        # Save metadata and a dummy png/bin for the prototype
        meta = []
        for e in embeddings:
            meta.append({
                "word": e.word,
                "hilbert_index": e.hilbert_index
            })
        
        meta_path = str(self.output_pdb_path) + ".meta.json"
        with open(meta_path, 'w') as f:
            json.dump(meta, f, indent=2)
            
        print(f"Saved metadata to {meta_path}")

    def run(self) -> None:
        words = self.load_vocabulary()
        print(f"Loaded {len(words)} unique words from voicebook")
        if not words:
            print("No words found, exiting.")
            return
            
        embeddings = self.compute_embeddings(words)
        spatials = self.project_to_2d(embeddings)
        hilbert_indices = self.map_to_hilbert(spatials)
        pixel_rows = self.encode_as_pixels(embeddings)

        vecs = []
        for i, word in enumerate(words):
            vecs.append(EmbeddingVector(
                word=word,
                vector=embeddings[i],
                hilbert_index=hilbert_indices[i],
                pixel_row=pixel_rows[i]
            ))

        self.store_in_pdb(vecs)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--voicebook", default="voicebook")
    parser.add_argument("--model", default="all-MiniLM-L6-v2")
    parser.add_argument("--output", default="embedding_table.pdb.png")
    parser.add_argument("--tile-size", type=int, default=4096)
    
    args = parser.parse_args()
    
    s = EmbeddingSpatializer(args.voicebook, args.model, args.output, args.tile_size)
    s.run()

if __name__ == "__main__":
    main()

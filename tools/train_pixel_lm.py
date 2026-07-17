#!/usr/bin/env python3
"""
Pixel-token transformer training script.

Trains a small decoder-only transformer on pixel-corpus data.
Vocabulary: top ~16k words from wordbase + specials (IDs 0-15 reserved).

Usage:
    # Full training
    python3 tools/train_pixel_lm.py --corpus data/corpus.npy --embeddings models/pixel_embeddings.npz

    # Fast smoke test (tiny corpus, few steps)
    python3 tools/train_pixel_lm.py --corpus data/corpus.npy --embeddings models/pixel_embeddings.npz --fast-mode
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.pixel_embeddings import PixelEmbeddings
from src.pixel_tokenizer import PixelTokenizer, SpecialTokens


# ============================================================================
# Dataset
# ============================================================================

class PixelCorpusDataset(Dataset):
    """Dataset for pixel-corpus training data."""

    def __init__(self, corpus_path: Path, seq_len: int = 512):
        """
        Load corpus from numpy file.

        Args:
            corpus_path: Path to .npy file with word ID sequences
            seq_len: Maximum sequence length for training
        """
        # Load corpus
        self.corpus = np.load(corpus_path, allow_pickle=True)

        # Handle different corpus formats
        if self.corpus.ndim == 1:
            # Flat sequence: split into chunks
            self.sequences = self._split_into_chunks(self.corpus, seq_len)
        elif self.corpus.ndim == 2:
            # Already sequences: ensure each is <= seq_len
            self.sequences = [seq[:seq_len] for seq in self.corpus if len(seq) > 1]
        else:
            raise ValueError(f"Unexpected corpus shape: {self.corpus.shape}")

        print(f"Loaded {len(self.sequences)} sequences from {corpus_path}")

    def _split_into_chunks(self, flat_ids: np.ndarray, seq_len: int) -> List[np.ndarray]:
        """Split flat ID sequence into chunks of length seq_len."""
        chunks = []
        for i in range(0, len(flat_ids) - seq_len, seq_len):
            chunk = flat_ids[i:i + seq_len]
            if len(chunk) == seq_len:
                chunks.append(chunk)
        return chunks

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get input and target sequences.

        For language modeling: input = tokens[:-1], target = tokens[1:]
        """
        seq = self.sequences[idx]
        input_ids = torch.tensor(seq[:-1], dtype=torch.long)
        target_ids = torch.tensor(seq[1:], dtype=torch.long)
        return input_ids, target_ids


class TinyCorpusDataset(Dataset):
    """Tiny synthetic corpus for fast smoke testing."""

    def __init__(self, vocab_size: int = 1000, n_sequences: int = 100, seq_len: int = 64):
        """Generate synthetic word ID sequences."""
        self.sequences = []
        for _ in range(n_sequences):
            # Random sequence with some structure (biased towards lower IDs)
            seq = np.random.randint(1, min(vocab_size, 1000), size=seq_len)
            self.sequences.append(seq)
        print(f"Generated {len(self.sequences)} synthetic sequences for fast mode")

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        seq = self.sequences[idx]
        input_ids = torch.tensor(seq[:-1], dtype=torch.long)
        target_ids = torch.tensor(seq[1:], dtype=torch.long)
        return input_ids, target_ids


# ============================================================================
# Model
# ============================================================================

class PixelTransformer(nn.Module):
    """Decoder-only transformer for pixel-token language modeling."""

    def __init__(
        self,
        vocab_size: int,
        d_model: int = 256,
        n_head: int = 8,
        n_layers: int = 6,
        d_ff: int = 1024,
        max_seq_len: int = 512,
        dropout: float = 0.1,
        embedding_matrix: Optional[np.ndarray] = None,
    ):
        """
        Initialize transformer.

        Args:
            vocab_size: Vocabulary size (including special tokens)
            d_model: Model dimension
            n_head: Number of attention heads
            n_layers: Number of transformer layers
            d_ff: Feed-forward dimension
            max_seq_len: Maximum sequence length
            dropout: Dropout rate
            embedding_matrix: Pre-trained embeddings (vocab_size, d_model) or None
        """
        super().__init__()

        self.vocab_size = vocab_size
        self.d_model = d_model
        self.n_head = n_head
        self.n_layers = n_layers

        # Token embeddings
        if embedding_matrix is not None:
            assert embedding_matrix.shape[0] == vocab_size, \
                f"Embedding vocab size {embedding_matrix.shape[0]} != vocab_size {vocab_size}"
            self.token_embedding = nn.Embedding.from_pretrained(
                torch.FloatTensor(embedding_matrix),
                freeze=False  # Allow fine-tuning
            )
            if embedding_matrix.shape[1] != d_model:
                # Project embeddings to d_model
                self.embedding_proj = nn.Linear(embedding_matrix.shape[1], d_model)
            else:
                self.embedding_proj = None
        else:
            self.token_embedding = nn.Embedding(vocab_size, d_model)
            self.embedding_proj = None

        # Position embeddings
        self.position_embedding = nn.Embedding(max_seq_len, d_model)

        # Transformer decoder layers
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=d_model,
            nhead=n_head,
            dim_feedforward=d_ff,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerDecoder(decoder_layer, num_layers=n_layers)

        # Output projection
        self.output_proj = nn.Linear(d_model, vocab_size)

        # Dropout
        self.dropout = nn.Dropout(dropout)

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize model weights."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Args:
            input_ids: (batch_size, seq_len) token IDs

        Returns:
            logits: (batch_size, seq_len, vocab_size)
        """
        batch_size, seq_len = input_ids.shape

        # Token embeddings
        token_emb = self.token_embedding(input_ids)  # (batch_size, seq_len, emb_dim)
        if self.embedding_proj is not None:
            token_emb = self.embedding_proj(token_emb)  # (batch_size, seq_len, d_model)

        # Position embeddings
        positions = torch.arange(seq_len, device=input_ids.device).unsqueeze(0)  # (1, seq_len)
        pos_emb = self.position_embedding(positions)  # (1, seq_len, d_model)

        # Combine embeddings
        x = self.dropout(token_emb + pos_emb)  # (batch_size, seq_len, d_model)

        # Transformer decoder (causal mask)
        causal_mask = self._generate_causal_mask(seq_len, device=input_ids.device)
        x = self.transformer(x, x, tgt_mask=causal_mask)  # (batch_size, seq_len, d_model)

        # Output projection
        logits = self.output_proj(x)  # (batch_size, seq_len, vocab_size)

        return logits

    def _generate_causal_mask(self, seq_len: int, device: torch.device) -> torch.Tensor:
        """Generate causal mask for decoder."""
        mask = torch.triu(torch.ones(seq_len, seq_len, device=device), diagonal=1)
        mask = mask.masked_fill(mask.bool(), float('-inf'))
        return mask


# ============================================================================
# Unigram baseline
# ============================================================================

def compute_unigram_perplexity(corpus_ids: List[np.ndarray], vocab_size: int) -> float:
    """
    Compute unigram baseline perplexity.

    Unigram model: P(w) = count(w) / total_tokens

    Args:
        corpus_ids: List of sequences (word IDs)
        vocab_size: Vocabulary size

    Returns:
        Unigram perplexity
    """
    # Count token frequencies
    counts = np.zeros(vocab_size, dtype=np.int64)
    total_tokens = 0

    for seq in corpus_ids:
        for token_id in seq:
            if 0 <= token_id < vocab_size:
                counts[token_id] += 1
                total_tokens += 1

    # Avoid division by zero
    if total_tokens == 0:
        return float('inf')

    # Compute unigram probabilities with add-1 smoothing
    probs = (counts + 1) / (total_tokens + vocab_size)

    # Compute log probabilities
    log_probs = np.log(probs + 1e-10)  # Avoid log(0)

    # Compute average negative log likelihood
    nll = 0.0
    n = 0
    for seq in corpus_ids:
        for token_id in seq:
            if 0 <= token_id < vocab_size:
                nll -= log_probs[token_id]
                n += 1

    if n == 0:
        return float('inf')

    avg_nll = nll / n
    perplexity = np.exp(avg_nll)

    return perplexity


# ============================================================================
# Training
# ============================================================================

def train(
    model: PixelTransformer,
    train_loader: DataLoader,
    val_loader: DataLoader,
    n_epochs: int,
    device: torch.device,
    learning_rate: float = 1e-4,
) -> Tuple[List[float], List[float]]:
    """
    Train the model.

    Args:
        model: Model to train
        train_loader: Training data loader
        val_loader: Validation data loader
        n_epochs: Number of epochs
        device: Device to train on
        learning_rate: Learning rate

    Returns:
        (train_losses, val_losses) lists
    """
    optimizer = AdamW(model.parameters(), lr=learning_rate)
    criterion = nn.CrossEntropyLoss(ignore_index=-100)

    train_losses = []
    val_losses = []

    for epoch in range(n_epochs):
        # Training
        model.train()
        epoch_train_loss = 0.0
        n_batches = 0

        for batch_idx, (input_ids, target_ids) in enumerate(train_loader):
            input_ids = input_ids.to(device)
            target_ids = target_ids.to(device)

            optimizer.zero_grad()

            # Forward pass
            logits = model(input_ids)  # (batch_size, seq_len, vocab_size)

            # Compute loss
            batch_size, seq_len, vocab_size = logits.shape
            loss = criterion(
                logits.view(-1, vocab_size),
                target_ids.view(-1)
            )

            # Backward pass
            loss.backward()

            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()

            epoch_train_loss += loss.item()
            n_batches += 1

        avg_train_loss = epoch_train_loss / n_batches if n_batches > 0 else 0.0
        train_losses.append(avg_train_loss)

        # Validation
        model.eval()
        epoch_val_loss = 0.0
        n_val_batches = 0

        with torch.no_grad():
            for input_ids, target_ids in val_loader:
                input_ids = input_ids.to(device)
                target_ids = target_ids.to(device)

                logits = model(input_ids)
                batch_size, seq_len, vocab_size = logits.shape
                loss = criterion(
                    logits.view(-1, vocab_size),
                    target_ids.view(-1)
                )

                epoch_val_loss += loss.item()
                n_val_batches += 1

        avg_val_loss = epoch_val_loss / n_val_batches if n_val_batches > 0 else 0.0
        val_losses.append(avg_val_loss)

        # Compute perplexities
        train_ppl = np.exp(avg_train_loss) if avg_train_loss > 0 else float('inf')
        val_ppl = np.exp(avg_val_loss) if avg_val_loss > 0 else float('inf')

        print(f"Epoch {epoch + 1}/{n_epochs}: "
              f"Train loss={avg_train_loss:.4f} (ppl={train_ppl:.2f}), "
              f"Val loss={avg_val_loss:.4f} (ppl={val_ppl:.2f})")

    return train_losses, val_losses


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Train pixel-token transformer")
    parser.add_argument("--corpus", type=str, help="Path to corpus .npy file")
    parser.add_argument("--embeddings", type=str, help="Path to embeddings .npz file")
    parser.add_argument("--wordbase", type=str, default="db/wordbase.db", help="Path to wordbase")
    parser.add_argument("--output", type=str, default="models/pixel_lm.pt", help="Output checkpoint path")
    parser.add_argument("--vocab-size", type=int, default=16000, help="Vocabulary size (excluding specials)")
    parser.add_argument("--d-model", type=int, default=256, help="Model dimension")
    parser.add_argument("--n-head", type=int, default=8, help="Number of attention heads")
    parser.add_argument("--n-layers", type=int, default=6, help="Number of transformer layers")
    parser.add_argument("--d-ff", type=int, default=1024, help="Feed-forward dimension")
    parser.add_argument("--seq-len", type=int, default=512, help="Maximum sequence length")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size")
    parser.add_argument("--n-epochs", type=int, default=10, help="Number of epochs")
    parser.add_argument("--learning-rate", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--fast-mode", action="store_true", help="Fast smoke test (tiny corpus, few steps)")
    parser.add_argument("--device", type=str, default="cpu", help="Device to train on")
    args = parser.parse_args()

    # Device
    device = torch.device(args.device)
    print(f"Using device: {device}")

    # Fast mode overrides
    if args.fast_mode:
        print("FAST MODE: Using tiny synthetic corpus and minimal training")
        args.vocab_size = 1000
        args.d_model = 128
        args.n_head = 4
        args.n_layers = 2
        args.d_ff = 512
        args.seq_len = 64
        args.batch_size = 4
        args.n_epochs = 3

    # Vocabulary size including specials
    full_vocab_size = SpecialTokens.NUM_SPECIAL + args.vocab_size
    print(f"Vocabulary size: {args.vocab_size} words + {SpecialTokens.NUM_SPECIAL} specials = {full_vocab_size}")

    # Load or build embeddings
    if args.embeddings and os.path.exists(args.embeddings):
        print(f"Loading embeddings from {args.embeddings}")
        embedding_data = np.load(args.embeddings, allow_pickle=True)
        embedding_matrix = embedding_data['embeddings']
        print(f"Loaded embedding matrix shape: {embedding_matrix.shape}")

        # Ensure embeddings match vocab size
        if embedding_matrix.shape[0] > args.vocab_size:
            embedding_matrix = embedding_matrix[:args.vocab_size]
            print(f"Truncated embeddings to vocab size {args.vocab_size}")
        elif embedding_matrix.shape[0] < args.vocab_size:
            # Pad with random embeddings
            n_pad = args.vocab_size - embedding_matrix.shape[0]
            padding = np.random.randn(n_pad, embedding_matrix.shape[1]) * 0.02
            embedding_matrix = np.vstack([embedding_matrix, padding])
            print(f"Padded embeddings with {n_pad} random vectors")
    else:
        print("No embeddings provided, using random initialization")
        embedding_matrix = None

    # Load dataset
    if args.fast_mode:
        train_dataset = TinyCorpusDataset(vocab_size=args.vocab_size, n_sequences=100, seq_len=args.seq_len)
        val_dataset = TinyCorpusDataset(vocab_size=args.vocab_size, n_sequences=20, seq_len=args.seq_len)
    elif args.corpus and os.path.exists(args.corpus):
        train_dataset = PixelCorpusDataset(Path(args.corpus), seq_len=args.seq_len)
        # Use 10% of data for validation
        n_val = max(1, len(train_dataset) // 10)
        n_train = len(train_dataset) - n_val
        train_dataset, val_dataset = torch.utils.data.random_split(
            train_dataset, [n_train, n_val]
        )
        print(f"Train samples: {n_train}, Val samples: {n_val}")
    else:
        raise ValueError("Must provide --corpus or use --fast-mode")

    # Data loaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=0,  # CPU-safe
        collate_fn=lambda batch: torch.utils.data.default_collate(batch)
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )

    # Compute unigram baseline
    print("\nComputing unigram baseline perplexity...")
    corpus_ids = [train_dataset[i][0].numpy() for i in range(min(len(train_dataset), 1000))]
    unigram_ppl = compute_unigram_perplexity(corpus_ids, full_vocab_size)
    print(f"Unigram baseline perplexity: {unigram_ppl:.2f}")

    # Create model
    print(f"\nCreating model: {args.n_layers} layers, {args.d_model} dim, {args.n_head} heads")
    model = PixelTransformer(
        vocab_size=full_vocab_size,
        d_model=args.d_model,
        n_head=args.n_head,
        n_layers=args.n_layers,
        d_ff=args.d_ff,
        max_seq_len=args.seq_len,
        embedding_matrix=embedding_matrix,
    )
    model = model.to(device)

    # Count parameters
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {n_params:,}")

    # Train
    print("\nTraining...")
    train_losses, val_losses = train(
        model,
        train_loader,
        val_loader,
        n_epochs=args.n_epochs,
        device=device,
        learning_rate=args.learning_rate,
    )

    # Final validation perplexity
    final_val_ppl = np.exp(val_losses[-1]) if val_losses else float('inf')
    print(f"\nFinal validation perplexity: {final_val_ppl:.2f}")
    print(f"Unigram baseline perplexity: {unigram_ppl:.2f}")

    if final_val_ppl < unigram_ppl:
        print("✓ Model beats unigram baseline!")
    else:
        print("✗ Model does NOT beat unigram baseline (may need more training/data)")

    # Save checkpoint
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        'model_state_dict': model.state_dict(),
        'config': {
            'vocab_size': full_vocab_size,
            'd_model': args.d_model,
            'n_head': args.n_head,
            'n_layers': args.n_layers,
            'd_ff': args.d_ff,
            'max_seq_len': args.seq_len,
        },
        'train_losses': train_losses,
        'val_losses': val_losses,
        'unigram_perplexity': unigram_ppl,
        'val_perplexity': final_val_ppl,
    }

    torch.save(checkpoint, output_path)
    print(f"Checkpoint saved to {output_path}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nTraining interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
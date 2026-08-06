#!/usr/bin/env python3
"""
Pixel-Token Language Model Training Script

Trains a small decoder-only transformer on pixel-encoded audio representations.
Supports both real corpus training and fast mode with synthetic data for testing.
"""

import argparse
import sys
import os
import json
import math
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# Special tokens
PAD_TOKEN = 0
UNK_TOKEN = 1
BOS_TOKEN = 2
EOS_TOKEN = 3
MASK_TOKEN = 4
SPECIAL_TOKENS = [PAD_TOKEN, UNK_TOKEN, BOS_TOKEN, EOS_TOKEN, MASK_TOKEN]

# Default model configuration
DEFAULT_D_MODEL = 256
DEFAULT_N_HEADS = 8
DEFAULT_N_LAYERS = 6
DEFAULT_D_FF = 1024
DEFAULT_MAX_SEQ_LEN = 512
DEFAULT_DROPOUT = 0.1

# Default training configuration
DEFAULT_BATCH_SIZE = 32
DEFAULT_N_EPOCHS = 10
DEFAULT_LEARNING_RATE = 1e-4
DEFAULT_WEIGHT_DECAY = 0.01
DEFAULT_VOCAB_SIZE = 16000


class PixelCorpusDataset(Dataset):
    """Dataset for loading and batching pixel corpus data."""
    
    def __init__(self, corpus_path: str, seq_len: int = 512):
        """
        Initialize dataset from corpus file.
        
        Args:
            corpus_path: Path to .npy corpus file (1D or 2D array)
            seq_len: Maximum sequence length
        """
        self.seq_len = seq_len
        corpus_path = Path(corpus_path)
        
        # Load corpus
        corpus_data = np.load(corpus_path)
        
        # Handle 1D or 2D arrays
        if corpus_data.ndim == 1:
            # Flat array - split into sequences
            self.sequences = []
            for i in range(0, len(corpus_data) - self.seq_len, self.seq_len):
                # Take chunks of seq_len (not seq_len+1) to ensure final seq is shorter
                seq = corpus_data[i:i + self.seq_len]
                if len(seq) >= 2:  # Need at least 2 for input/target split
                    self.sequences.append(seq)
        elif corpus_data.ndim == 2:
            # Already split - flatten to list of sequences
            self.sequences = []
            for seq in corpus_data:
                if len(seq) >= 2:
                    # Truncate if needed to ensure output < seq_len
                    if len(seq) > self.seq_len:
                        seq = seq[:self.seq_len]
                    self.sequences.append(seq)
        else:
            raise ValueError(f"Invalid corpus shape: {corpus_data.shape}")
        
        if len(self.sequences) == 0:
            raise ValueError(f"No valid sequences found in corpus")
    
    def __len__(self) -> int:
        return len(self.sequences)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """Get a training example (input_ids, target_ids)."""
        seq = self.sequences[idx]
        
        # Truncate to seq_len + 1, but keep at least 2 elements for input/target
        if len(seq) > self.seq_len + 1:
            seq = seq[:self.seq_len]
        elif len(seq) < 2:
            # Pad to minimum length of 2 (one input, one target)
            seq = np.pad(seq, (0, 2 - len(seq)), constant_values=PAD_TOKEN)
        
        # Split into input and target (shifted by one)
        # This ensures input and target are both shorter than seq_len
        input_ids = torch.LongTensor(seq[:-1])
        target_ids = torch.LongTensor(seq[1:])
        
        return input_ids, target_ids


class PixelTransformer(nn.Module):
    """Decoder-only transformer for pixel token language modeling."""
    
    def __init__(
        self,
        vocab_size: int,
        d_model: int = DEFAULT_D_MODEL,
        n_head: int = DEFAULT_N_HEADS,
        n_layers: int = DEFAULT_N_LAYERS,
        d_ff: int = DEFAULT_D_FF,
        max_seq_len: int = DEFAULT_MAX_SEQ_LEN,
        dropout: float = DEFAULT_DROPOUT,
    ):
        """
        Initialize PixelTransformer.
        
        Args:
            vocab_size: Size of vocabulary
            d_model: Model dimension
            n_head: Number of attention heads
            n_layers: Number of transformer layers
            d_ff: Feed-forward dimension
            max_seq_len: Maximum sequence length
            dropout: Dropout rate
        """
        super().__init__()
        
        self.vocab_size = vocab_size
        self.d_model = d_model
        self.n_head = n_head
        self.n_layers = n_layers
        self.d_ff = d_ff
        self.max_seq_len = max_seq_len
        self.dropout = dropout
        
        # Embedding layer
        self.token_embedding = nn.Embedding(vocab_size, d_model)
        self.position_embedding = nn.Embedding(max_seq_len, d_model)
        
        # Use a simpler approach: TransformerEncoder with causal attention
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_head,
            dim_feedforward=d_ff,
            dropout=dropout,
            batch_first=True,  # [batch, seq_len, d_model]
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        
        # Output layer
        self.output_layer = nn.Linear(d_model, vocab_size)
        
        # Dropout
        self.dropout_layer = nn.Dropout(dropout)
        
        # Initialize weights
        self._init_weights()
    
    def _init_weights(self):
        """Initialize model weights."""
        # Initialize embeddings
        nn.init.normal_(self.token_embedding.weight, mean=0.0, std=0.02)
        nn.init.normal_(self.position_embedding.weight, mean=0.0, std=0.02)
        
        # Initialize linear layers
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_normal_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
    
    def _generate_causal_mask(self, seq_len: int, device: torch.device) -> torch.Tensor:
        """
        Generate causal attention mask.
        
        Args:
            seq_len: Sequence length
            device: Device to create mask on
        
        Returns:
            Causal mask of shape [seq_len, seq_len]
        """
        # Create a mask where positions can only attend to previous positions
        mask = torch.triu(torch.ones(seq_len, seq_len, device=device), diagonal=1)
        return mask
    
    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.
        
        Args:
            input_ids: Input token IDs [batch_size, seq_len]
        
        Returns:
            Logits [batch_size, seq_len, vocab_size]
        """
        batch_size, seq_len = input_ids.shape
        
        # Create position indices
        positions = torch.arange(seq_len, dtype=torch.long, device=input_ids.device)
        positions = positions.unsqueeze(0).expand(batch_size, -1)
        
        # Get embeddings
        token_emb = self.token_embedding(input_ids)  # [batch_size, seq_len, d_model]
        pos_emb = self.position_embedding(positions)  # [batch_size, seq_len, d_model]
        
        # Combine embeddings
        x = token_emb + pos_emb
        x = self.dropout_layer(x)
        
        # Generate causal mask
        causal_mask = self._generate_causal_mask(seq_len, input_ids.device)
        
        # Apply transformer encoder with causal masking
        # src_key_padding_mask: mask padding tokens (all False for now)
        x = self.transformer_encoder(
            x,
            mask=causal_mask,
        )
        
        # Output logits
        logits = self.output_layer(x)  # [batch_size, seq_len, vocab_size]
        
        return logits
    
    def get_param_count(self) -> int:
        """Get total parameter count."""
        return sum(p.numel() for p in self.parameters())


def compute_unigram_perplexity(train_loader: DataLoader, vocab_size: int, device: torch.device) -> float:
    """
    Compute unigram baseline perplexity from training data.
    
    Args:
        train_loader: Training data loader
        vocab_size: Vocabulary size
        device: Device to compute on
    
    Returns:
        Unigram perplexity
    """
    # Count token frequencies
    token_counts = torch.zeros(vocab_size, device=device)
    total_tokens = 0
    
    for input_ids, target_ids in train_loader:
        # Flatten and count
        flat = target_ids.view(-1)
        valid_mask = flat != PAD_TOKEN
        valid_tokens = flat[valid_mask]
        
        # Count frequencies
        unique, counts = torch.unique(valid_tokens, return_counts=True)
        token_counts[unique] += counts
        total_tokens += valid_tokens.numel()
    
    if total_tokens == 0:
        return float('inf')
    
    # Compute probabilities (add epsilon for numerical stability)
    epsilon = 1e-10
    probs = (token_counts + epsilon) / (total_tokens + vocab_size * epsilon)
    
    # Compute entropy
    nonzero = probs > 0
    entropy = -torch.sum(probs[nonzero] * torch.log(probs[nonzero]))
    
    # Perplexity = exp(entropy)
    perplexity = torch.exp(entropy).item()
    
    return perplexity


def compute_perplexity(loss: float) -> float:
    """Compute perplexity from cross-entropy loss."""
    return math.exp(loss)


def train_epoch(
    model: nn.Module,
    train_loader: DataLoader,
    optimizer: optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    """
    Train for one epoch.
    
    Args:
        model: Model to train
        train_loader: Training data loader
        optimizer: Optimizer
        criterion: Loss function
        device: Device to train on
    
    Returns:
        Average training loss
    """
    model.train()
    total_loss = 0.0
    num_batches = 0
    
    for input_ids, target_ids in train_loader:
        input_ids = input_ids.to(device)
        target_ids = target_ids.to(device)
        
        # Forward pass
        logits = model(input_ids)
        
        # Compute loss (flatten for cross-entropy)
        batch_size, seq_len, vocab_size = logits.shape
        loss = criterion(
            logits.view(-1, vocab_size),
            target_ids.view(-1)
        )
        
        # Backward pass
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
        num_batches += 1
    
    return total_loss / num_batches if num_batches > 0 else 0.0


def validate(
    model: nn.Module,
    val_loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    """
    Validate the model.
    
    Args:
        model: Model to validate
        val_loader: Validation data loader
        criterion: Loss function
        device: Device to validate on
    
    Returns:
        Average validation loss
    """
    model.eval()
    total_loss = 0.0
    num_batches = 0
    
    with torch.no_grad():
        for input_ids, target_ids in val_loader:
            input_ids = input_ids.to(device)
            target_ids = target_ids.to(device)
            
            # Forward pass
            logits = model(input_ids)
            
            # Compute loss
            batch_size, seq_len, vocab_size = logits.shape
            loss = criterion(
                logits.view(-1, vocab_size),
                target_ids.view(-1)
            )
            
            total_loss += loss.item()
            num_batches += 1
    
    return total_loss / num_batches if num_batches > 0 else 0.0


def generate_synthetic_corpus(
    vocab_size: int,
    n_sequences: int = 100,
    seq_len: int = 512,
) -> np.ndarray:
    """
    Generate synthetic corpus for fast mode testing.
    
    Args:
        vocab_size: Vocabulary size
        n_sequences: Number of sequences to generate
        seq_len: Sequence length
    
    Returns:
        2D numpy array of shape [n_sequences, seq_len + 1]
    """
    # Generate structured sequences (not random)
    sequences = []
    
    for i in range(n_sequences):
        # Create pattern with some structure
        seq = []
        pattern_start = (i * 7) % (vocab_size - 10) + 10
        
        for j in range(seq_len + 1):
            # Mix of pattern and randomness
            if j % 8 == 0:
                token = pattern_start
            elif j % 4 == 0:
                token = (pattern_start + 2) % vocab_size
            else:
                token = (pattern_start + j + i) % (vocab_size - 1) + 1
            
            seq.append(token)
        
        sequences.append(np.array(seq))
    
    return np.array(sequences)


def train(
    corpus_path: Optional[str] = None,
    embeddings_path: Optional[str] = None,
    output_path: str = "models/pixel_lm.pt",
    vocab_size: int = DEFAULT_VOCAB_SIZE,
    d_model: int = DEFAULT_D_MODEL,
    n_heads: int = DEFAULT_N_HEADS,
    n_layers: int = DEFAULT_N_LAYERS,
    d_ff: int = DEFAULT_D_FF,
    max_seq_len: int = DEFAULT_MAX_SEQ_LEN,
    dropout: float = DEFAULT_DROPOUT,
    batch_size: int = DEFAULT_BATCH_SIZE,
    n_epochs: int = DEFAULT_N_EPOCHS,
    learning_rate: float = DEFAULT_LEARNING_RATE,
    weight_decay: float = DEFAULT_WEIGHT_DECAY,
    device: str = "cuda",
    fast_mode: bool = False,
    vocab_size_fast: int = 1000,
    early_stop_patience: int = 4,
) -> Dict:
    """
    Main training function.
    
    Args:
        corpus_path: Path to pixel corpus .npy file
        embeddings_path: Path to pre-trained embeddings .npz file
        output_path: Output checkpoint path
        vocab_size: Vocabulary size
        d_model: Model dimension
        n_heads: Number of attention heads
        n_layers: Number of transformer layers
        d_ff: Feed-forward dimension
        max_seq_len: Maximum sequence length
        dropout: Dropout rate
        batch_size: Training batch size
        n_epochs: Number of training epochs
        learning_rate: Learning rate
        weight_decay: Weight decay
        device: Device (cuda or cpu)
        fast_mode: Use synthetic corpus for quick testing
        vocab_size_fast: Vocabulary size for fast mode
    
    Returns:
        Training results dictionary
    """
    # Set device
    device = torch.device(device if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # Handle fast mode
    if fast_mode:
        print("Running in FAST MODE with synthetic corpus")
        vocab_size = vocab_size_fast
        corpus_data = generate_synthetic_corpus(vocab_size, n_sequences=200, seq_len=256)
        max_seq_len = 256
        
        # Save to temporary file for dataset loading
        import tempfile
        temp_corpus = tempfile.NamedTemporaryFile(suffix='.npy', delete=False)
        np.save(temp_corpus.name, corpus_data)
        corpus_path = temp_corpus.name
        print(f"Generated synthetic corpus with {len(corpus_data)} sequences")
    else:
        if corpus_path is None:
            raise ValueError("corpus_path required when not in fast_mode")
        if not os.path.exists(corpus_path):
            raise ValueError(f"Corpus file not found: {corpus_path}")
    
    # Create datasets
    full_dataset = PixelCorpusDataset(corpus_path, seq_len=max_seq_len)
    
    # Split into train/val (90/10)
    train_size = int(0.9 * len(full_dataset))
    val_size = len(full_dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(
        full_dataset,
        [train_size, val_size],
        generator=torch.Generator().manual_seed(42)
    )
    
    print(f"Training samples: {len(train_dataset)}, Validation samples: {len(val_dataset)}")
    
    # Create data loaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
    )
    
    # Create model
    model = PixelTransformer(
        vocab_size=vocab_size,
        d_model=d_model,
        n_head=n_heads,
        n_layers=n_layers,
        d_ff=d_ff,
        max_seq_len=max_seq_len,
        dropout=dropout,
    ).to(device)
    
    n_params = model.get_param_count()
    print(f"Model parameters: {n_params:,}")
    print(f"Target range: 10-25M, actual: {n_params/1e6:.2f}M")
    
    # Load pre-trained embeddings if provided
    if embeddings_path and os.path.exists(embeddings_path):
        print(f"Loading pre-trained embeddings from {embeddings_path}")
        embeddings = np.load(embeddings_path)
        if 'embeddings' in embeddings:
            emb_array = embeddings['embeddings']
        else:
            emb_array = embeddings[list(embeddings.keys())[0]]
        
        # Load embeddings
        if emb_array.shape[0] >= vocab_size and emb_array.shape[1] == d_model:
            model.token_embedding.weight.data[:vocab_size] = torch.from_numpy(emb_array[:vocab_size])
            print("Loaded pre-trained embeddings")
        else:
            print(f"Warning: Embedding shape {emb_array.shape} doesn't match model ({vocab_size}, {d_model})")
    
    # Loss function (ignore padding)
    criterion = nn.CrossEntropyLoss(ignore_index=PAD_TOKEN)
    
    # Optimizer
    optimizer = optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
    )
    
    # Compute unigram baseline
    print("Computing unigram baseline...")
    unigram_ppl = compute_unigram_perplexity(train_loader, vocab_size, device)
    print(f"Unigram baseline perplexity: {unigram_ppl:.2f}")
    
    # Training loop
    train_losses = []
    val_losses = []
    best_val_loss = float('inf')
    epochs_without_improvement = 0

    print(f"\nStarting training for up to {n_epochs} epochs "
          f"(early stop after {early_stop_patience} epochs without improvement)...")

    for epoch in range(n_epochs):
        # Train
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
        train_losses.append(train_loss)
        
        # Validate
        val_loss = validate(model, val_loader, criterion, device)
        val_losses.append(val_loss)
        
        # Compute perplexity
        train_ppl = compute_perplexity(train_loss)
        val_ppl = compute_perplexity(val_loss)
        
        print(f"Epoch {epoch + 1}/{n_epochs}: "
              f"Train Loss: {train_loss:.4f} (PPL: {train_ppl:.2f}), "
              f"Val Loss: {val_loss:.4f} (PPL: {val_ppl:.2f})")
        
        # Save checkpoint
        checkpoint = {
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'epoch': epoch + 1,
            'train_losses': train_losses,
            'val_losses': val_losses,
            'val_perplexity': val_ppl,
            'unigram_perplexity': unigram_ppl,
            'config': {
                'vocab_size': vocab_size,
                'd_model': d_model,
                'n_head': n_heads,
                'n_layers': n_layers,
                'd_ff': d_ff,
                'max_seq_len': max_seq_len,
                'dropout': dropout,
            },
        }
        
        # Create output directory if needed
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # Only overwrite the checkpoint when validation loss actually improves.
        # Saving unconditionally every epoch means the final file on disk is
        # whatever the LAST epoch produced, which on a small corpus is
        # typically an overfit model far worse than the best one seen -
        # exactly what happened training on data/pixel_corpus/real_corpus.npy
        # (best val PPL 316 at epoch 9, final val PPL 1942 at epoch 15).
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            epochs_without_improvement = 0
            torch.save(checkpoint, output_path)
            print(f"  -> New best (val loss {val_loss:.4f}), checkpoint saved to {output_path}")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= early_stop_patience:
                print(f"  -> No improvement for {early_stop_patience} epochs, stopping early "
                      f"at epoch {epoch + 1}/{n_epochs}.")
                break

    # Reload the best checkpoint actually written to disk for an honest summary
    # (train_losses[-1]/val_losses[-1] are the LAST epoch, not the best one).
    best_checkpoint = torch.load(output_path, map_location=device, weights_only=False)

    print("\n" + "="*50)
    print("Training complete!")
    print(f"Best checkpoint from epoch: {best_checkpoint['epoch']}/{n_epochs}")
    print(f"Best validation loss: {best_checkpoint['val_losses'][-1]:.4f}")
    print(f"Best validation perplexity: {best_checkpoint['val_perplexity']:.2f}")
    print(f"Unigram baseline perplexity: {unigram_ppl:.2f}")
    print(f"Model beats baseline: {best_checkpoint['val_perplexity'] < unigram_ppl}")
    print(f"Checkpoint saved to: {output_path}")
    print("="*50)

    return best_checkpoint


def main():
    """Main entry point for command-line usage."""
    parser = argparse.ArgumentParser(
        description="Train Pixel-Token Language Model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Data arguments
    parser.add_argument(
        '--corpus',
        type=str,
        default=None,
        help='Path to pixel corpus .npy file (not required in fast-mode)',
    )
    parser.add_argument(
        '--embeddings',
        type=str,
        default=None,
        help='Path to pre-trained embeddings .npz file (not required in fast-mode)',
    )
    parser.add_argument(
        '--output',
        type=str,
        default='models/pixel_lm.pt',
        help='Output checkpoint path',
    )
    
    # Model architecture arguments
    parser.add_argument(
        '--vocab-size',
        type=int,
        default=DEFAULT_VOCAB_SIZE,
        help='Vocabulary size (top N words)',
    )
    parser.add_argument(
        '--d-model',
        type=int,
        default=DEFAULT_D_MODEL,
        help='Model dimension',
    )
    parser.add_argument(
        '--n-heads',
        type=int,
        default=DEFAULT_N_HEADS,
        help='Number of attention heads',
    )
    parser.add_argument(
        '--n-layers',
        type=int,
        default=DEFAULT_N_LAYERS,
        help='Number of transformer layers',
    )
    parser.add_argument(
        '--d-ff',
        type=int,
        default=DEFAULT_D_FF,
        help='Feed-forward dimension',
    )
    parser.add_argument(
        '--max-seq-len',
        type=int,
        default=DEFAULT_MAX_SEQ_LEN,
        help='Maximum sequence length',
    )
    parser.add_argument(
        '--dropout',
        type=float,
        default=DEFAULT_DROPOUT,
        help='Dropout rate',
    )
    
    # Training arguments
    parser.add_argument(
        '--batch-size',
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help='Training batch size',
    )
    parser.add_argument(
        '--n-epochs',
        type=int,
        default=DEFAULT_N_EPOCHS,
        help='Number of training epochs',
    )
    parser.add_argument(
        '--learning-rate',
        type=float,
        default=DEFAULT_LEARNING_RATE,
        help='Learning rate',
    )
    parser.add_argument(
        '--weight-decay',
        type=float,
        default=DEFAULT_WEIGHT_DECAY,
        help='Weight decay for regularization',
    )
    parser.add_argument(
        '--device',
        type=str,
        default='cuda',
        choices=['cuda', 'cpu'],
        help='Device to train on',
    )
    
    # Fast mode
    parser.add_argument(
        '--fast-mode',
        action='store_true',
        help='Use synthetic corpus for quick testing',
    )
    parser.add_argument(
        '--vocab-size-fast',
        type=int,
        default=1000,
        help='Vocab size for fast-mode synthetic data',
    )
    
    args = parser.parse_args()
    
    # Run training
    try:
        result = train(
            corpus_path=args.corpus,
            embeddings_path=args.embeddings,
            output_path=args.output,
            vocab_size=args.vocab_size,
            d_model=args.d_model,
            n_heads=args.n_heads,
            n_layers=args.n_layers,
            d_ff=args.d_ff,
            max_seq_len=args.max_seq_len,
            dropout=args.dropout,
            batch_size=args.batch_size,
            n_epochs=args.n_epochs,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            device=args.device,
            fast_mode=args.fast_mode,
            vocab_size_fast=args.vocab_size_fast,
        )
        print("\n✓ Training completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
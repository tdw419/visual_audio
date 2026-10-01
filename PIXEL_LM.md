# Pixel-Token Language Model (Pixel LM)

This document describes the pixel-token transformer language model training pipeline for Visual Audio.

## Overview

The Pixel LM is a small decoder-only transformer (10-25M parameters) trained on pixel-encoded audio representations. It learns to predict the next pixel token in a sequence, enabling generation of visual audio patterns.

## Architecture

### Model Specs

- **Type**: Decoder-only transformer
- **Parameters**: ~10-25M (configurable)
- **Model dimension (d_model)**: 256
- **Attention heads**: 8
- **Transformer layers**: 6
- **Feed-forward dimension**: 1024
- **Maximum sequence length**: 512 tokens
- **Dropout**: 0.1

### Vocabulary

- **Size**: Top ~16,000 words from wordbase + special tokens
- **Special tokens**: PAD, UNK, BOS, EOS, MASK, etc. (IDs 0-15 reserved)
- **OOV handling**: Words outside top 16k mapped to UNK token

### Embeddings

The model can use pre-trained pixel embeddings:

- **Source**: `models/pixel_embeddings.npz`
- **Shape**: (vocab_size, embedding_dim)
- **Training**: Embeddings are fine-tuned during model training (not frozen)

## Training Pipeline

### Data Preparation

The pixel corpus is a collection of word ID sequences derived from pixel-encoded audio data:

1. **Corpus format**: NumPy array (.npy file)
   - Flat: 1D array of word IDs (split into chunks during loading)
   - Sequences: 2D array (list of sequences)

2. **Sequence length**: Maximum 512 tokens per training example
3. **Language modeling setup**: Input = tokens[:-1], Target = tokens[1:]

### Training Command

```bash
# Full training with real corpus
python3 tools/train_pixel_lm.py \
    --corpus data/corpus.npy \
    --embeddings models/pixel_embeddings.npz \
    --output models/pixel_lm.pt \
    --vocab-size 16000 \
    --d-model 256 \
    --n-heads 8 \
    --n-layers 6 \
    --n-epochs 10 \
    --batch-size 32 \
    --learning-rate 1e-4 \
    --device cuda

# Fast mode for testing (synthetic data, fewer steps)
python3 tools/train_pixel_lm.py \
    --fast-mode \
    --output models/pixel_lm.pt \
    --n-epochs 3 \
    --device cpu
```

### Training Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--corpus` | path | Required | Path to pixel corpus .npy file (not required in fast-mode) |
| `--embeddings` | path | Required | Path to pre-trained embeddings .npz file (not required in fast-mode) |
| `--output` | path | models/pixel_lm.pt | Output checkpoint path |
| `--vocab-size` | int | 16000 | Vocabulary size (top N words) |
| `--d-model` | int | 256 | Model dimension |
| `--n-heads` | int | 8 | Number of attention heads |
| `--n-layers` | int | 6 | Number of transformer layers |
| `--d-ff` | int | 1024 | Feed-forward dimension |
| `--max-seq-len` | int | 512 | Maximum sequence length |
| `--dropout` | float | 0.1 | Dropout rate |
| `--batch-size` | int | 32 | Training batch size |
| `--n-epochs` | int | 10 | Number of training epochs |
| `--learning-rate` | float | 1e-4 | Learning rate |
| `--weight-decay` | float | 0.01 | Weight decay for regularization |
| `--device` | str | cuda | Device: cuda or cpu |
| `--fast-mode` | flag | False | Use synthetic corpus for quick testing |
| `--vocab-size-fast` | int | 1000 | Vocab size for fast-mode synthetic data |

### Training Process

1. **Load data**:
   - Load corpus from .npy file (real) or generate synthetic (fast-mode)
   - Load pre-trained embeddings if provided
   - Split into train/validation sets (90/10)

2. **Initialize model**:
   - Create PixelTransformer with specified architecture
   - Initialize weights (Xavier normal for linear, embedding init for embeddings)
   - Optionally load pre-trained embeddings

3. **Training loop**:
   - For each epoch:
     - Train on training set
     - Compute training loss (cross-entropy)
     - Validate on validation set
     - Compute validation perplexity
     - Save checkpoint if validation loss improves

4. **Checkpoint format**:
   ```python
   {
       'model_state_dict': torch.Tensor,  # Model weights
       'optimizer_state_dict': torch.Tensor,  # Optimizer state
       'epoch': int,  # Current epoch
       'train_losses': List[float],  # Training loss history
       'val_losses': List[float],  # Validation loss history
       'val_perplexity': float,  # Latest validation perplexity
       'unigram_perplexity': float,  # Unigram baseline perplexity
       'config': dict,  # Model configuration
   }
   ```

### Baseline Comparison

The training script computes a unigram baseline to verify the model is learning:

- **Unigram baseline**: Perplexity based on token frequency in training set
- **Model performance**: Should beat unigram baseline (lower perplexity)
- **Fast mode tolerance**: Model can be up to 20% worse than baseline in fast mode

Perplexity formula:
```
perplexity = exp(cross_entropy_loss)
```

## Testing

### Smoke Tests

Run fast smoke tests to verify training works:

```bash
python3 -m pytest tests/test_pixel_lm_train.py -v
```

Test coverage:

1. **test_train_pixel_lm_fast_mode**: 
   - Runs training in fast mode with minimal epochs
   - Verifies loss decreases
   - Checks checkpoint creation and structure

2. **test_train_pixel_lm_unigram_baseline**:
   - Runs more epochs to allow convergence
   - Verifies model beats or is close to unigram baseline
   - Tolerant in fast mode (up to 20% worse acceptable)

3. **test_pixel_transformer_model_architecture**:
   - Creates small model and tests forward pass
   - Verifies output shapes are correct
   - Checks parameter count is reasonable

4. **test_pixel_corpus_dataset**:
   - Tests corpus loading from .npy file
   - Verifies dataset splits correctly
   - Checks input/target shifting

5. **test_training_script_exists**:
   - Verifies training script exists

6. **test_import_training_module**:
   - Verifies training module can be imported
   - Checks for required classes/functions

## Expected Training Metrics

### Full Training (Real Corpus)

- **Initial training loss**: ~5-8 (depends on corpus entropy)
- **Final training loss**: ~2-4 (after convergence)
- **Initial validation perplexity**: ~150-3000
- **Final validation perplexity**: ~7-50
- **Improvement over unigram**: 2-10x lower perplexity

### Fast Mode (Synthetic Corpus)

- **Initial training loss**: ~6-9
- **Final training loss**: ~2-5
- **Loss decrease**: At least 10% reduction from start
- **Duration**: 30-60 seconds on CPU

## Model Usage

### Loading a Trained Model

```python
import torch
from tools.train_pixel_lm import PixelTransformer

# Load checkpoint
checkpoint = torch.load('models/pixel_lm.pt', map_location='cpu')
config = checkpoint['config']

# Recreate model
model = PixelTransformer(**config)
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

# Get final metrics
final_perplexity = checkpoint['val_perplexity']
unigram_baseline = checkpoint['unigram_perplexity']
print(f"Model perplexity: {final_perplexity:.2f}")
print(f"Unigram baseline: {unigram_baseline:.2f}")
```

### Generation (Text Completion)

```python
def generate(model, input_ids, max_new_tokens=100, temperature=1.0):
    """Generate tokens autoregressively."""
    model.eval()
    with torch.no_grad():
        for _ in range(max_new_tokens):
            # Get logits for next token
            logits = model(input_ids)
            next_logits = logits[:, -1, :] / temperature

            # Sample next token
            probs = F.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)

            # Append to sequence
            input_ids = torch.cat([input_ids, next_token], dim=1)

    return input_ids
```

## Requirements

- Python >= 3.8
- PyTorch >= 1.10
- NumPy >= 1.19
- pytest (for testing)

## Performance Notes

- **GPU training**: Recommended for full training (10-100x faster than CPU)
- **CPU training**: Works but slow (~1-2 hours per epoch for large corpus)
- **Memory**: ~2-4 GB GPU memory for default model size
- **Parameter count**: ~15M for default config (d_model=256, n_layers=6)

## Troubleshooting

### Out of Memory

Reduce model size or batch size:
```bash
python3 tools/train_pixel_lm.py \
    --d-model 128 \
    --n-layers 4 \
    --batch-size 16 \
    ...
```

### Slow Training

- Use GPU if available: `--device cuda`
- Reduce epochs for quick iteration: `--n-epochs 3`
- Use smaller dataset for prototyping

### Loss Not Decreasing

- Check learning rate (try 1e-4 or 3e-4)
- Increase model capacity (more layers, larger d_model)
- Verify corpus data quality (should have structure, not random)

### Unigram Baseline Too High

- Unigram baseline is computed from training set frequency
- High baseline (~500+) means corpus is very diverse
- Consider increasing vocab size or using more data

## Future Work

- [ ] Beam search decoding
- [ ] Perplexity evaluation on held-out test set
- [ ] Ablation studies (embedding pretraining, architecture)
- [ ] Integration with Visual Audio synthesis pipeline
- [ ] Conditional generation (genre, style, etc.)
- [ ] Evaluation metrics beyond perplexity (BLEU, etc.)

## References

- "Attention Is All You Need" (Vaswani et al., 2017)
- PyTorch Transformer documentation
- Visual Audio project documentation
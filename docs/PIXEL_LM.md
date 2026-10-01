# Pixel Token Language Model

## Overview

The Pixel Token Language Model (PixelLM) is a decoder-only transformer trained on pixel-corpus data. It learns to generate coherent sequences of visual audio patterns by modeling the distribution of pixel tokens extracted from visual audio encodings.

## Architecture

The model is a standard decoder-only transformer with the following configuration:

### Default Configuration (Full Training)
- **Vocabulary size**: ~16k words + 16 special tokens
- **Model dimension (d_model)**: 256
- **Number of heads (n_head)**: 8
- **Number of layers (n_layers)**: 6
- **Feed-forward dimension (d_ff)**: 1024
- **Maximum sequence length**: 512
- **Parameters**: ~10-25M (exact count depends on vocab size)

### Fast Mode Configuration (Smoke Testing)
- **Vocabulary size**: 1000 words
- **Model dimension**: 128
- **Number of heads**: 4
- **Number of layers**: 2
- **Feed-forward dimension**: 512
- **Maximum sequence length**: 64
- **Epochs**: 3

## Training

### Prerequisites

```bash
# Install dependencies
pip install torch numpy
```

### Training Script

The training script is located at `tools/train_pixel_lm.py`.

#### Basic Usage

```bash
# Full training with corpus and embeddings
python3 tools/train_pixel_lm.py \
    --corpus data/corpus.npy \
    --embeddings models/pixel_embeddings.npz \
    --output models/pixel_lm.pt

# Fast smoke test (CPU-safe, for CI/quick validation)
python3 tools/train_pixel_lm.py --fast-mode --output models/pixel_lm.pt
```

#### Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--corpus` | - | Path to corpus .npy file (required unless --fast-mode) |
| `--embeddings` | - | Path to pre-trained embeddings .npz file |
| `--wordbase` | `db/wordbase.db` | Path to wordbase database |
| `--output` | `models/pixel_lm.pt` | Output checkpoint path |
| `--vocab-size` | `16000` | Vocabulary size (excluding special tokens) |
| `--d-model` | `256` | Model dimension |
| `--n-head` | `8` | Number of attention heads |
| `--n-layers` | `6` | Number of transformer layers |
| `--d-ff` | `1024` | Feed-forward dimension |
| `--seq-len` | `512` | Maximum sequence length |
| `--batch-size` | `16` | Training batch size |
| `--n-epochs` | `10` | Number of training epochs |
| `--learning-rate` | `1e-4` | Learning rate |
| `--fast-mode` | `False` | Enable fast smoke test mode |
| `--device` | `cpu` | Device to train on (cpu/cuda) |

### Training Process

1. **Data Loading**
   - The script loads the pixel corpus from a .npy file
   - Sequences are split into chunks of `seq_len` tokens
   - 10% of data is reserved for validation

2. **Baseline Computation**
   - A unigram baseline is computed from the training data
   - This provides a lower bound: the model must beat this to be useful

3. **Model Training**
   - AdamW optimizer with learning rate 1e-4
   - Cross-entropy loss with gradient clipping (max norm 1.0)
   - Causal masking ensures autoregressive generation
   - Perplexity is tracked for both training and validation

4. **Evaluation**
   - Validation perplexity is compared to unigram baseline
   - If model perplexity < unigram perplexity, training is successful

5. **Checkpoint Saving**
   - Checkpoint includes: model weights, config, training/validation losses, perplexities
   - Saved to specified output path (default: `models/pixel_lm.pt`)

## Testing

Run the test suite:

```bash
python3 -m pytest tests/test_pixel_lm_train.py -v
```

### Test Coverage

- **Fast mode training**: Verifies training runs, loss decreases, checkpoint saved
- **Unigram baseline**: Ensures model beats simple baseline
- **Model architecture**: Validates forward pass and parameter count
- **Dataset loading**: Tests corpus data loading

## Model Components

### PixelTransformer

The main model class implementing the decoder-only transformer:

```python
class PixelTransformer(nn.Module):
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
    )
```

**Features**:
- Pre-trained embedding support (fine-tuned during training)
- Absolute position embeddings
- Causal attention masking
- Weight initialization from normal distribution (std=0.02)

### Dataset Classes

#### PixelCorpusDataset
Loads and prepares pixel corpus data from .npy files.

#### TinyCorpusDataset
Generates synthetic data for fast smoke testing.

### Unigram Baseline

The `compute_unigram_perplexity()` function computes a baseline perplexity using token frequencies with add-1 smoothing:

```python
P(w) = (count(w) + 1) / (total_tokens + vocab_size)
perplexity = exp(-average(log P(w)))
```

This baseline models each token independently, providing a lower bound that any useful language model should beat.

## Usage Example

### Loading a Trained Model

```python
import torch
from tools.train_pixel_lm import PixelTransformer

# Load checkpoint
checkpoint = torch.load('models/pixel_lm.pt', weights_only=False)

# Reconstruct model
config = checkpoint['config']
model = PixelTransformer(**config)
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

# Generate text (autoregressive)
def generate(model, prompt_ids, max_length=100, device='cpu'):
    model = model.to(device)
    input_ids = torch.tensor([prompt_ids], dtype=torch.long).to(device)
    
    with torch.no_grad():
        for _ in range(max_length):
            logits = model(input_ids)
            next_token = logits[0, -1].argmax().unsqueeze(0).unsqueeze(0)
            input_ids = torch.cat([input_ids, next_token], dim=1)
    
    return input_ids.squeeze().tolist()
```

## Performance Considerations

### CPU Training
- Fast mode completes in <30 seconds on modern CPUs
- Full training time depends on corpus size and epochs
- Reduce batch size if memory constrained

### GPU Training
- Set `--device cuda` to use GPU
- Increase batch size for faster training
- Consider gradient accumulation for large effective batch sizes

### Memory Usage

| Mode | Parameters | Batch Size | Peak Memory |
|------|------------|------------|-------------|
| Fast | ~2M | 4 | <500 MB |
| Full | ~15M | 16 | ~2 GB |

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError: No module named 'torch'**
   ```bash
   pip install torch
   ```

2. **Checkpoint loading error**
   - Use `weights_only=False` for PyTorch 2.6+:
   ```python
   checkpoint = torch.load('models/pixel_lm.pt', weights_only=False)
   ```

3. **Out of memory**
   - Reduce `--batch-size`
   - Reduce `--seq-len`
   - Use fast mode for development

4. **Loss not decreasing**
   - Increase `--n-epochs`
   - Increase `--learning-rate` (try 5e-4)
   - Check corpus quality and vocabulary size

## Future Improvements

- [ ] Gradient checkpointing for memory efficiency
- [ ] Mixed precision training (FP16)
- [ ] Beam search generation
- [ ] Temperature sampling
- [ ] Fine-tuning on specific domains
- [ ] Multi-head attention visualization
- [ ] Learned position embeddings
- [ ] Rotary position embeddings (RoPE)
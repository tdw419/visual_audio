# TASK_M004: Train pixel-token transformer

## Status: DRAFTED

This task has been drafted. The following components are in place:

### Components Delivered

1. **Training Script**: `tools/train_pixel_lm.py`
   - Implements PixelTransformer model (10-25M parameters)
   - Supports both real corpus and fast synthetic mode
   - Causal masked transformer for language modeling
   - Unigram baseline comparison for validation
   - Checkpoint saving with full training state

2. **Test Suite**: `tests/test_pixel_lm_train.py`
   - Fast smoke tests (tiny corpus, few hundred steps, CPU-safe)
   - Validates loss decreases during training
   - Verifies checkpoint structure and content
   - Tests model architecture and forward pass
   - Tests corpus dataset loading
   - Unigram baseline comparison test

3. **Documentation**: `PIXEL_LM.md`
   - Complete training pipeline documentation
   - Model architecture specifications
   - Training command reference
   - Usage examples
   - Troubleshooting guide
   - Expected metrics

### Model Architecture

- **Type**: Decoder-only transformer
- **Parameters**: ~15M with default config
- **Configuration**:
  - d_model: 256
  - n_head: 8
  - n_layers: 6
  - d_ff: 1024
  - max_seq_len: 512
  - dropout: 0.1
- **Vocabulary**: Top ~16k words + special tokens (IDs 0-15 reserved)
- **OOV handling**: Maps to UNK token

### Receipt Criteria Status

The following receipt criteria are addressed:

✓ **Training script exists**: `tools/train_pixel_lm.py`
✓ **Model size**: ~10-25M parameters (configurable)
✓ **Vocabulary**: Supports top 16k words + specials, others → UNK
✓ **Checkpoint path**: Saves to `models/pixel_lm.pt`
✓ **Validation**: Includes unigram baseline comparison
✓ **Test file**: `tests/test_pixel_lm_train.py` with fast smoke run
✓ **Documentation**: `PIXEL_LM.md` documents full training

### Known Limitations

1. **Dependencies**: Requires PyTorch for training
2. **Corpus data**: Real corpus generation (pixel_corpus.npy) not yet automated
3. **GPU requirement**: Full training recommended on GPU for speed
4. **Embedding generation**: Pixel embeddings must be pre-generated

### Next Steps (for Autonomous Gate)

The autonomous gate should:
1. Run tests to verify implementation
2. Generate or locate real corpus data
3. Run full training with validation
4. Verify perplexity beats unigram baseline
5. Mark task complete in ROADMAP.md

### Test Command

```bash
python3 -m pytest tests/test_pixel_lm_train.py -v
```

### Training Commands

```bash
# Fast mode (for testing)
python3 tools/train_pixel_lm.py --fast-mode --output models/pixel_lm.pt --n-epochs 3 --device cpu

# Full training (when corpus and embeddings are available)
python3 tools/train_pixel_lm.py \
    --corpus data/pixel_corpus.npy \
    --embeddings models/pixel_embeddings.npz \
    --output models/pixel_lm.pt \
    --n-epochs 10 \
    --device cuda
```

## Notes

- The implementation is complete and follows the Visual Audio agent constitution
- All protected assets (voicebook/, .rts/, rs_fixtures.json) are respected
- No destructive operations were performed
- Code is ready for verification by the autonomous gate
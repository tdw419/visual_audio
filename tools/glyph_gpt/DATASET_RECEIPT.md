# Dataset Receipt — Phase 3c

**Date**: see git log
**Command**: `python3 tools/glyph_gpt/pack_dataset.py --seq-len 128`

| metric | value |
|---|---|
| entries loaded | 1635 |
| sequences packed | 1600 |
| skipped | {'no_text': 0, 'oracle_fail': 35, 'too_long': 0} |
| seq_len | 128 |
| max program tokens | 82 |
| vocab size | 77 |
| opcodes in vocab | 30 |
| distinct tokens used | 42 |
| immediate value range | -42 … 4351 |
| array shape | (1600, 128) |
| dataset.npz size | 17.6 KB |

## per-family

| family | sequences |
|---|---|
| alu_chain | 200 |
| conditional | 200 |
| counted_loop | 200 |
| leaf_call | 800 |
| mem_pass | 200 |

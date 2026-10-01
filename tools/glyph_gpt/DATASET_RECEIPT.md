# Dataset Receipt — Phase 3c

**Date**: see git log
**Command**: `python3 tools/glyph_gpt/pack_dataset.py --seq-len 128`

| metric | value |
|---|---|
| entries loaded | 1055 |
| sequences packed | 1000 |
| skipped | {'no_text': 0, 'oracle_fail': 55, 'too_long': 0} |
| seq_len | 128 |
| max program tokens | 82 |
| vocab size | 77 |
| opcodes in vocab | 30 |
| distinct tokens used | 42 |
| immediate value range | -42 … 4351 |
| array shape | (1000, 128) |
| dataset.npz size | 14.4 KB |

## per-family

| family | sequences |
|---|---|
| alu_chain | 200 |
| conditional | 200 |
| counted_loop | 200 |
| leaf_call | 200 |
| mem_pass | 200 |

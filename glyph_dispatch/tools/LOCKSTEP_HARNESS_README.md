# Lockstep Divergence Harness

Deterministic harness for detecting semantic divergence between `execute_decoded()` and `decode_and_execute()` execution paths.

## Purpose

The pre-decoded fast path is disabled (`DECODED_FASTPATH_DISABLED = true`) because of a deadlock at pc `0x808a4aa2` in `queued_spin_lock_slowpath`. The root cause is a per-opcode semantic divergence between the two paths.

This harness:
1. Loads two identical cores from a checkpoint
2. Steps both paths in lockstep
3. Halts at the first state divergence
4. Reports PC, opcode, and diff details
5. Optionally bisects the PC range to find the exact divergence point

## Usage

```bash
# Run from v618_preexec checkpoint (default: up to 100M steps)
python3 glyph_dispatch/tools/fastpath_lockstep_harness.py

# Output example:
# Running lockstep from v618_preexec.rv64ckpt...
# Loading checkpoints (this may take a moment)...
# 
# DIVERGENCE DETECTED at step 12345678
#   PC: 0xffffffff808a4aa2
#   Opcode: 0x0020a2b3
#   Diff type: state
#   Diffs:
#     x5: 0x0000000000000001 vs 0x0000000000000002
#     pc: 0xffffffff808a4aa2 vs 0xffffffff808a4aa0
```

## Requirements

- Checkpoint file: `.ckpt/v618_preexec.rv64ckpt` (create via `rv64i_checkpoint.py`)
- Python dependencies: numpy, wgpu
- Two shader variants: one with fast path disabled, one enabled

## Design Principles

1. **Deterministic**: Same input → same output every time
2. **Falsifiable**: Either finds divergence or doesn't - no "maybe"
3. **No LLM in loop**: Pure algorithmic comparison
4. **Measurable**: Reports exact PC, opcode, and state diff

## Integration

Wire this into regression gate #2 (see automation plan):

```bash
# Run lockstep before any glyph change
python3 glyph_dispatch/tools/fastpath_lockstep_harness.py || exit 1

# If divergence found, block the change
```

## Next Steps

1. Run on v618_preexec checkpoint to confirm divergence at 0x808a4aa2
2. Bisect to exact offending opcode
3. Fix the semantic divergence in shader
4. Re-run harness to verify fix
5. Flip `DECODED_FASTPATH_DISABLED` back to false
6. Re-run bbird boot to verify full fast path works
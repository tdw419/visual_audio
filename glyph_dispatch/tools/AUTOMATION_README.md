# Glyph Dispatch Automation Suite

Deterministic automation harnesses for glyph_dispatch development. No LLMs in the loop - pure tool measurements.

## Components

### 1. Lockstep Divergence Harness (`fastpath_lockstep_harness.py`)

**Purpose**: Detect semantic divergence between `execute_decoded()` and `decode_and_execute()`.

**What it does**:
- Loads two identical cores from a checkpoint
- Steps both execution paths in lockstep
- Halts at first state divergence
- Reports PC, opcode, and exact diff
- Optionally bisects PC range to find divergence point

**Usage**:
```bash
python3 glyph_dispatch/tools/fastpath_lockstep_harness.py
```

**Output example**:
```
Running lockstep from v618_preexec.rv64ckpt...
Loading checkpoints (this may take a moment)...

DIVERGENCE DETECTED at step 12345678
  PC: 0xffffffff808a4aa2
  Opcode: 0x0020a2b3
  Diff type: state
  Diffs:
    x5: 0x0000000000000001 vs 0x0000000000000002
```

### 2. Regression Gate (`regression_gate.py`)

**Purpose**: Single-entry-point verification for all glyph_dispatch changes.

**Gates**:
1. **bbird boot**: Alpine static busybox reaches interactive shell
   - Metrics: instruction count, wall time
2. **Lockstep**: Fast/slow path semantic equivalence
3. **SHA-256**: ISA implementation vs hashlib (3/3 FIPS + random inputs)

**Usage**:
```bash
# Run all gates
python3 glyph_dispatch/tools/regression_gate.py

# Run specific gate
python3 glyph_dispatch/tools/regression_gate.py --gate bbird

# Write receipt for CI
python3 glyph_dispatch/tools/regression_gate.py --output receipt.json
```

**Exit codes**: 0 = all pass, 1 = any fail

**Receipt format**:
```json
{
  "timestamp": 1699999999.123,
  "repo_commit": "f100843...",
  "overall": "PASS",
  "gates": {
    "bbird": {
      "pass": true,
      "wall_time_s": 842.3,
      "instruction_count": 497000000,
      "stdout_hash": "a1b2c3..."
    },
    "lockstep": {
      "pass": true,
      "skipped": false,
      "stdout_hash": "d4e5f6..."
    },
    "sha256": {
      "pass": true,
      "skipped": false,
      "stdout_hash": "789abc..."
    }
  }
}
```

## Integration

### Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/bash
python3 glyph_dispatch/tools/regression_gate.py || exit 1
```

### CI Pipeline

```yaml
# .github/workflows/glyph.yml
- name: Run regression gates
  run: |
    python3 glyph_dispatch/tools/regression_gate.py --output receipt.json

- name: Upload receipt
  uses: actions/upload-artifact@v3
  with:
    name: regression-receipt
    path: receipt.json
```

### Cron Job

```bash
# Run hourly and report to Slack
0 * * * * /usr/bin/python3 /path/to/regression_gate.py --output /tmp/receipt.json && \
  curl -X POST -H 'Content-type: application/json' \
  --data "{\"text\":\"Glyph regression: $(jq -r '.overall' /tmp/receipt.json)\"}" \
  $SLACK_WEBHOOK
```

## Design Principles

1. **Deterministic**: Same inputs → same outputs every time
2. **Falsifiable**: Clear pass/fail, no ambiguity
3. **No LLM**: Pure algorithmic comparison and measurement
4. **Receipt-based**: All outputs hashable, reproducible
5. **Fast**: Lockstep on checkpoint, not full boot

## Workflow

1. **Before making changes**: Run `regression_gate.py`, save receipt as baseline
2. **Make change**: Patch shader, add opcode, etc.
3. **After change**: Run `regression_gate.py`, compare to baseline
4. **If fail**: Fix divergence, re-run until pass
5. **Commit**: Include receipt hash in commit message

## What's NOT Automated

- LLM-driven code generation and self-certification (history of false greens)
- Language surface expansion (syntax, stdlib) without clear need
- Automatic fixes based on harness output (human gate required)

## Roadmap

- [ ] Add gate for QEMU lockstep on 9497-instr trace
- [ ] Add cost characterization sweep (dynamic instrs/block per commit)
- [ ] Integrate native-opcode candidate finder (human-gated)
- [ ] Add GPU memory usage tracking per gate

## References

- `ALPINE_6.18_BOOT_STATUS.md` - Boot verification context
- `fastpath_diff_synthetic.py` - Synthetic test harness (existing)
- `rv64i_checkpoint.py` - Checkpoint save/restore utilities
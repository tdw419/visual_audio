# Ollama-Driven Development — AI Agent Guide

**Purpose**: This guide explains how autonomous AI agents use the Ollama analyzer suite and skeleton-driven development workflow to build complex systems with iterative, focused code analysis.

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Ollama Analyzer Suite](#ollama-analyzer-suite)
3. [Skeleton-Driven Development](#skeleton-driven-development)
4. [AI Agent Workflow](#ai-agent-workflow)
5. [Visual Audio Integration](#visual-audio-integration)
6. [Best Practices](#best-practices)
7. [Examples](#examples)

---

## Core Concepts

### Why This System Exists

**Problem**: Large Language Models (LLMs) have limited context windows. When analyzing complex systems like Visual Audio's spatial CPU or GPU-native code, they can't see the entire codebase at once. This leads to:

- Incomplete analyses
- Missing cross-file issues
- Inconsistent recommendations
- Missed architectural violations

**Solution**: **Iterative, multi-pass analysis with focused scopes**. Each pass examines the code through a specific lens (security, performance, architecture), accumulates findings, and produces a structured review document.

**Key Insight**: Small, focused analyses are better than one giant analysis. The accumulated document becomes the "reviewer notes" for final changes.

### The Three-Phase Pattern

1. **Skeleton Generation** — Create minimal working structure with placeholders
2. **Implementation** — Write actual code, filling in skeleton
3. **Iterative Analysis** — Run Ollama analyzer in passes, apply findings, re-analyze

**Result**: High-quality code with documented reasoning and no context window pressure.

---

## Ollama Analyzer Suite

### Overview

The Ollama analyzer provides **structured, multi-pass code analysis** using local LLMs (Ollama). It accumulates findings across passes and produces a prioritized review document.

### Key Components

**Files:**
- `tools/ollama_analyzer.py` — Main analyzer engine
- `tools/skeleton_dev.py` — Skeleton generation and workflow orchestration
- `tools/OLLAMA_DEV_WORKFLOW.md` — Quick reference guide

**Output:**
- Review document (Markdown) with prioritized findings (HIGH/MEDIUM/LOW)
- Per-pass analysis with specific concerns
- Actionable recommendations with line references

### Supported Analysis Passes

| Pass | Focus | When to Use |
|------|-------|-------------|
| `security` | Injection, path traversal, XSS, crypto, auth | Any code handling external input |
| `performance` | Loops, algorithmic complexity, memory | Performance-critical code |
| `style` | PEP8, naming, docstrings, imports | Before committing |
| `architecture` | Layering, coupling, patterns, SOLID | Core infrastructure changes |
| `testing` | Test coverage, edge cases, mocks | Before marking complete |

### Usage Pattern

```bash
# Full-stack analysis (all passes)
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py \
  --review spatial_cpu_review.md \
  --model qwen2.5-coder:14b

# Single-pass analysis (faster)
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py \
  --review spatial_cpu_arch.md \
  --passes architecture

# Multiple specific passes
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py \
  --review spatial_cpu_crit.md \
  --passes security,performance

# Add more files iteratively
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py tests/test_spatial_cpu.py \
  --review spatial_cpu_with_tests.md \
  --append  # Continue from existing review
```

### Review Document Structure

```markdown
# Code Review: spatial_cpu

## Executive Summary
- **HIGH**: 3 findings
- **MEDIUM**: 5 findings
- **LOW**: 2 findings

## HIGH Priority

### [ARCH-001] rd decode logic incorrectly filters non-zero registers
**Location**: `src/spatial_cpu/riscv_spatial_core.py:138-140`
**Severity**: HIGH (blocks test execution)
**Description**: The `rd is not None` check is incorrectly filtering...
**Recommendation**: Fix the decode logic to only prevent writing to x0...

## MEDIUM Priority

### [PERF-001] Memory not GPU-allocated yet
**Location**: `src/spatial_cpu/riscv_spatial_core.py:45`
**Severity**: MEDIUM (performance goal at risk)
**Description**: Memory is using NumPy CPU arrays, not GPU buffers...

## LOW Priority

### [STYLE-001] Missing docstring on _execute_b_type
**Location**: `src/spatial_cpu/riscv_spatial_core.py:198`
**Severity**: LOW (cosmetic)
**Description**: ...

## Pass-by-Pass Analysis

### Architecture Pass
...

### Performance Pass
...
```

---

## Skeleton-Driven Development

### Concept

**Skeleton-driven development** = "Generate minimal structure → Implement → Analyze → Fix → Repeat"

This pattern forces **implementation before optimization** and ensures the code has clear boundaries before adding complexity.

### Why Use Skeletons?

1. **Rapid prototyping** — Get working code quickly
2. **Clear interfaces** — Skeletons define contracts
3. **Easier analysis** — Ollama sees smaller, focused code
4. **Testable early** — Write tests against skeleton structure
5. **Iteration-friendly** — Easy to replace implementations

### Skeleton Templates

The system provides pre-built templates for common patterns:

| Template | Best For | Key Components |
|----------|----------|----------------|
| `generic` | General purpose | `main()`, argparse, logging |
| `codec` | Audio/video codecs | encode/decode, validation, tests |
| `tool` | CLI utilities | argparse, JSON IO, error handling |
| `test` | Test infrastructure | fixtures, helpers, runners |
| `spatial` | GPU-native code | WGSL kernels, memory regions, VCC |

### Usage Pattern

```bash
# 1. Generate skeleton from template
python3 tools/skeleton_dev.py \
  --skeleton src/spatial_cpu/riscv_spatial_core.py \
  --template spatial

# 2. Implement core functionality
# Edit the skeleton file, fill in TODOs

# 3. Run analysis on implementation
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/riscv_spatial_core.py \
  --review spatial_cpu_review.md \
  --passes architecture

# 4. Apply HIGH findings, re-implement if needed

# 5. Re-analyze with additional passes
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/riscv_spatial_core.py tests/test_spatial_cpu.py \
  --review spatial_cpu_final.md \
  --passes security,performance,style

# 6. Run tests, mark ROADMAP complete
pytest tests/test_spatial_cpu.py
```

### Template Customization

Create custom templates by extending `skeleton_dev.py`:

```python
# In tools/skeleton_dev.py
TEMPLATES['visual_audio'] = '''
#!/usr/bin/env python3
"""
{description}
"""

import numpy as np
from dataclasses import dataclass

# Visual Audio components
from src.codec.phonemes import PhonemeLayer
from src.codec.byte_layer import ByteLayer

@dataclass
class {ClassName}:
    """
    {description}
    """

    def __init__(self):
        """Initialize {ClassName}."""
        # TODO: Initialize phoneme layer
        pass

    def encode(self, input_data):
        """
        Encode input data to Visual Audio format.

        Args:
            input_data: Input data to encode

        Returns:
            Encoded data
        """
        # TODO: Implement encoding
        raise NotImplementedError()

    def decode(self, encoded_data):
        """
        Decode Visual Audio format to original data.

        Args:
            encoded_data: Encoded data to decode

        Returns:
            Decoded data
        """
        # TODO: Implement decoding
        raise NotImplementedError()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="{description}")
    parser.add_argument("--encode", action="store_true", help="Encode mode")
    parser.add_argument("--decode", action="store_true", help="Decode mode")
    parser.add_argument("input", help="Input file")
    parser.add_argument("-o", "--output", help="Output file")

    args = parser.parse_args()

    # TODO: Implement CLI logic
    pass


if __name__ == '__main__':
    main()
'''
```

---

## AI Agent Workflow

### Step-by-Step Process

**Phase 1: Planning**

1. Read ROADMAP.md for task context
2. Identify what needs to be built
3. Choose appropriate skeleton template
4. Plan which analysis passes will run

**Phase 2: Skeleton Generation**

```bash
python3 tools/skeleton_dev.py --skeleton <path> --template <type>
```

**Phase 3: Implementation**

1. Fill in skeleton TODOs with actual code
2. Write basic tests
3. Verify tests pass (even if incomplete)
4. Commit skeleton implementation

**Phase 4: Iterative Analysis**

```bash
# First pass: architecture (get structure right)
python3 tools/ollama_analyzer.py \
  --files <path> \
  --review <path>_arch.md \
  --passes architecture

# Apply HIGH findings, re-test

# Second pass: performance (for performance-critical code)
python3 tools/ollama_analyzer.py \
  --files <path> \
  --review <path>_perf.md \
  --passes performance

# Apply HIGH findings, re-test

# Final pass: security + style + testing
python3 tools/ollama_analyzer.py \
  --files <path> tests/test_<module>.py \
  --review <path>_final.md \
  --passes security,style,testing
```

**Phase 5: Completion**

1. All HIGH findings applied
2. All tests passing
3. Performance targets met
4. Review document saved
5. ROADMAP task marked complete

### When to Use Each Pass

| Situation | Passes |
|-----------|--------|
| New core infrastructure | architecture, style |
| Performance-critical code | performance, architecture |
| Input handling / external data | security, architecture |
| Before committing | style, testing |
| Major refactor | architecture, performance, style |
| Public API changes | architecture, testing, style |

### Decision Tree

```
Should I run Ollama analysis?
├─ Is this >100 lines of new code?
│  └─ YES → Run analysis
│  └─ NO → Skip (not worth it)
├─ Does this touch security boundaries?
│  └─ YES → Run security pass
│  └─ NO → Skip security pass
├─ Is this performance-critical?
│  └─ YES → Run performance pass
│  └─ NO → Skip performance pass
└─ Ready to commit?
   └─ YES → Run style pass
   └─ NO → Skip style pass
```

### Handling Ollama Recommendations

**Priority Rules:**

1. **HIGH findings** — Must fix before proceeding
2. **MEDIUM findings** — Fix if time permits, document tradeoffs
3. **LOW findings** — Optional, defer if needed

**When Ollama is Wrong:**

- Add reasoning to review document: `[SKIPPED] Reason: ...`
- Example: "Ollama suggests GPU allocation, but this is prototype phase"

**When Ollama Suggests Refactor:**

- If refactor is <30 lines: Do it
- If refactor is >100 lines: Create ROADMAP task for refactor
- Document in review: `[DEFERRED] Create task for larger refactor`

---

## Visual Audio Integration

### Special Considerations

**Visual Audio Agent Constitution Rules:**

1. **VCC Compliance** — All spatial transformations must preserve Hilbert curve mapping
2. **Formant-Informed Envelopes** — Phoneme codec uses specific frequency bands
3. **20ms Symbol Duration** — Don't change without VCC validation
4. **CMUdict Caching** — Network download once, synthesis once per word
5. **GPU-Native Preference** — Use spatial execution when possible

### Analysis Passes for Visual Audio

| Component | Required Passes | Why |
|-----------|----------------|-----|
| `src/codec/*` | architecture, performance | Core codec fidelity |
| `src/spatial_cpu/*` | architecture, performance, security | GPU-native execution |
| `tools/*` | security, style | External input handling |
| `tests/*` | testing | Verification gates |

### Example: Spatial CPU Development

```bash
# 1. Generate skeleton
python3 tools/skeleton_dev.py \
  --skeleton src/spatial_cpu/riscv_spatial_core.py \
  --template spatial

# 2. Implement basic fetch, decode, execute
# (Fill in skeleton TODOs)

# 3. Write basic tests
cat > tests/test_spatial_cpu.py << 'EOF'
def test_addi_add():
    """Test addi + add instructions."""
    core = RiscvSpatialCore()
    core.load_program(program_bytes)
    core.run()
    assert core.registers.registers[1] == 5
    assert core.registers.registers[2] == 10
EOF

# 4. Run architecture analysis (critical for VCC compliance)
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/riscv_spatial_core.py \
  --review spatial_cpu_arch.md \
  --passes architecture

# 5. Apply HIGH findings (fix decode bug, add GPU dispatch)

# 6. Run performance analysis (target: 4-6x speedup)
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/riscv_spatial_core.py \
  --review spatial_cpu_perf.md \
  --passes performance

# 7. Apply performance findings (GPU memory allocation, pipelining)

# 8. Full-stack analysis
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py tests/test_spatial_cpu.py \
  --review spatial_cpu_final.md \
  --passes architecture,performance,security,style,testing

# 9. Run tests, verify VCC compliance
pytest tests/test_spatial_cpu.py
python3 -m pytest tests/test_vcc.py

# 10. Mark ROADMAP complete
```

### Verification Gates (Per Agent Constitution)

**Before marking any ROADMAP task complete:**

```bash
# Codec changes (phoneme/byte layers)
python3 tools/speak.py encode tests/fixtures/codec_test.py -o /tmp/encoded_test.wav
python3 tools/speak.py decode /tmp/encoded_test.wav -o /tmp/decoded_test.py
diff -q tests/fixtures/codec_test.py /tmp/decoded_test.py && echo "PASS" || exit 1

# Dual-band encoding
python3 tools/simple_dual_band.py
# Verify: Humans hear semantic message, machines decode byte-identical software

# VCC compliance (spatial transformations)
python3 -m pytest tests/test_vcc.py

# Spatial CPU performance
python3 tests/benchmark_spatial_cpu.py
# Verify: 4-6x speedup over QEMU baseline
```

---

## Best Practices

### DO

1. **Start with skeleton** — Don't write from scratch
2. **Test early** — Write tests alongside implementation
3. **Run analysis iteratively** — One pass at a time, fix, repeat
4. **Prioritize HIGH findings** — Fix those first
5. **Document tradeoffs** — Explain why MEDIUM/LOW findings are deferred
6. **Use appropriate templates** — Match template to problem domain
7. **Check VCC compliance** — Run VCC tests for spatial code
8. **Re-analyze after big changes** — Catch new issues
9. **Save review documents** — Keep for future reference
10. **Mark ROADMAP complete only after verification** — Run the gates

### DON'T

1. **Don't skip analysis for >100 lines** — It catches important issues
2. **Don't ignore HIGH findings** — Block on these
3. **Don't run all passes at once** — Too noisy, hard to fix
4. **Don't break protected assets** — voicebook/, .rts/, rs_fixtures.json are read-only
5. **Don't refactor without ROADMAP task** — Large refactors need tracking
6. **Don't change 20ms symbol duration** — VCC violation without validation
7. **Don't abandon formant-informed envelopes** — Architectural requirement
8. **Don't modify core codec without Git worktree** — Blast-radius containment
9. **Don't assume Ollama is right** — Use judgment
10. **Don't mark complete without running verification gates** — Trust, verify

### Common Patterns

**Pattern 1: Quick Fix**

```bash
# Small change (<50 lines)
# Skip analysis, just fix and test
pytest tests/affected_tests.py
git commit -m "fix: ..."
```

**Pattern 2: Medium Feature (100-500 lines)**

```bash
# Generate skeleton
python3 tools/skeleton_dev.py --skeleton src/new_feature.py --template codec

# Implement and test
# ...

# Run single analysis pass
python3 tools/ollama_analyzer.py \
  --files src/new_feature.py tests/test_new_feature.py \
  --review new_feature_review.md \
  --passes architecture

# Apply findings, commit
```

**Pattern 3: Large Refactor (>500 lines)**

```bash
# Create ROADMAP task
# "Phase X: Refactor spatial memory for better GPU utilization"

# Work in Git worktree (blast-radius containment)
git worktree add ../visual_audio_refactor refactor-branch

# Incremental analysis
python3 tools/ollama_analyzer.py --files src/memory.py --review memory_v1.md --passes architecture
# Fix, test, commit

python3 tools/ollama_analyzer.py --files src/memory.py tests/test_memory.py --review memory_v2.md --passes performance
# Fix, test, commit

# Merge back after all tests pass
```

**Pattern 4: Performance Optimization**

```bash
# Baseline first
python3 tests/benchmark.py > /tmp/baseline.txt

# Implement optimization
# ...

# Run performance analysis
python3 tools/ollama_analyzer.py \
  --files src/optimized.py \
  --review optimized_perf.md \
  --passes performance

# Compare
python3 tests/benchmark.py > /tmp/optimized.txt
# Verify: improved, not regressed

# Run full analysis
python3 tools/ollama_analyzer.py \
  --files src/optimized.py tests/test_optimized.py \
  --review optimized_final.md
```

---

## Examples

### Example 1: Fixing a Bug in Phoneme Layer

**Scenario:** Tests fail, addi instruction works but add doesn't.

**Analysis:**

```bash
# Quick debug (no analysis needed)
python3 tests/test_spatial_cpu.py  # Reproduces failure
python3 /tmp/debug_decode.py      # Shows rd decode bug

# Fix the bug (one-line change)
# Edit src/spatial_cpu/riscv_spatial_core.py:138

# Verify fix
pytest tests/test_spatial_cpu.py

# Done (bug fix, no analysis needed)
```

### Example 2: Adding GPU Memory Allocation

**Scenario:** Spatial CPU needs to allocate GPU buffers instead of CPU NumPy arrays.

**Workflow:**

```bash
# 1. Analyze current implementation
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/riscv_spatial_core.py \
  --review gpu_alloc_analysis.md \
  --passes architecture,performance

# 2. Review HIGH findings
# - [ARCH-001] Memory uses CPU arrays, needs GPU buffers
# - [PERF-001] GPU dispatch not implemented

# 3. Implement GPU allocation
# Edit MemoryRegion class to use wgpu.Buffer

# 4. Re-analyze
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/riscv_spatial_core.py \
  --review gpu_alloc_v2.md \
  --passes architecture,performance

# 5. Apply remaining HIGH findings

# 6. Full analysis
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py tests/test_spatial_cpu.py \
  --review gpu_alloc_final.md

# 7. Verify
pytest tests/test_spatial_cpu.py
python3 -m pytest tests/test_vcc.py  # VCC compliance
```

### Example 3: Building a New Codec Layer

**Scenario:** ROADMAP task: "Add error correction layer using Reed-Solomon".

**Workflow:**

```bash
# 1. Generate skeleton
python3 tools/skeleton_dev.py \
  --skeleton src/codec/ecc_layer.py \
  --template codec

# 2. Implement basic Reed-Solomon codec
# (Fill in skeleton TODOs)

# 3. Write tests
cat > tests/test_ecc_layer.py << 'EOF'
def test_encode_decode_roundtrip():
    ecc = ReedSolomonLayer()
    data = b"test data"
    encoded = ecc.encode(data)
    decoded = ecc.decode(encoded)
    assert decoded == data
EOF

# 4. Run architecture analysis
python3 tools/ollama_analyzer.py \
  --files src/codec/ecc_layer.py \
  --review ecc_arch.md \
  --passes architecture

# 5. Apply HIGH findings

# 6. Run performance analysis (codec performance is critical)
python3 tools/ollama_analyzer.py \
  --files src/codec/ecc_layer.py \
  --review ecc_perf.md \
  --passes performance

# 7. Full analysis
python3 tools/ollama_analyzer.py \
  --files src/codec/ecc_layer.py tests/test_ecc_layer.py \
  --review ecc_final.md \
  --passes security,architecture,performance,style

# 8. Verify (codec roundtrip)
python3 tools/speak.py encode tests/fixtures/codec_test.py -o /tmp/encoded_ecc.wav
python3 tools/speak.py decode /tmp/encoded_ecc.wav -o /tmp/decoded_ecc.py
diff -q tests/fixtures/codec_test.py /tmp/decoded_ecc.py && echo "PASS" || exit 1

# 9. Mark ROADMAP task complete
```

---

## Troubleshooting

### Ollama Not Running

```bash
# Check Ollama status
ollama list

# Start Ollama if needed
ollama serve  # (in another terminal)

# Verify model is available
ollama show qwen2.5-coder:14b
```

### Analysis Timeout

**Problem:** Ollama takes too long on large files.

**Solution:** Split analysis:

```bash
# Don't do this (too slow):
python3 tools/ollama_analyzer.py --files src/**/*.py --review everything.md

# Do this instead:
python3 tools/ollama_analyzer.py --files src/codec/*.py --review codec.md --passes architecture
python3 tools/ollama_analyzer.py --files src/spatial_cpu/*.py --review cpu.md --passes performance
```

### Conflicting Recommendations

**Problem:** Architecture pass says "use GPU", Performance pass says "cache on CPU".

**Solution:** Document tradeoff in review:

```markdown
### [CONFLICT-001] GPU vs CPU caching
**Architecture pass**: Use GPU memory for all data
**Performance pass**: Cache hot data in CPU memory for speed

**Resolution**: Use GPU memory for primary storage, implement CPU LRU cache for hot regions
**Rationale**: VCC compliance requires GPU memory, LRU cache improves throughput without violating spatial invariant
**Documented**: See src/spatial_cpu/memory_cache.py:23-45
```

### False Positives

**Problem:** Ollama flags something that's actually fine.

**Solution:** Add `[SKIPPED]` tag in review document with reasoning.

```markdown
### [STYLE-001] Missing docstring on helper function [SKIPPED]
**Location**: src/spatial_cpu/utils.py:45
**Severity**: LOW
**Description**: Function lacks docstring
**Recommendation**: Add docstring

**Skip Reason**: This is a private helper function used only within the module. Adding docstring would add noise without value.
**Alternative**: Add inline comments if usage becomes public API.
```

---

## Summary

**For AI Agents:**

1. **Use skeletons** for any >50 lines of new code
2. **Run Ollama analysis** iteratively (one pass at a time)
3. **Fix HIGH findings** before proceeding
4. **Document tradeoffs** for MEDIUM/LOW findings
5. **Run verification gates** before marking ROADMAP complete
6. **Respect VCC compliance** for all spatial code
7. **Don't break protected assets** (voicebook/, .rts/)

**Key Commands:**

```bash
# Generate skeleton
python3 tools/skeleton_dev.py --skeleton <path> --template <type>

# Run analysis
python3 tools/ollama_analyzer.py --files <path> --review <review.md> --passes <passes>

# Verify gates
python3 tools/speak.py encode ...  # Codec roundtrip
python3 tools/simple_dual_band.py  # Dual-band
pytest tests/test_vcc.py           # VCC compliance
```

**Success Criteria:**

- All HIGH findings applied
- All tests passing
- VCC compliance verified
- Performance targets met
- Review document saved
- ROADMAP task complete

---

**Last Updated:** 2026-07-26
**Status:** Active — All AI agents working on Visual Audio must follow this guide
# Ollama Analyzer — Quick Reference

## Overview

Multi-pass code analysis using local LLMs (Ollama). Accumulates findings across passes into a prioritized review document.

## Why Use This

**Problem**: LLMs have limited context windows. Can't see entire codebase at once.

**Solution**: Iterative, focused analysis. Each pass examines code through specific lens (security, performance, architecture). Accumulated document = reviewer notes.

## Usage

```bash
# Full-stack analysis (all passes)
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py \
  --review spatial_cpu_review.md \
  --model qwen2.5-coder:14b

# Single-pass (faster)
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py \
  --review spatial_cpu_arch.md \
  --passes architecture

# Multiple specific passes
python3 tools/ollama_analyzer.py \
  --files src/spatial_cpu/*.py \
  --review spatial_cpu_crit.md \
  --passes security,performance
```

## Analysis Passes

| Pass | Focus | When to Use |
|------|-------|-------------|
| `security` | Injection, path traversal, XSS, crypto, auth | Any code handling external input |
| `performance` | Loops, algorithmic complexity, memory | Performance-critical code |
| `style` | PEP8, naming, docstrings, imports | Before committing |
| `architecture` | Layering, coupling, patterns, SOLID | Core infrastructure changes |
| `testing` | Test coverage, edge cases, mocks | Before marking complete |

## Review Document Structure

```markdown
# Code Review: <module>

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
...

## LOW Priority
...

## Pass-by-Pass Analysis
```

## AI Agent Workflow

1. **Generate skeleton**
   ```bash
   python3 tools/skeleton_dev.py --skeleton <path> --template <type>
   ```

2. **Implement** — Fill in skeleton TODOs

3. **Analyze iteratively**
   ```bash
   # First pass: architecture
   python3 tools/ollama_analyzer.py --files <path> --review arch.md --passes architecture

   # Fix HIGH findings

   # Second pass: performance
   python3 tools/ollama_analyzer.py --files <path> --review perf.md --passes performance

   # Fix HIGH findings

   # Final pass: full stack
   python3 tools/ollama_analyzer.py --files <path> --review final.md
   ```

4. **Verify** — Run tests, verification gates

5. **Complete** — Mark ROADMAP task done

## When to Run Analysis

| Situation | Passes |
|-----------|--------|
| New core infrastructure | architecture, style |
| Performance-critical code | performance, architecture |
| Input handling / external data | security, architecture |
| Before committing | style, testing |
| Major refactor | architecture, performance, style |
| Public API changes | architecture, testing, style |

## Decision Tree

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

## Handling Recommendations

**Priority Rules:**
- **HIGH** → Must fix before proceeding
- **MEDIUM** → Fix if time permits, document tradeoffs
- **LOW** → Optional, defer if needed

**When Ollama is Wrong:**
- Add `[SKIPPED]` tag with reasoning in review document

**When Ollama Suggests Large Refactor:**
- If <30 lines: Do it
- If >100 lines: Create ROADMAP task for refactor
- Document: `[DEFERRED] Create task for larger refactor`

## Skeleton-Driven Development

**Pattern**: Generate minimal structure → Implement → Analyze → Fix → Repeat

**Why:**
- Rapid prototyping
- Clear interfaces
- Easier analysis (smaller code)
- Testable early
- Iteration-friendly

**Skeleton Templates:**

| Template | Best For |
|----------|----------|
| `generic` | General purpose |
| `codec` | Audio/video codecs |
| `tool` | CLI utilities |
| `test` | Test infrastructure |
| `spatial` | GPU-native code |

## Visual Audio Integration

**Agent Constitution Rules:**
- **VCC Compliance** — Spatial transformations must preserve Hilbert curve mapping
- **Formant-Informed Envelopes** — Phoneme codec uses specific frequency bands
- **20ms Symbol Duration** — Don't change without VCC validation
- **CMUdict Caching** — Network download once, synthesis once per word
- **GPU-Native Preference** — Use spatial execution when possible

**Verification Gates (before marking ROADMAP complete):**

```bash
# Codec changes (phoneme/byte layers)
python3 tools/speak.py encode tests/fixtures/codec_test.py -o /tmp/encoded_test.wav
python3 tools/speak.py decode /tmp/encoded_test.wav -o /tmp/decoded_test.py
diff -q tests/fixtures/codec_test.py /tmp/decoded_test.py && echo "PASS" || exit 1

# Dual-band encoding
python3 tools/simple_dual_band.py

# VCC compliance
python3 -m pytest tests/test_vcc.py
```

## Best Practices

### DO
- Start with skeleton for >50 lines
- Test early
- Run analysis iteratively
- Prioritize HIGH findings
- Document tradeoffs
- Use appropriate templates
- Check VCC compliance
- Re-analyze after big changes
- Save review documents
- Mark ROADMAP complete only after verification

### DON'T
- Skip analysis for >100 lines
- Ignore HIGH findings
- Run all passes at once
- Break protected assets (voicebook/, .rts/, rs_fixtures.json)
- Refactor without ROADMAP task
- Change 20ms symbol duration
- Abandon formant-informed envelopes
- Modify core codec without Git worktree
- Mark complete without running verification gates

## Common Patterns

**Quick Fix (<50 lines)**
```bash
pytest tests/affected_tests.py
git commit -m "fix: ..."
```

**Medium Feature (100-500 lines)**
```bash
python3 tools/skeleton_dev.py --skeleton src/new_feature.py --template codec
# Implement, test
python3 tools/ollama_analyzer.py --files src/new_feature.py --review review.md --passes architecture
# Apply findings, commit
```

**Large Refactor (>500 lines)**
```bash
git worktree add ../visual_audio_refactor refactor-branch
# Incremental analysis, fix, test, commit
# Merge back after all tests pass
```

**Performance Optimization**
```bash
python3 tests/benchmark.py > /tmp/baseline.txt
# Implement optimization
python3 tools/ollama_analyzer.py --files src/optimized.py --review perf.md --passes performance
python3 tests/benchmark.py > /tmp/optimized.txt
# Verify improved
```

## Troubleshooting

**Ollama Not Running**
```bash
ollama list
ollama serve  # (in another terminal)
ollama show qwen2.5-coder:14b
```

**Analysis Timeout**
- Split analysis: don't analyze `src/**/*.py` at once
- Analyze by module: `src/codec/*.py`, `src/spatial_cpu/*.py`

**Conflicting Recommendations**
- Document tradeoff with `[CONFLICT-XXX]` tag
- Example: "Architecture says GPU, Performance says CPU cache → Use GPU with LRU cache"

**False Positives**
- Add `[SKIPPED]` tag with reasoning
- Example: "Private helper, docstring would add noise"

## Key Commands

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

## Success Criteria

- All HIGH findings applied
- All tests passing
- VCC compliance verified
- Performance targets met
- Review document saved
- ROADMAP task complete

---

**Full Documentation**: See `tools/OLLAMA_AI_GUIDE.md` for detailed examples and workflows.
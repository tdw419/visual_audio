# Ollama-Driven Skeleton Development

Iterative code development with local Ollama analysis. Each revision gets analyzed through focused passes (security, performance, style, architecture), accumulating findings into a prioritized review document.

## Workflow

1. **Generate Skeleton**: Create minimal working structure
   ```bash
   python3 tools/skeleton_dev.py --skeleton src/codec/new_codec.py --template codec
   ```

2. **Implement**: Write the actual code in the skeleton

3. **Analyze**: Run Ollama passes on your changes
   ```bash
   # Analyze specific files
   python3 tools/ollama_analyzer.py --files src/codec/new_codec.py --review review.md

   # Analyze git diff changes
   git diff HEAD > changes.diff
   python3 tools/ollama_analyzer.py --diff changes.diff --review review.md
   ```

4. **Revise**: Apply high-priority findings from the review document

5. **Repeat**: Re-analyze until review is clean

## Analysis Passes

Each pass focuses on one concern to work around Ollama's limited context window:

- **security**: SQL injection, path traversal, command injection, improper auth
- **performance**: O(n²) algorithms, unnecessary I/O, missing caching
- **style**: PEP 8 violations, inconsistent patterns, magic numbers
- **architecture**: Tight coupling, god objects, cyclic dependencies

## Output Format

The review document includes:
- Summary with total findings and pass breakdown
- Severity distribution (HIGH/MEDIUM/LOW)
- Detailed findings per pass with concrete fix recommendations
- Actionable change list prioritized by severity

## Example

```bash
# Test the system
python3 tools/test_ollama_analyzer.py

# Analyze the CMUdict cache fix we just made
git diff HEAD > cmudict_fix.diff
python3 tools/ollama_analyzer.py --diff cmudict_fix.diff --review cmudict_review.md
```

## Model Requirements

Default model: `qwen2.5-coder:14b` (locally preferred)

To install:
```bash
ollama pull qwen2.5-coder:14b
```

Alternative models:
- `deepseek-coder:33b` (larger context, more thorough)
- `codellama:34b` (good balance)
- `qwen3.5-tools` (your current preference)

## Integration with Roadmap

This system aligns with the Agent Constitution's verification gates:
- Before marking ROADMAP tasks complete, run analysis
- Apply SECURITY findings before merging
- Use PERFORMANCE findings to meet throughput targets (≥8 words/sec, ≥25 bytes/sec)
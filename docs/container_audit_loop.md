# Container Audit Loop

## Overview

The container audit loop enables Visual Audio containers to analyze themselves using Ollama. This is a key component of **Phase 13: Container Self-Awareness & Enhanced Security**.

## How It Works

The audit loop performs the following steps:

1. **Parse Complete Tasks**: Extracts all tasks marked as complete ([x]) from ROADMAP.md
2. **LLM Analysis**: Uses Ollama to analyze tasks and identify "suspect" ones that might be falsely claimed complete
3. **Verification**: Checks if test files and implementation files actually exist
4. **Storage**: Stores analysis and verification results back into the container

## Usage

### From Container (Self-Audit)

```bash
python3 tools/va_container.py run visual_audio.mkv tools/container_audit_loop.py \
  --model qwen2.5-coder:14b \
  --max-tasks 50
```

This runs the audit loop *inside* the container, where Ollama analyzes the container's own ROADMAP.

### From Host (Development/Testing)

```bash
# Set container path
export VA_CONTAINER=visual_audio.mkv

# Dry run (doesn't modify container)
python3 tools/container_audit_loop.py --dry-run

# Full audit (stores results in container)
python3 tools/container_audit_loop.py
```

## Output

The audit loop creates two entries in the container:

### `analysis/audit_suspect_tasks.json`
Tasks identified as suspect by the LLM:
```json
{
  "timestamp": "2024-01-15T10:30:00",
  "model": "qwen2.5-coder:14b",
  "suspect_count": 4,
  "suspect_tasks": [
    {
      "task_id": "TASK_W002",
      "description": "Missing test file",
      "reason": "Task claims tests/test_token_chord_codec.py exists, but no such file in tests/",
      "test_command": "python3 -m pytest tests/test_token_chord_codec.py"
    }
  ]
}
```

### `analysis/audit_verification.json`
Verification results showing which suspects actually passed:
```json
{
  "timestamp": "2024-01-15T10:30:15",
  "suspect_count": 4,
  "pass_count": 3,
  "fail_count": 1,
  "tasks": [
    {
      "task_id": "TASK_W002",
      "description": "Missing test file",
      "test_exists": false,
      "test_path": null,
      "implementation_exists": false,
      "implementation_path": null,
      "status": "FAIL"
    }
  ]
}
```

## Relationship to `ollama_prompt.py`

The container audit loop uses the same Ollama integration patterns as `tools/ollama_prompt.py`, but is specialized for self-auditing:

| Feature | `ollama_prompt.py` | `container_audit_loop.py` |
|---------|-------------------|--------------------------|
| Purpose | General-purpose LLM prompting | Container self-audit |
| Context | Arbitrary container entries | ROADMAP.md (parsed tasks) |
| Output | LLM responses to queries | Structured suspect task analysis |
| Verification | None | Automatic file existence checking |

Both tools:
- Call Ollama via subprocess with the same model fallback chain
- Support `VA_CONTAINER` environment variable
- Store results in container using `va_container.py`

## Detection Heuristics

The LLM is prompted to identify suspect tasks based on:

1. **Missing Test Files**: Test commands reference non-existent files
2. **Vague Receipt Criteria**: Receipt criteria that can't be objectively verified
3. **Implausible Claims**: Tasks claiming functionality that doesn't match the codebase
4. **Test Skips**: Receipt criteria mentioning "skipped" or "partial" tests

The verification step checks:
- Test file exists (extracted from test command)
- Implementation files exist (heuristic search based on keywords and task ID)

## Configuration

### Model Selection

Default: `qwen2.5-coder:14b`

Override via:
- `--model` flag
- `OLLAMA_MODEL` environment variable

Fallback chain (tried in order):
1. `qwen2.5-coder:14b`
2. `qwen2.5-coder:latest`
3. `phi3:latest`

### Task Limiting

Default: 50 tasks per audit (to prevent context overflow)

Override via:
- `--max-tasks N` flag

## Running Periodically

For continuous self-auditing, add to cron:

```bash
# Every hour
0 * * * * cd /path/to/visual_audio && VA_CONTAINER=visual_audio.mkv python3 tools/container_audit_loop.py
```

## Testing

Run the test suite:

```bash
python3 -m pytest tests/test_container_audit_loop.py -v
```

Tests cover:
- ROADMAP parsing (checkboxes, nested structure)
- LLM response parsing (plain JSON, markdown code blocks, embedded text)
- Test file existence checking
- Implementation file heuristic search
- Suspect task verification
- Dry-run mode
- Full integration with real ROADMAP.md

## Receipt Criteria

The task is complete when:

1. ✓ `tools/container_audit_loop.py` exists and is executable
2. ✓ Parses complete tasks from ROADMAP.md ([x] checkboxes)
3. ✓ Uses Ollama to analyze tasks and identify suspects
4. ✓ Verifies suspects by checking test/implementation files exist
5. ✓ Stores analysis and verification results in container
6. ✓ Test suite passes: `python3 tests/test_container_audit_loop.py`
7. ✓ Dry-run mode works with real ROADMAP.md
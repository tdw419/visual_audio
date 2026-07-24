# Phase 13: Ollama-Container Integration

## Overview

Phase 13 bridges the Visual Audio container system with Ollama-powered LLM agents, enabling self-awareness, autonomous auditing, security analysis, and progress tracking. The container becomes not just a data repository but an active participant in its own development lifecycle.

### Architecture

```
                    ┌──────────────────────────────┐
                    │         Ollama LLM            │
                    │   (qwen2.5-coder:14b)         │
                    └────┬─────────────────────┬────┘
                         │                     │
              ┌──────────▼──────────┐  ┌──────▼───────┐
              │  ollama_prompt.py   │  │ ollama_memory │
              │  (audit + verify)   │  │ _manager.py  │
              └──────────┬──────────┘  │ (SQLite mem) │
                         │             └──────────────┘
              ┌──────────▼──────────────────┐
              │    ollama_security_analyzer │
              │    .py (attack vectors)     │
              └──────────┬──────────────────┘
                         │
              ┌──────────▼──────────────────┐
              │  progress_tracker.py         │
              │  (snapshots + trends)        │
              └──────────┬──────────────────┘
                         │
              ┌──────────▼──────────────────┐
              │  task_scheduler.py           │
              │  (frame metadata)            │
              └──────────┬──────────────────┘
                         │
              ┌──────────▼──────────────────┐
              │  va_container.py            │
              │  (MKV/FFV1, PNG containers)  │
              └─────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.12+
- `ollama` CLI installed and running (systemd or manual)
- Required Python packages: `numpy`, `Pillow`
- FFmpeg with FFV1 support for MKV containers
- Ollama model: `qwen2.5-coder:14b` (or configure via `OLLAMA_MODEL` env var)

### Install Dependencies

```bash
pip install numpy Pillow
ollama pull qwen2.5-coder:14b
```

### Verify Ollama is Running

```bash
ollama list
# Should show: qwen2.5-coder:14b (or your configured model)

ollama run qwen2.5-coder:14b "Hello" --nowordcount 2>&1 | head -1
# Should respond
```

## Tools Reference

### 1. `tools/ollama_prompt.py` — Container Self-Audit (TASK_A001)

Autonomous audit loop that reads `ROADMAP.md`, verifies task completion claims, and flags suspect entries.

**Usage:**
```bash
# Run a full audit with Ollama analysis
python3 tools/ollama_prompt.py --audit

# Run without Ollama (file-existence check only)
python3 tools/ollama_prompt.py --audit --no-ollama

# Single-file audit of a container
python3 tools/ollama_prompt.py --container visual_audio.mkv
```

**Key Functions:**
- `prompt_ollama()` — Send prompts to Ollama and get structured responses
- `parse_roadmap_tasks()` — Extract task metadata from `ROADMAP.md`
- `run_audit()` — Full autonomous audit loop with receipt verification
- `analyze_task_with_ollama()` — Use Ollama to assess implementation likelihood

**Exit Codes:**
- 0: Clean audit (no suspect tasks)
- 1: Suspect tasks found (check the JSON report)

### 2. `tools/ollama_memory_manager.py` — Conversation Memory (TASK_A001)

SQLite-backed persistent memory for Ollama conversations, enabling multi-turn reasoning across container restarts.

**Usage:**
```python
from ollama_memory_manager import OllamaMemoryManager

manager = OllamaMemoryManager(db_path="~/.ollama_memory.db")
session = manager.create_session("container_audit_001")
session.add_message("user", "Analyze this container for vulnerabilities")
session.add_message("assistant", "Scanning container frames...")
history = session.get_conversation_history()
```

**Key Features:**
- Session isolation via unique session IDs
- LRU cleanup on access count for memory efficiency
- Auto-truncation when sessions exceed message limits
- Atomic SQLite writes with ACID guarantees

**Database Schema:**
- `sessions` table: session_id, created_at, last_accessed, metadata, access_count
- `messages` table: id, session_id, role, content, timestamp, metadata

### 3. `tools/task_scheduler.py` — Frame-Based Task Scheduler (TASK_A002)

Reads PNG container metadata to prioritize and schedule tasks based on priority, urgency, deadlines, and dependencies.

**Usage:**
```python
from task_scheduler import TaskScheduler
from pathlib import Path

scheduler = TaskScheduler(max_concurrent=4)
scheduler.add_container(Path("task_container.png"))

task = scheduler.get_next_task()
if task:
    scheduler.mark_running(task.task_id)
    # Execute task...
    scheduler.mark_completed(task.task_id)

stats = scheduler.get_statistics()
print(stats)  # {total_tasks, ready, pending, running, completed, failed}
```

**Priority Scoring:**
- Base score = `priority * 10` (lower = higher priority)
- Urgency modifiers: immediate (-30), high (-20), normal (0), low (+10)
- Deadline modifiers: overdue (-100), <1 hour (-15), <1 day (-5)

### 4. `tools/ollama_security_analyzer.py` — Security Analysis (TASK_A004)

Uses Ollama to propose attack vectors, verify mitigations, and generate security reports.

**Usage:**
```bash
# Verify existing mitigations
python3 tools/ollama_security_analyzer.py --verify-mitigations

# Propose attack vectors (heuristic only, no Ollama)
python3 tools/ollama_security_analyzer.py --propose --no-ollama

# Propose vectors with Ollama
python3 tools/ollama_security_analyzer.py --propose --category code_execution_escape

# Generate full security report
python3 tools/ollama_security_analyzer.py --full-report -o security_report.json

# Focused analysis per category
python3 tools/ollama_security_analyzer.py --propose --category data_exfiltration --count 3
```

**Attack Categories Analyzed:**

| Category | Severity | Description |
|----------|----------|-------------|
| code_execution_escape | CRITICAL | Bypassing sandbox for arbitrary code execution |
| container_integrity | HIGH | Frame tampering, metadata corruption |
| data_exfiltration | HIGH | Side channels, covert data extraction |
| denial_of_service | MEDIUM | Resource exhaustion, decode bombs |
| audio_injection | MEDIUM | Acoustic attacks via spectral codec |
| steganography_abuse | MEDIUM | DCT/PNG steganography payload exploits |

**Mitigation Layers Verified:**

| Layer | Check | What's Validated |
|-------|-------|------------------|
| Sandbox import blocking | Blocked module count | ≥10 modules blocked in sandbox.py |
| Resource limits | RLIMIT + timeout | CPU, memory, wall-time limits in place |
| Container integrity | CRC + SHA256 | Checksums verify container data integrity |
| Codec safety | Error handling + bounds | try/except + ValueError/assert in DCT codec |
| Test coverage | Security test files | ≥3 security test files found |

### 5. `tools/progress_tracker.py` — Progress Tracking (TASK_A005)

Scans container files (MKV and PNG), extracts frame metadata, builds progress snapshots, and uses LLM interpretation to identify bottlenecks and trends.

**Usage:**
```bash
# Scan a directory for containers
python3 tools/progress_tracker.py --scan /path/to/containers

# Generate progress report with metrics
python3 tools/progress_tracker.py --progress /path/to/containers

# Interpret progress with heuristic analysis
python3 tools/progress_tracker.py --interpret /path/to/containers

# Full report with snapshot, trend, and interpretation
python3 tools/progress_tracker.py --full-report /path/to/containers -o report.json

# Use Ollama for deeper interpretation
python3 tools/progress_tracker.py --interpret /path/to/containers --ollama
```

**Report Structure:**
```json
{
  "timestamp": "2026-07-23T16:00:00",
  "scan_directory": "/path/to/containers",
  "containers": [
    {
      "path": "/path/to/task_a.png",
      "type": "png",
      "size_bytes": 1024,
      "task_type": "codec",
      "priority": 3,
      "urgency": 1
    }
  ],
  "snapshot": {
    "container_count": 10,
    "task_count": 8,
    "task_type_counts": {"codec": 5, "test": 3},
    "priority_distribution": {"high": 2, "medium": 4, "low": 2},
    "average_priority": 3.5,
    "overdue_count": 1
  },
  "trend": {
    "container_growth": 5,
    "task_growth": 4,
    "velocity": 8.0,
    "completion_rate": 0.8,
    "bottleneck_types": ["test"]
  },
  "interpretation": {
    "assessment": "healthy",
    "insights": ["Dominant task type: codec (5/8, 62%)", "Velocity: 8.0 tasks/day"],
    "warnings": [],
    "recommendations": ["Maintain momentum by tackling bottleneck types"]
  }
}
```

## Container Integration Patterns

### Pattern 1: Container Birth → Audit Loop

```bash
# 1. Create a container
python3 tools/va_container.py init work.mkv

# 2. Add tasks as entries
python3 tools/va_container.py add work.mkv code.py --name task_001 --role codec

# 3. Run self-audit
python3 tools/ollama_prompt.py --container work.mkv --audit

# 4. Track progress over time
python3 tools/progress_tracker.py --full-report . -o progress_report.json
```

### Pattern 2: Security-First Development Loop

```bash
# 1. Before merging code, run security analysis
python3 tools/ollama_security_analyzer.py --verify-mitigations

# 2. Propose attack vectors for new feature
python3 tools/ollama_security_analyzer.py --propose --category code_execution_escape

# 3. Generate full security report
python3 tools/ollama_security_analyzer.py --full-report -o sec_report.json

# 4. Only merge if all mitigation layers pass
# (all 5 layers should show PASS)
```

### Pattern 3: Multi-Session Memory Chain

```python
from ollama_memory_manager import OllamaMemoryManager

# Session 1: Initial analysis
manager = OllamaMemoryManager()
session = manager.create_session("codec_analysis")
session.add_message("user", "Analyze DCT steganography codec performance")
session.add_message("assistant", "Current throughput: 24 bytes/sec, target: 25 bytes/sec")

# Later, Session 2: Continue from memory
session2 = manager.get_session("codec_analysis")
history = session2.get_conversation_history()
# Last message: "Current throughput: 24 bytes/sec, target: 25 bytes/sec"
session2.add_message("user", "What optimization did we identify last time?")
```

### Pattern 4: Task Scheduling Pipeline

```bash
# 1. Create PNG containers with metadata
python3 tools/create_task_container.py --id task_001 --priority 1 --type codec

# 2. Schedule and track
python3 -c "
from task_scheduler import TaskScheduler
from pathlib import Path
from tools.progress_tracker import scan_containers

scheduler = TaskScheduler()
scheduler.add_container(Path('task_001.png'))
task = scheduler.get_next_task()
print(f'Next task: {task.task_id}, priority score: {task.priority_score}')
"
```

## Testing

Each tool has a dedicated test file. Run them individually or together:

```bash
# Run all Phase 13 tests
python3 -m pytest tests/test_ollama_contextual_memory.py -v
python3 -m pytest tests/test_container_task_scheduler.py -v
python3 -m pytest tests/test_container_audit_loop.py -v
python3 -m pytest tests/test_ollama_security_analysis.py -v
python3 -m pytest tests/test_frame_based_progress_tracking.py -v

# Run all at once
python3 -m pytest tests/test_ollama_contextual_memory.py \
  tests/test_container_task_scheduler.py \
  tests/test_container_audit_loop.py \
  tests/test_ollama_security_analysis.py \
  tests/test_frame_based_progress_tracking.py -v
```

**Expected test counts:**

| Test File | Tasks | Expected |
|-----------|-------|----------|
| `test_ollama_contextual_memory.py` | A001 | 43 tests |
| `test_container_task_scheduler.py` | A002 | 7 tests |
| `test_container_audit_loop.py` | A003 | 21 tests |
| `test_ollama_security_analysis.py` | A004 | 37 tests |
| `test_frame_based_progress_tracking.py` | A005 | 44 tests |

## Security Considerations

### Shared Threat Model

All Phase 13 tools share the following trust boundary:

- **Ollama is a co-process**: LLM responses are advisory, not authoritative. All Ollama output should be verified against real file existence, test results, and codebase state.
- **Memory is local**: The SQLite memory database (ollama_memory_manager.py) is stored locally and not encrypted. Treat session logs as sensitive if they contain code or analysis results.
- **Attack vectors are suggestions**: The security analyzer's proposed attack vectors are starting points for investigation, not confirmed vulnerabilities.

### Known Limitations

1. **Ollama model dependency**: Analysis quality depends on the model used. `qwen2.5-coder:14b` is the default; larger models may produce better results.
2. **Container scanning speed**: Scanning large MKV containers requires ffmpeg and can take time proportional to frame count.
3. **Heuristic fallback**: When Ollama is unavailable (--no-ollama), all tools fall back to rule-based heuristics that cover common cases but miss novel patterns.

### Best Practices

1. Always run `--verify-mitigations` after code changes
2. Keep `OLLAMA_MODEL` environment variable consistent across sessions
3. Periodically clean up old Ollama memory sessions with `llist_sessions()` and `delete_session()`
4. Use `--no-ollama` in CI pipelines where Ollama may not be available

## Cross-Phase Dependencies

| Phase 13 Task | Requires From Earlier Phases | Provides To |
|--------------|------------------------------|-------------|
| A001 (Memory + Audit) | Frame format (Phase 0), va_container.py (Phase 0) | A003, A004, A005 |
| A002 (Task Scheduler) | PNG metadata format | A005 |
| A003 (Container Audit Loop) | A001, Ollama integration | A004 |
| A004 (Security Analysis) | A003 (audit patterns), sandbox.py | Phase 14+ |
| A005 (Progress Tracking) | A002 (task metadata), A004 (security metrics) | Phase 14+ |

---

**Document Version**: 1.0
**Last Updated**: 2026-07-23
**Tasks Covered**: TASK_A001 — TASK_A005
**Status**: Complete — All Phase 13 tasks implemented and tested

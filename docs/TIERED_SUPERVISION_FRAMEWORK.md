# Tiered Supervision Framework - Documentation

## Overview

The Tiered Supervision Framework provides a reusable, production-ready architecture for monitoring and recovering long-running autonomous tasks. It decouples task logic from orchestration through standardized interfaces for **State**, **Supervision**, and **Tiered Execution**.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Tiered Cron Orchestrator                 │
│  - Tier 1 (1-5 min): Process health, crash recovery         │
│  - Tier 2 (15-30 min): Progress verification, stall checks  │
│  - Tier 3 (1 hr+): Resource cleanup, success/alerts         │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
       checks & restarts              reads checkpoints
               ▼                               ▼
┌──────────────────────────────┐ ┌─────────────────────────────┐
│    Standard Worker Daemon    │ │    Persistent State Store   │
│   (Implements BaseWorker)    │ │   (Atomic JSON / SQLite)    │
│  - Signal handling (SIGTERM) │ │  - Checkpoint metrics       │
│  - Step iteration            │ │  - Applied mutations/fixes │
│  - Heartbeat & Checkpoints   │ │  - Run status & lockfiles   │
└──────────────────────────────┘ ┌─────────────────────────────┘
```

## Components

### 1. BaseWorker (`tools/base_worker.py`)

Abstract base class for supervised long-running workers. Provides:

- **Signal handling**: Graceful shutdown on SIGTERM/SIGINT
- **Heartbeat mechanism**: Periodic heartbeat file updates
- **Atomic state persistence**: Safe checkpoint writes
- **Progress tracking**: Track iteration, best progress, applied mutations

```python
from tools.base_worker import BaseWorker, WorkerState

class MyWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            state_file='worker_state.json',
            heartbeat_file='/tmp/worker_heartbeat',
            heartbeat_interval=30
        )

    def run_iteration(self) -> bool:
        """
        Run one atomic work unit.

        Returns:
            True: Task completed successfully
            False: Task not yet complete, continue iterating
        """
        # Your task logic here
        progress = do_something()
        self.update_progress(progress)

        if progress >= SUCCESS_THRESHOLD:
            self.apply_mutation("task_completed")
            return True
        return False

    def on_shutdown(self):
        """Persist in-flight state before exit"""
        self.save_state()
        # Your cleanup logic here

# Usage
worker = MyWorker()
worker.run(max_iterations=100)
```

### 2. SupervisorEngine (`tools/supervisor_engine.py`)

Generic supervisory engine parameterized with validation rules:

- **Process health monitoring**: Heartbeat freshness check
- **Progress validation**: Pluggable progress evaluator function
- **Crash recovery**: Automatic restart with exponential backoff
- **Rate limiting**: Prevent crash loops

```python
from tools.supervisor_engine import SupervisorEngine, SupervisorConfig

def progress_validator(state: dict) -> tuple[bool, str]:
    """Custom progress validation logic"""
    recent = state.get('results', [])[-5:]
    steps = [r.get('steps', 0) for r in recent]
    is_progressing = len(set(steps)) > 1
    return is_progressing, "making_progress" if is_progressing else "stalled"

def success_detector(state: dict) -> bool:
    """Custom success detection logic"""
    return state.get('best_progress', 0) >= SUCCESS_THRESHOLD

config = SupervisorConfig(
    max_heartbeat_age=120,
    max_restart_backoff=300,
    max_restarts_per_hour=6,
    progress_evaluator=progress_validator,
    success_evaluator=success_detector
)

engine = SupervisorEngine(
    worker_cmd=['python3', 'my_worker.py'],
    state_file='worker_state.json',
    heartbeat_file='/tmp/worker_heartbeat',
    supervisor_state_file='supervisor_state.json',
    config=config
)

# Run different supervision tiers
engine.run_tier1_watchdog()    # Fast crash detection
engine.run_tier2_progress_auditor()  # Progress checks
engine.run_tier3_gc_and_success()  # Success detection
```

### 3. Task Specification (JSON)

Declarative configuration for supervised tasks:

```json
{
    "name": "My Autonomous Task",
    "description": "Long-running task with automatic recovery",
    "worker_cmd": ["python3", "my_worker.py"],
    "state_file": "worker_state.json",
    "heartbeat_file": "/tmp/worker_heartbeat",
    "supervisor_state_file": "supervisor_state.json",
    "max_heartbeat_age": 120,
    "max_restart_backoff": 300,
    "max_restarts_per_hour": 6,
    "success_threshold": 100000000
}
```

### 4. Supervisor CLI (`tools/supervisor_cli.py`)

CLI tool for tiered supervision:

```bash
# Tier 1: Fast crash detection (every 1-5 min)
supervisor-cli check-liveness --config task_spec.json

# Tier 2: Progress audit (every 15-30 min)
supervisor-cli audit-progress --config task_spec.json

# Tier 3: GC and success handler (every 1 hr)
supervisor-cli sweep-and-report --config task_spec.json
```

## Tiered Cron Scheduling

Split monitoring duties across multiple schedules:

| Schedule | Frequency | Responsibility | Failures Mitigated |
|----------|-----------|----------------|-------------------|
| **Tier 1** | `*/5 * * * *` | Heartbeat & PID presence | Silent death, OOM kills |
| **Tier 2** | `*/15 * * * *` | Checkpoint delta comparison | Infinite loops, deadlocks |
| **Tier 3** | `0 * * * *` | Process age, success cleanup | Memory leaks, zombies |

### Crontab Configuration

```cron
# Tier 1: Fast crash detection
*/5 * * * * cd /project && python3 tools/supervisor_cli.py check-liveness --config task.json

# Tier 2: Progress audit
*/15 * * * * cd /project && python3 tools/supervisor_cli.py audit-progress --config task.json

# Tier 3: GC and success handler
0 * * * * cd /project && python3 tools/supervisor_cli.py sweep-and-report --config task.json
```

## Key Design Guardrails

### 1. Atomic State Writes

Always write to temporary file before renaming:

```python
# Bad: Corrupt on crash
with open(state_file, 'w') as f:
    json.dump(state, f)

# Good: Atomic
temp_file = state_file.with_suffix('.tmp')
with open(temp_file, 'w') as f:
    json.dump(state, f)
os.replace(temp_file, state_file)  # Atomic rename
```

### 2. Exponential Backoff

Prevent crash loops with backoff:

```python
# Restart delay: 2^restart_count seconds (capped at 300s)
backoff = min(2 ** restart_count, max_restart_backoff)
if time_since_restart < backoff:
    # Skip restart, wait for backoff period
    return False
```

### 3. Rate Limiting

Limit restarts per hour:

```python
if restarts_in_last_hour >= MAX_RESTARTS_PER_HOUR:
    log("⚠ Restart limit exceeded, alerting human")
    return False
```

### 4. Clean Exit on Success

Disable supervisor when task completes:

```python
if check_success(state):
    log("🎉 SUCCESS achieved")
    # Kill worker
    subprocess.run(['kill', str(pid)])
    # Disable supervisor crons (implementation-specific)
    disable_supervisor_crons()
```

## Example: Alpine Boot Worker

Full implementation example:

```python
# alpine_boot_worker.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))

from base_worker import BaseWorker

class AlpineBootWorker(BaseWorker):
    def __init__(self):
        super().__init__(
            state_file='alpine_boot_state.json',
            heartbeat_file='/tmp/alpine_boot_heartbeat',
            heartbeat_interval=30
        )

    def run_iteration(self) -> bool:
        self.log(f"Iteration {self.state.iteration}")

        # Run boot attempt
        steps = run_boot_attempt()

        # Update progress
        self.update_progress(steps)

        # Check for success
        if steps >= 100000000:
            self.apply_mutation("boot_success")
            return True

        return False

    def on_shutdown(self):
        self.save_state()

if __name__ == '__main__':
    worker = AlpineBootWorker()
    sys.exit(0 if worker.run(max_iterations=100) else 1)
```

```bash
# alpine_boot_task.json
{
    "name": "Alpine Boot Worker",
    "worker_cmd": ["python3", "alpine_boot_worker.py"],
    "state_file": "alpine_boot_state.json",
    "heartbeat_file": "/tmp/alpine_boot_heartbeat",
    "supervisor_state_file": "alpine_boot_supervisor_state.json"
}
```

```bash
# Install crontab entries
crontab - <<'EOF'
*/5 * * * * cd /project && python3 tools/supervisor_cli.py check-liveness --config alpine_boot_task.json
*/15 * * * * cd /project && python3 tools/supervisor_cli.py audit-progress --config alpine_boot_task.json
0 * * * * cd /project && python3 tools/supervisor_cli.py sweep-and-report --config alpine_boot_task.json
EOF
```

## Migration from Single-Supervisor Pattern

To migrate from single supervisor to tiered framework:

**Before:**
```cron
*/5 * * * * python3 supervisor.py  # All logic in one script
```

**After:**
```cron
*/5 * * * * python3 supervisor_cli.py check-liveness --config task.json
*/15 * * * * python3 supervisor_cli.py audit-progress --config task.json
0 * * * * python3 supervisor_cli.py sweep-and-report --config task.json
```

## Benefits

1. **Decoupling**: Task logic independent of supervision
2. **Reusability**: BaseWorker works for any long-running task
3. **Tiered optimization**: Fast checks for critical issues, slower checks for progress
4. **Crash recovery**: Automatic restart with backoff and rate limiting
5. **Atomic persistence**: No corrupted state files
6. **Production-ready**: Includes guardrails and monitoring

## Files in This Framework

- `tools/base_worker.py` - Abstract worker base class
- `tools/supervisor_engine.py` - Generic supervisory engine
- `tools/supervisor_cli.py` - CLI tool for tiered supervision
- `alpine_boot_worker.py` - Example worker implementation
- `alpine_boot_task.json` - Example task specification
- `alpine_boot_supervisor_state.json` - Supervisor persistent state

## Related Documentation

- `docs/SUPERVISORY_CRON_PATTERN.md` - Pattern rationale and explanation
- `docs/SUPERVISORY_CRON_SUCCESS_RECEIPT.md` - Real-world validation
- `docs/SUPERVISORY_CRON_LIVE_RECEIPT.md` - Live crash recovery documentation

---

**Framework Status**: Production-ready
**Last Updated**: 2026-08-27
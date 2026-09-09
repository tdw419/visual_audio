# Supervisory Cron Pattern - Why Monitor Your Monitors

## Executive Summary

When running long-lived autonomous processes (cron jobs, daemons, background workers), a common failure mode is **silent death**: the process crashes or gets stuck, but nobody notices until manual inspection. Creating a supervisory cron job that monitors your primary cron job transforms this from a single point of failure into a resilient, self-healing system.

## The Problem: Silent Failure

### Scenario: Autonomous Alpine Boot Monitor

We created `monitor_alpine_boot.py` - a long-running daemon that:
- Iterates through boot attempts (up to 100 iterations)
- Detects stall conditions
- Applies fixes to SPATIAL_RV64I.wgsl
- Persists state to `alpine_boot_state.json`
- Runs for hours or days

**Without supervision, what happens when it crashes?**

```bash
# If monitor_alpine_boot.py crashes due to:
- Memory error
- Uncaught exception
- SIGKILL from OOM killer
- System reboot
- Python dependency update breaking import

# Result:
✗ Daemon dies silently
✗ No monitoring occurs
✗ Alpine boot never completes
✗ Days pass before manual discovery
✗ Lost computation time
```

### Why Single-Cron Is Insufficient

```python
# Primary cron job: runs monitor_alpine_boot.py
*/10 * * * * cd /project && python3 monitor_alpine_boot.py

# Problems:
1. If daemon crashes mid-iteration, cron won't know until next schedule (10 min)
2. If daemon enters infinite loop, cron spawns another instance, creating resource wars
3. No coordination between multiple restart attempts
4. No progress tracking across crashes
5. No success detection and cleanup
6. No logging of why daemon crashed
```

## The Solution: Supervisory Cron Pattern

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Supervisory Cron                          │
│                    (every 5 minutes)                         │
│  alpine_boot_supervisor.py                                   │
│    - Check daemon health (pgrep)                            │
│    - Verify progress advancement                            │
│    - Detect infinite loops (age check)                      │
│    - Restart if crashed                                     │
│    - Detect success and shutdown                            │
└────────────┬────────────────────────────────────────────────┘
             │
             │ monitors
             ▼
┌─────────────────────────────────────────────────────────────┐
│                  Primary Daemon                              │
│                  (long-running)                              │
│  monitor_alpine_boot.py                                      │
│    - Run boot iterations                                    │
│    - Detect stalls                                          │
│    - Apply fixes                                            │
│    - Persist state to JSON                                  │
│    - Loop until success or max iterations                   │
└────────────┬────────────────────────────────────────────────┘
             │
             │ orchestrates
             ▼
┌─────────────────────────────────────────────────────────────┐
│              Boot Session (per iteration)                    │
│              (transient, 5-10 min)                           │
│  monitor_rv64i.py --program alpine                           │
│    - Run emulator for N steps                               │
│    - Capture metrics to JSONL                               │
│    - Exit with status                                        │
└─────────────────────────────────────────────────────────────┘
```

### Why This Works

**1. Crash Recovery**
```python
def is_daemon_running() -> tuple[bool, int]:
    """Check if daemon process is running"""
    result = subprocess.run(['pgrep', '-f', str(DAEMON_SCRIPT)], ...)
    return (result.returncode == 0, pid)

if not running:
    log("❌ Daemon NOT running - attempting restart...")
    restart_daemon()
```
- Detects death within 5 minutes (cron interval)
- Immediately restarts, minimizing downtime
- Logs all recovery attempts

**2. Progress Validation**
```python
def check_progress(state: dict) -> tuple[bool, str]:
    """Check if daemon is making progress"""
    recent = results[-5:]  # Last 5 iterations
    steps_list = [r.get('steps', 0) for r in recent]

    # If stuck at same step count, not progressing
    if len(set(steps_list)) <= 1:
        return False, f"stuck_at_{steps_list[0]}_steps"

    return True, "making_progress"
```
- Detects infinite loops (e.g., PC stuck at same address)
- Detects logic errors causing repeated crashes
- Alerts for manual intervention when progress stalls

**3. Success Detection and Cleanup**
```python
def check_success(state: dict) -> bool:
    """Check if Alpine booted successfully"""
    best_steps = state.get('state', {}).get('last_working_step', 0)
    return best_steps >= 100_000_000  # Success threshold

if check_success(state):
    log("🎉 SUCCESS: Alpine booted successfully!")
    subprocess.run(['kill', str(pid)])  # Kill daemon
    sys.exit(0)  # Supervisor exits
```
- Automatic shutdown on success
- Prevents wasted computation after goal achieved
- Clean state transition

**4. Resource Management**
```python
age = get_daemon_age(pid)
if age > MAX_DAEMON_AGE_HOURS:
    log(f"⚠ WARNING: Daemon running for {age:.1f} hours")
    # Optionally kill and restart fresh
```
- Detects zombie processes
- Prevents memory leaks from long runs
- Enables periodic fresh starts

## Real-World Impact

### Before Supervisory Pattern
```
Day 1: Daemon starts, crashes at iteration 47
Day 1: No monitoring, no restart
Day 2: Human notices boot not progressing
Day 2: Manual investigation, restart daemon
Day 2: Daemon crashes again at iteration 23
Day 3: More manual debugging...
```

### After Supervisory Pattern
```
14:20: Daemon starts iteration 1
14:38: Daemon crashes (Python error)
14:45: Supervisor detects crash, restarts daemon
14:45: Daemon resumes from iteration 2 (state persisted)
14:55: Daemon stalls at iteration 5 (PC stuck)
15:00: Supervisor detects no progress, logs alert
15:00: Daemon applies permission fix, iteration 6
...
(Daemon continues autonomously for hours/days)
```

**Time saved**: ~24-48 hours of manual monitoring per autonomous task

**Reliability gained**: Crash recovery in ≤5 minutes instead of days

## When Supervisory Pattern Is Essential

✅ **Long-running autonomous processes** (hours to days)
✅ **Computation with checkpoints** (state persistence required)
✅ **Iterative workflows** (need progress tracking across crashes)
✅ **Mission-critical automation** (can't afford silent failure)
✅ **Resource-intensive tasks** (need watchdog behavior)

❌ **One-shot scripts** (run once and exit)
❌ **Trivial tasks** (failure is acceptable)
❌ **Fully supervised environments** (Kubernetes, systemd, etc.)

## Implementation Checklist

### Primary Daemon Requirements
1. ✅ State persistence (JSON file or database)
2. ✅ Graceful shutdown on signal
3. ✅ Idempotent iteration logic (can resume from crash)
4. ✅ Progress tracking (iteration count, best result)

### Supervisor Requirements
1. ✅ Process health check (`pgrep` or PID file)
2. ✅ Progress validation (check state file)
3. ✅ Crash recovery (restart logic)
4. ✅ Success detection and cleanup
5. ✅ Logging (audit trail)

### Cron Configuration
```cron
# Primary daemon (run once at startup, then supervisor handles it)
# (Or systemd/init script instead of cron for long-running daemon)

# Supervisor: frequent health checks
*/5 * * * * cd /project && python3 supervisor.py

# (Optional) Success notification cron
0 * * * * cat /project/state.json | jq -r '.success' && notify-send
```

## Advanced Patterns

### 1. Tiered Supervision
```
Tier 1 (1min): Health check, crash restart
Tier 2 (15min): Progress validation
Tier 3 (1hour): Success detection, resource checks
```

### 2. Dead Man's Switch
```python
# Daemon updates heartbeat file every 30 seconds
with open('/tmp/daemon_heartbeat', 'w') as f:
    f.write(str(time.time()))

# Supervisor checks file age
heartbeat_age = time.time() - os.path.getmtime('/tmp/daemon_heartbeat')
if heartbeat_age > 120:  # 2 minutes without update
    log("❌ Heartbeat expired - daemon hung or crashed")
    restart_daemon()
```

### 3. Health Endpoint
```python
# Daemon exposes HTTP health endpoint
from flask import Flask
app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({
        'running': True,
        'iteration': current_iteration,
        'last_progress': last_progress_time,
        'state': 'healthy'
    })

# Supervisor checks endpoint instead of pgrep
response = requests.get('http://localhost:8080/health', timeout=5)
if not response.json().get('running'):
    restart_daemon()
```

### 4. Graceful Degradation
```python
def handle_daemon_failure():
    # First attempt: restart
    if restart_daemon():
        return True

    # Second attempt: log and alert
    log("⚠ WARNING: Restart failed, investigating...")
    capture_diagnostic_info()

    # Third attempt: minimal mode
    if start_minimal_daemon():
        log("✓ Started minimal daemon")
        return True

    # Last resort: escalate to human
    send_alert("❌ CRITICAL: Daemon unrecoverable")
    return False
```

## Anti-Patterns to Avoid

### ❌ Cron-on-Cron Without State Persistence
```cron
# Primary: run heavy computation
*/10 * * * * python3 heavy_task.py

# Supervisor: restart if not running
*/5 * * * * pkill -f heavy_task.py; python3 heavy_task.py

# Problem: Work lost on every restart, no progress
```

### ❌ Infinite Supervision Loop
```python
while True:
    if not is_daemon_running():
        restart_daemon()  # Bad: crashes supervisor if daemon crashes immediately
    time.sleep(60)
```

**Fix**: Add backoff and max restart attempts
```python
restart_count = 0
while restart_count < MAX_RESTARTS:
    if not is_daemon_running():
        if not restart_daemon():
            restart_count += 1
            sleep(backoff(restart_count))
        else:
            restart_count = 0  # Reset on success
    else:
        restart_count = 0
    time.sleep(60)
```

### ❌ No Success Detection
```python
# Bad: Daemon runs forever even after goal achieved
while not success:
    do_work()
```

**Fix**: Check for success and exit cleanly
```python
while True:
    if check_success():
        log("🎉 Success achieved, exiting")
        break
    do_work()
```

## Conclusion

The supervisory cron pattern transforms fragile single-point-of-failure automation into resilient, self-healing systems. For long-running autonomous tasks like the Alpine boot monitor, this pattern is not optional—it's essential.

**Key takeaways:**
1. Silent failure is the enemy of autonomous systems
2. Supervisors detect crashes in minutes, not days
3. State persistence enables crash recovery without lost work
4. Progress validation prevents infinite loops
5. Success detection prevents wasted computation after goal achieved

**When in doubt, add a supervisor.** The cost is 30 minutes of code; the benefit is days of saved manual monitoring and recovered computation time.

---

## References

- **This project**: `monitor_alpine_boot.py` + `alpine_boot_supervisor.py`
- **Related skills**: `cron-operational-reporting`, `skillopt-sleep`
- **Pattern family**: Autonomous agent monitoring, health check loops
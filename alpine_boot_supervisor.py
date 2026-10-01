#!/usr/bin/env python3
"""
Alpine Boot Supervisor - Monitors and supervises the autonomous boot daemon

This cron job checks:
- Daemon process health
- Progress advancement
- Crash recovery
- Success detection
"""

import subprocess
import json
import os
import sys
import signal
from pathlib import Path
from datetime import datetime

# Configuration
PROJECT_ROOT = Path("/home/jericho/projects/zion/projects/visual_audio")
DAEMON_SCRIPT = PROJECT_ROOT / "monitor_alpine_boot.py"
STATE_FILE = PROJECT_ROOT / "alpine_boot_state.json"
LOG_FILE = Path("/tmp/alpine_supervisor.log")

# Thresholds
MAX_STALL_ITERATIONS = 10  # Alert if no progress for N iterations
MAX_DAEMON_AGE_HOURS = 24  # Alert if daemon running too long without success

def log(message: str):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + '\n')

def is_daemon_running() -> tuple[bool, int]:
    """Check if daemon process is running"""
    try:
        result = subprocess.run(
            ['pgrep', '-f', str(DAEMON_SCRIPT)],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            return True, int(pids[0])
        return False, 0
    except Exception as e:
        log(f"Error checking daemon: {e}")
        return False, 0

def get_daemon_age(pid: int) -> float:
    """Get daemon age in hours"""
    try:
        # Get process start time in seconds since epoch
        with open(f'/proc/{pid}/stat', 'r') as f:
            stat = f.read()
        # Field 22 is starttime (in jiffies)
        starttime = int(stat.split()[22])
        # Get system uptime and boot time
        uptime = float(subprocess.run(['cat', '/proc/uptime'], capture_output=True, text=True).stdout.split()[0])
        boot_time = datetime.now().timestamp() - uptime
        # Convert jiffies to seconds (usually 100 Hz)
        hz = os.sysconf('SC_CLK_TCK')
        proc_start = boot_time + (starttime / hz)
        age = (datetime.now().timestamp() - proc_start) / 3600  # Convert to hours
        return age
    except Exception as e:
        log(f"Error getting daemon age: {e}")
        return 0

def load_state() -> dict:
    """Load boot state"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"Error loading state: {e}")
    return {}

def check_progress(state: dict) -> tuple[bool, str]:
    """Check if daemon is making progress"""
    if not state:
        return False, "no_state_file"

    current_iter = state.get('state', {}).get('iteration', 0)
    results = state.get('results', [])

    if len(results) < 2:
        return False, "insufficient_history"

    # Check last few iterations for progress
    recent = results[-min(5, len(results)):]
    steps_list = [r.get('steps', 0) for r in recent]

    # If all steps are 0 or equal, not making progress
    if len(set(steps_list)) <= 1:
        return False, f"stuck_at_{steps_list[0]}_steps"

    return True, "making_progress"

def restart_daemon():
    """Restart the daemon"""
    log("Attempting to restart daemon...")
    # Kill existing
    subprocess.run(['pkill', '-f', str(DAEMON_SCRIPT)], timeout=10)
    # Start new
    try:
        subprocess.Popen(
            ['python3', str(DAEMON_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=PROJECT_ROOT,
            start_new_session=True
        )
        log("Daemon restarted successfully")
        
        # Check for EFAULT fix (epoch-based decoded_ops invalidation)
        try:
            wgsl_path = PROJECT_ROOT / "tools" / "SPATIAL_RV64I.wgsl"
            with open(wgsl_path) as f:
                wgsl_content = f.read()
            
            if "decoded_ops_epoch" in wgsl_content:
                log("INFO: EFAULT fix detected in WGSL")
                
                # Check if state needs reset
                state_file = PROJECT_ROOT / "alpine_boot_state.json"
                if state_file.exists():
                    with open(state_file) as f:
                        import json
                        state = json.loads(f.read())
                    
                    iteration = state.get('state', {}).get('iteration', 0)
                    if iteration > 0 and 'epoch_fix_verified' not in state.get('state', {}).get('applied_fixes', []):
                        log(f"INFO: Clearing stale state (iteration {iteration})")
                        
                        # Reset state
                        state['state']['iteration'] = 0
                        state['state']['applied_fixes'] = ['epoch_fix_verified']
                        state['state']['status'] = 'fixed_externally'
                        state['state']['last_working_step'] = 0
                        state['results'] = []
                        
                        with open(state_file, 'w') as f:
                            json.dump(state, f, indent=2, default=str)
                        
                        log("INFO: State reset to iteration 0")
        except Exception as e:
            log(f"WARN: Could not check EFAULT fix: {e}")

        return True
    except Exception as e:
        log(f"Failed to restart daemon: {e}")
        return False

def check_success(state: dict) -> bool:
    """Check if Alpine booted successfully"""
    if not state:
        return False

    # Check last result for success
    results = state.get('results', [])
    if results:
        last_result = results[-1]
        if last_result.get('status') == 'success':
            return True

    # Check if best progress meets success threshold
    best_steps = state.get('state', {}).get('last_working_step', 0)
    return best_steps >= 100_000_000  # Success threshold

def main():
    log("=" * 70)
    log("ALPINE BOOT SUPERVISOR CHECK")
    log("=" * 70)

    # Check daemon status
    running, pid = is_daemon_running()

    if not running:
        log("❌ Daemon NOT running - attempting restart...")
        if restart_daemon():
            log("✓ Daemon restarted")
        else:
            log("✗ Failed to restart daemon")
            sys.exit(1)
        return

    log(f"✓ Daemon running (PID: {pid})")

    # Get daemon age
    age = get_daemon_age(pid)
    log(f"  Age: {age:.1f} hours")

    if age > MAX_DAEMON_AGE_HOURS:
        log(f"⚠ WARNING: Daemon running for {age:.1f} hours (max: {MAX_DAEMON_AGE_HOURS}h)")

    # Load state
    state = load_state()
    if state:
        iteration = state.get('state', {}).get('iteration', 0)
        best_steps = state.get('state', {}).get('last_working_step', 0)
        fixes = state.get('state', {}).get('applied_fixes', [])
        log(f"  Iteration: {iteration}")
        log(f"  Best progress: {best_steps:,} steps")
        log(f"  Fixes applied: {', '.join(fixes) or 'none'}")
    else:
        log("  No state file found")
        log("  Daemon may be starting up...")

    # Check for success
    if check_success(state):
        log("🎉 SUCCESS: Alpine booted successfully!")
        log("  Killing daemon...")
        subprocess.run(['kill', str(pid)], timeout=5)
        log("  ✗ Supervisor exiting")
        sys.exit(0)

    # Check progress
    making_progress, progress_status = check_progress(state)
    if not making_progress:
        log(f"⚠ WARNING: Not making progress ({progress_status})")
        log("  Consider manual investigation")
    else:
        log(f"✓ {progress_status}")

    log("=" * 70)
    log("Supervisor check complete - daemon healthy")
    log("=" * 70)

if __name__ == "__main__":
    main()
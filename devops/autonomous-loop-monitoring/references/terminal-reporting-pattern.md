# Terminal Reporting for Human Oversight

Autonomous cron jobs need human-readable terminal output that's easy to scan and understand. The basic `DaemonMonitor` template provides minimal logging, but adding rich output makes monitoring much easier.

## Rich Terminal Output Pattern

The glyph_dispatch cron job demonstrated a terminal reporting pattern for roadmap builder autonomous loops:

```python
def execute_iteration(self) -> dict:
    iteration = self.state.get('iteration', 0) + 1
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    result = {
        'status': 'success',
        'steps': 0,
        'stall_mode': None,
        'details': {},
        'iteration': iteration,
    }
    
    try:
        import subprocess
        import json
        
        # Print iteration header
        print(f"\n{'='*70}")
        print(f"[{timestamp}] Roadmap Builder Iteration {iteration}")
        print(f"{'='*70}")
        
        # Parse current roadmap state before running
        if self.roadmap_file.exists():
            with open(self.roadmap_file) as f:
                roadmap = json.load(f)
                total_tasks = len(roadmap['tasks'])
                done_tasks = sum(1 for t in roadmap['tasks'] if t['status'] == 'done')
                pending_tasks = sum(1 for t in roadmap['tasks'] if t['status'] == 'pending')
                blocked_tasks = sum(1 for t in roadmap['tasks'] if t['status'] == 'blocked')
                
                # Find next pending task
                next_task = None
                for t in roadmap['tasks']:
                    if t['status'] == 'pending':
                        done_ids = {tid for tid, status in self._get_task_statuses(roadmap).items() if status == 'done'}
                        if set(t.get('deps', [])).issubset(done_ids):
                            next_task = t
                            break
                
                # Print pre-execution status
                print(f"\n📋 Roadmap Status:")
                print(f"   Total: {total_tasks} | ✅ Done: {done_tasks} | ⏳ Pending: {pending_tasks} | 🚫 Blocked: {blocked_tasks}")
                
                if next_task:
                    print(f"\n🔄 Next Task: {next_task['id']} - {next_task['title']}")
                elif blocked_tasks > 0:
                    blocked_list = [t['id'] for t in roadmap['tasks'] if t['status'] == 'blocked']
                    print(f"\n⚠️  All pending tasks blocked: {blocked_list}")
                else:
                    print(f"\n✅ All tasks complete!")
        
        # Run daemon
        proc = subprocess.run(
            ["python3", str(self.daemon_script), "--once"],
            capture_output=True,
            text=True,
            cwd=str(ROADMAP_DIR)
        )
        
        result['details']['exit_code'] = proc.returncode
        result['details']['output'] = proc.stdout[-1000:] if proc.stdout else ""
        result['details']['error'] = proc.stderr[-1000:] if proc.stderr else ""
        
        # Print daemon output
        if proc.stdout:
            print(f"\n📤 Daemon Output:")
            for line in proc.stdout.strip().split('\n')[-20:]:  # Last 20 lines
                print(f"   {line}")
        
        # Parse post-execution roadmap state
        if self.roadmap_file.exists():
            with open(self.roadmap_file) as f:
                roadmap = json.load(f)
                result['details']['tasks'] = {
                    t['id']: t['status'] for t in roadmap['tasks']
                }
                result['details']['total_tasks'] = len(roadmap['tasks'])
                result['details']['done_tasks'] = sum(1 for t in roadmap['tasks'] if t['status'] == 'done')
                result['details']['pending_tasks'] = sum(1 for t in roadmap['tasks'] if t['status'] == 'pending')
                result['details']['blocked_tasks'] = sum(1 for t in roadmap['tasks'] if t['status'] == 'blocked')
                
                # Print task-by-task status
                print(f"\n📊 Task Status:")
                for t in roadmap['tasks']:
                    status_icon = '✅' if t['status'] == 'done' else '⏳' if t['status'] == 'pending' else '🚫'
                    deps_str = f" (deps: {', '.join(t.get('deps', []))})" if t.get('deps') else ""
                    print(f"   {status_icon} {t['id']}: {t['title']}{deps_str}")
        
        # Print daemon exit code
        print(f"\n🏁 Exit Code: {proc.returncode}")
        
        if proc.returncode == 0:
            result['status'] = 'success'
            print(f"✅ Iteration {iteration} completed successfully")
        else:
            result['status'] = 'failure'
            result['stall_mode'] = 'task_failure'
            print(f"❌ Iteration {iteration} failed")
            
            # Print error details
            if proc.stderr:
                print(f"\n❌ Error Output:")
                for line in proc.stderr.strip().split('\n')[-10:]:
                    print(f"   {line}")
        
        self._update_code_epoch()
        
    except Exception as e:
        result['status'] = 'error'
        result['stall_mode'] = 'unexpected_error'
        result['details']['error'] = str(e)
        print(f"\n💥 Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
    
    return result
```

## Example Output

```
======================================================================
[2026-08-31 07:30:00] Roadmap Builder Iteration 1
======================================================================

📋 Roadmap Status:
   Total: 9 | ✅ Done: 2 | ⏳ Pending: 7 | 🚫 Blocked: 0

🔄 Next Task: P2-3 - Add Phase 2 implementation intent comments to test skeleton

📤 Daemon Output:
   [2026-08-31 07:30:00] Task P2-3: Add Phase 2 implementation intent comments to test skeleton
   [2026-08-31 07:30:01] ✓ Task P2-3 done (3/9), committed

📊 Task Status:
   ✅ P2-1: Add Phase 2 implementation intent comments to WGSL skeleton
   ✅ P2-2: Add Phase 2 implementation intent comments to Python skeleton
   ✅ P2-3: Add Phase 2 implementation intent comments to test skeleton
   ⏳ P3-1: Implement MMIO write handler in WGSL shader (deps: P2-1)
   ⏳ P3-2: Integrate MMIO handler into WGSL mmio_write function (deps: P3-1)
   ⏳ P3-3: Create WGSL lockstep test for MMIO handler (deps: P3-2)
   ⏳ P4-1: Implement SHA-256 glyph kernel (Python stub) (deps: P3-3)
   ⏳ P4-2: Create SHA-256 lockstep test (deps: P4-1)
   ⏳ P4-3: Integrate SHA-256 glyph kernel into dispatcher (deps: P4-2)

🏁 Exit Code: 0
✅ Iteration 1 completed successfully
```

## Key Features

1. **Iteration header** with timestamp and iteration number
2. **Roadmap status summary** (total/done/pending/blocked) with icons
3. **Next task identification** with title
4. **Daemon output** (last 20 lines, truncated)
5. **Task-by-task status** with icons and dependencies
6. **Exit code** and final status (success/failure)
7. **Error details** on failure (last 10 lines)

## Cron Wrapper Pattern

For cron execution, wrap the supervisor with a cron wrapper that handles path issues:

```python
#!/usr/bin/env python3
"""Cron wrapper for roadmap supervisor."""

import sys
import os
from pathlib import Path

# Set up environment
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
sys.path.insert(0, str(script_dir.parent / "templates"))

os.chdir(script_dir)

# Import and run the supervisor
exec(open(script_dir / "roadmap-glyph-dispatch_supervisor.py").read())
```

## When Manual Intervention is Required

The session demonstrated a stuck loop pattern:

**Symptom:**
```
Iteration 1-32: Same task failing repeatedly
Task P2-2: Add Phase 2 implementation intent comments to Python skeleton
✗ Task P2-2 acceptance failed (unknown), attempt 1/3
```

**Root Cause:**
- File already had comments (from git commit)
- `sed` command was idempotent but didn't add missing bullet points
- Acceptance test checked for bullet points that weren't added

**Fix Pattern:**
1. Pause cron job to stop loop
2. Diagnose: Check file exists, check actual content
3. Fix manually: Add missing bullet points with `sed -i`
4. Commit changes
5. Resume cron job

**Detection:**
- Same task failing for >3 iterations
- Exit code always 1 with same error message
- No new git commits
- `last_working_step` not incrementing
```
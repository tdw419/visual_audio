#!/usr/bin/env python3
"""
Alpine Boot Worker Wrapper - Simple supervisor for monitor_alpine_boot.py.

This wrapper provides BaseWorker benefits (crash recovery, heartbeat, tiered supervision)
while delegating the actual monitoring logic to the battle-tested monitor_alpine_boot.py.

The monitor writes its own state; wrapper just provides heartbeat and crash recovery.
"""

import sys
import subprocess
import json
import signal
import time
from pathlib import Path

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))

from base_worker import BaseWorker, WorkerState

# Configuration
MONITOR_SCRIPT = Path('monitor_alpine_boot.py')
MONITOR_STATE_FILE = Path('alpine_boot_state.json')  # Written by monitor_alpine_boot.py
SUCCESS_THRESHOLD = 100_000_000


class AlpineBootWorkerWrapper(BaseWorker):
    """Simple wrapper that supervises monitor_alpine_boot.py"""

    def __init__(self):
        super().__init__(
            state_file='alpine_boot_wrapper_state.json',  # Different state file
            heartbeat_file='/tmp/alpine_boot_heartbeat',
            heartbeat_interval=30
        )

        self.monitor_process = None
        self.setup_signal_handlers()

    def setup_signal_handlers(self):
        """Handle shutdown gracefully, propagating to monitor process"""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Propagate signal to monitor process"""
        self.log(f"Received signal {signum}, shutting down...")
        if self.monitor_process and self.monitor_process.poll() is None:
            self.monitor_process.send_signal(signum)
            # Give monitor time to clean up
            time.sleep(2)
        sys.exit(0)

    def run_iteration(self) -> bool:
        """
        Run monitor_alpine_boot.py for one boot attempt.

        Returns:
            True: Alpine boot successful (100M+ steps)
            False: Continue iterating
        """
        self.log(f"Starting iteration {self.state.iteration + 1}...")

        if not MONITOR_SCRIPT.exists():
            self.log(f"ERROR: Monitor script not found: {MONITOR_SCRIPT}")
            return False

        try:
            # Run monitor script (it handles one boot attempt internally)
            result = subprocess.run(
                ['python3', str(MONITOR_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=1800  # 30 min max per iteration
            )

            # Read monitor's state file to get progress
            steps = self._read_monitor_state()
            self.update_progress(steps)

            self.log(f"Iteration complete: {steps:,} steps, exit={result.returncode}")

            # Check for success
            if steps >= SUCCESS_THRESHOLD and result.returncode == 0:
                self.log("🎉 Alpine boot successful!")
                return True

            return False

        except subprocess.TimeoutExpired:
            self.log("Iteration timed out after 30 minutes")
            return False
        except Exception as e:
            self.log(f"Iteration failed: {e}")
            return False

    def _read_monitor_state(self) -> int:
        """Read best step progress from monitor's state file"""
        try:
            if MONITOR_STATE_FILE.exists():
                with open(MONITOR_STATE_FILE, 'r') as f:
                    state = json.load(f)
                    # Monitor writes: state.last_working_step
                    return int(state.get('state', {}).get('last_working_step', 0))
        except Exception as e:
            self.log(f"Warning: Could not read monitor state: {e}")
        return 0

    def on_shutdown(self):
        """Persist state before exit"""
        self.log("Shutting down wrapper...")
        if self.monitor_process and self.monitor_process.poll() is None:
            self.monitor_process.terminate()
        self.save_state()


def main():
    """Main entry point"""
    worker = AlpineBootWorkerWrapper()

    try:
        worker.run(max_iterations=100)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
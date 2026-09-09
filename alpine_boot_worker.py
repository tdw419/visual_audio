#!/usr/bin/env python3
"""
Real Alpine Boot Worker - Supervised worker using BaseWorker framework.

Ported from monitor_alpine_boot.py to use BaseWorker pattern for:
- Automatic crash recovery
- State persistence
- Heartbeat monitoring
- Tiered supervision
"""

import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, Optional

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent / 'tools'))

from base_worker import BaseWorker, WorkerState

# Configuration
BOOT_SCRIPT = Path('standalone_alpine_boot_quick.py')
MAX_STEPS_PER_RUN = 500_000_000
MIN_SUCCESS_STEPS = 100_000_000


class RealAlpineBootWorker(BaseWorker):
    """Worker for autonomous Alpine Linux boot monitoring (real implementation)"""

    def __init__(self):
        super().__init__(
            state_file='alpine_boot_state.json',
            heartbeat_file='/tmp/alpine_boot_heartbeat',
            heartbeat_interval=30
        )

        # Load legacy state format from monitor_alpine_boot.py if exists
        self._maybe_migrate_legacy_state()

    def _maybe_migrate_legacy_state(self):
        """Migrate state from old monitor_alpine_boot.py format if needed"""
        legacy_file = Path('alpine_boot_legacy_state.json')
        if legacy_file.exists():
            try:
                with open(legacy_file, 'r') as f:
                    legacy = json.load(f)

                # Map legacy format to WorkerState
                self.state.last_progress_metric = float(legacy.get('state', {}).get('last_working_step', 0))
                self.state.best_progress_metric = float(legacy.get('state', {}).get('last_working_step', 0))

                # Preserve fixes history
                fixes = legacy.get('state', {}).get('applied_fixes', [])
                if fixes:
                    self.state.applied_mutations = fixes

                self.save_state()
                self.log(f"Migrated legacy state from iteration {legacy.get('state', {}).get('iteration', 0)}")
            except Exception as e:
                self.log(f"Failed to migrate legacy state: {e}")

    def run_boot_attempt(self) -> Dict:
        """
        Run a single Alpine boot attempt.

        Returns:
            Dictionary with boot metrics
        """
        self.log(f"Starting boot attempt (iteration {self.state.iteration})...")

        if not BOOT_SCRIPT.exists():
            self.log(f"ERROR: Boot script not found: {BOOT_SCRIPT}")
            return {
                'status': 'error',
                'steps': 0,
                'error': f'Boot script not found: {BOOT_SCRIPT}'
            }

        try:
            result = subprocess.run(
                ['python3', str(BOOT_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=1800  # 30 min max
            )

            # Parse output for step count
            steps = 0
            for line in result.stdout.split('\n'):
                # Look for "Steps 123456:" (number before colon)
                import re
                match = re.search(r'Steps\s+(\d+):', line)
                if match:
                    try:
                        steps = int(match.group(1))
                        break  # Use the last (highest) step count
                    except:
                        pass

            # Check for success indicators
            success = 'OpenSBI' in result.stdout or 'Linux' in result.stdout

            return {
                'status': 'success' if success else 'error',
                'steps': steps,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode
            }

        except subprocess.TimeoutExpired:
            self.log("Boot attempt timed out after 30 minutes")
            return {
                'status': 'timeout',
                'steps': 0,
                'error': 'Timeout after 30 minutes'
            }
        except Exception as e:
            self.log(f"Boot attempt failed: {e}")
            return {
                'status': 'error',
                'steps': 0,
                'error': str(e)
            }

    def run_iteration(self) -> bool:
        """
        Run one boot attempt iteration.

        Returns:
            True: Alpine booted successfully
            False: Need more iterations
        """
        self.log(f"Starting iteration {self.state.iteration + 1}...")

        # Run boot attempt
        metrics = self.run_boot_attempt()

        # Update progress
        steps = metrics.get('steps', 0)
        self.update_progress(steps)

        self.log(f"Iteration {self.state.iteration}: {steps:,} steps, status={metrics['status']}")

        # Check for success
        if steps >= MIN_SUCCESS_STEPS and metrics['status'] == 'success':
            self.log("🎉 Alpine boot successful!")
            return True

        # Check if we made progress
        if steps > self.state.best_progress_metric:
            self.log(f"New best: {steps:,} steps (was {self.state.best_progress_metric:,})")

        # Continue iterating
        return False

    def on_shutdown(self):
        """Persist state before exit"""
        self.log("Shutting down Alpine boot worker...")
        self.save_state()


def main():
    """Main entry point"""
    worker = RealAlpineBootWorker()

    try:
        worker.run(max_iterations=100)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
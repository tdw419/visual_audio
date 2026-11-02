"""
SupervisorEngine - Generic supervisory engine for monitored workers.

The supervisor is parameterized with validation rules rather than hardcoded logic.
Supports:
- Process health monitoring (heartbeat)
- Progress validation
- Crash recovery with exponential backoff
- Success detection and cleanup
"""

import subprocess
import json
import time
import os
from pathlib import Path
from typing import Callable, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SupervisorConfig:
    """Configuration for supervisor behavior"""
    max_heartbeat_age: int = 120  # Seconds before heartbeat considered stale
    max_restart_backoff: int = 300  # Max seconds to wait between restarts
    max_restarts_per_hour: int = 6  # Limit restart loops
    progress_evaluator: Optional[Callable] = None  # Function to evaluate progress
    success_evaluator: Optional[Callable] = None  # Function to detect success
    on_progress_stall: Optional[Callable] = None  # Called when progress stalls
    on_success: Optional[Callable] = None  # Called when success detected


@dataclass
class SupervisorState:
    """Persistent supervisor state"""
    last_restart_time: float = 0
    restart_count: float = 0
    restart_window_start: float = 0
    restarts_in_window: int = 0

    def to_dict(self) -> dict:
        return {
            'last_restart_time': self.last_restart_time,
            'restart_count': self.restart_count,
            'restart_window_start': self.restart_window_start,
            'restarts_in_window': self.restarts_in_window
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SupervisorState':
        return cls(
            last_restart_time=data.get('last_restart_time', 0),
            restart_count=data.get('restart_count', 0),
            restart_window_start=data.get('restart_window_start', 0),
            restarts_in_window=data.get('restarts_in_window', 0)
        )


class SupervisorEngine:
    """
    Generic supervisory engine for monitored workers.

    Decouples supervision logic from task specifics through:
    - Configurable validators (progress, success)
    - Pluggable callbacks (stall, success)
    - Parameterized worker command
    """

    def __init__(
        self,
        worker_cmd: list[str],
        state_file: str,
        heartbeat_file: str,
        supervisor_state_file: str,
        config: Optional[SupervisorConfig] = None
    ):
        self.worker_cmd = worker_cmd
        self.state_file = Path(state_file)
        self.heartbeat_file = Path(heartbeat_file)
        self.supervisor_state_file = Path(supervisor_state_file)
        self.config = config or SupervisorConfig()

        # Load supervisor state
        self.supervisor_state = self._load_supervisor_state()

    def log(self, message: str):
        """Log to stdout"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [SUPERVISOR] {message}")

    def _load_supervisor_state(self) -> SupervisorState:
        """Load supervisor state from file"""
        if self.supervisor_state_file.exists():
            try:
                with open(self.supervisor_state_file, 'r') as f:
                    data = json.load(f)
                return SupervisorState.from_dict(data)
            except Exception as e:
                self.log(f"Error loading supervisor state: {e}")
        return SupervisorState()

    def _save_supervisor_state(self):
        """Atomically save supervisor state"""
        temp_file = self.supervisor_state_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.supervisor_state.to_dict(), f)
            os.replace(temp_file, self.supervisor_state_file)
        except Exception as e:
            self.log(f"Error saving supervisor state: {e}")

    def is_heartbeat_alive(self) -> bool:
        """Check if worker heartbeat is current"""
        if not self.heartbeat_file.exists():
            return False

        try:
            heartbeat_age = time.time() - os.path.getmtime(self.heartbeat_file)
            return heartbeat_age <= self.config.max_heartbeat_age
        except Exception:
            return False

    def is_process_running(self) -> Tuple[bool, Optional[int]]:
        """Check if worker process is running"""
        try:
            result = subprocess.run(
                ['pgrep', '-f', ' '.join(self.worker_cmd)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                pids = [int(p) for p in result.stdout.strip().split('\n') if p.strip()]
                return True, pids[0] if pids else None
        except Exception as e:
            self.log(f"Error checking process: {e}")
        return False, None

    def can_restart(self) -> bool:
        """Check if we should restart (exponential backoff + rate limiting)"""
        current_time = time.time()

        # Check restart rate limit
        window_age = current_time - self.supervisor_state.restart_window_start
        if window_age > 3600:  # Reset after 1 hour
            self.supervisor_state.restart_window_start = current_time
            self.supervisor_state.restarts_in_window = 0

        if self.supervisor_state.restarts_in_window >= self.config.max_restarts_per_hour:
            self.log(f"⚠ Restart limit exceeded ({self.config.max_restarts_per_hour}/hour)")
            return False

        # Exponential backoff
        time_since_restart = current_time - self.supervisor_state.last_restart_time
        if time_since_restart < self._calculate_backoff():
            self.log(f"Backoff period active, waiting {self._calculate_backoff() - time_since_restart:.0f}s")
            return False

        return True

    def _calculate_backoff(self) -> float:
        """Calculate exponential backoff time"""
        # Base backoff: 2^restart_count, capped at max_backoff
        backoff = min(2 ** self.supervisor_state.restart_count, self.config.max_restart_backoff)
        return backoff

    def restart_worker(self) -> bool:
        """Restart the worker process"""
        if not self.can_restart():
            return False

        self.log("Attempting to restart worker...")

        # Kill existing
        subprocess.run(['pkill', '-f', ' '.join(self.worker_cmd)], timeout=10)

        # Start new
        try:
            subprocess.Popen(
                self.worker_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            # Update supervisor state
            current_time = time.time()
            self.supervisor_state.last_restart_time = current_time
            self.supervisor_state.restart_count += 1
            self.supervisor_state.restart_window_start = current_time
            self.supervisor_state.restarts_in_window += 1
            self._save_supervisor_state()

            self.log("✓ Worker restarted successfully")
            return True
        except Exception as e:
            self.log(f"✗ Failed to restart worker: {e}")
            return False

    def validate_progress(self) -> Tuple[bool, str]:
        """
        Validate worker progress.

        Returns:
            (is_making_progress, status_message)
        """
        if not self.config.progress_evaluator:
            return True, "no_progress_validator"

        if not self.state_file.exists():
            return False, "no_state_file"

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            return self.config.progress_evaluator(state)
        except Exception as e:
            self.log(f"Error validating progress: {e}")
            return False, f"validation_error: {e}"

    def check_success(self) -> bool:
        """Check if worker has succeeded"""
        if not self.config.success_evaluator:
            return False

        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            return self.config.success_evaluator(state)
        except Exception as e:
            self.log(f"Error checking success: {e}")
            return False

    def run_tier1_watchdog(self):
        """
        Tier 1: Fast crash detection and automatic relaunch.

        Checks:
        - Heartbeat freshness
        - Process presence
        - Restart if needed
        """
        self.log("=" * 70)
        self.log("TIER 1: Watchdog Check")
        self.log("=" * 70)

        heartbeat_alive = self.is_heartbeat_alive()
        process_running, pid = self.is_process_running()

        self.log(f"Heartbeat: {'✓ alive' if heartbeat_alive else '✗ stale/missing'}")
        self.log(f"Process: {'✓ running' if process_running else '✗ dead'}")

        if heartbeat_alive and process_running:
            self.log("✓ Worker healthy")
            return True
        else:
            self.log("❌ Worker unhealthy, attempting restart...")
            return self.restart_worker()

    def run_tier2_progress_auditor(self):
        """
        Tier 2: Progress verification and stall checks.

        Checks:
        - Progress advancement
        - Stall detection
        - Calls on_progress_stall callback if configured
        """
        self.log("=" * 70)
        self.log("TIER 2: Progress Audit")
        self.log("=" * 70)

        making_progress, status = self.validate_progress()

        self.log(f"Progress: {'✓ ' + status if making_progress else '✗ ' + status}")

        if not making_progress and self.config.on_progress_stall:
            self.log("⚠ Calling progress stall handler...")
            try:
                self.config.on_progress_stall(status)
            except Exception as e:
                self.log(f"Error in stall handler: {e}")

        return making_progress

    def run_tier3_gc_and_success(self):
        """
        Tier 3: Garbage collection and success handling.

        Checks:
        - Success detection
        - Process age (zombie detection)
        - Calls on_success callback if configured
        """
        self.log("=" * 70)
        self.log("TIER 3: GC & Success Handler")
        self.log("=" * 70)

        # Check for success
        if self.check_success():
            self.log("🎉 SUCCESS detected")

            # Kill worker
            process_running, pid = self.is_process_running()
            if process_running and pid:
                subprocess.run(['kill', str(pid)], timeout=5)
                self.log(f"✓ Killed worker (PID {pid})")

            # Call success handler
            if self.config.on_success:
                try:
                    self.config.on_success()
                except Exception as e:
                    self.log(f"Error in success handler: {e}")

            return True

        # Check process age (zombie detection)
        process_running, pid = self.is_process_running()
        if process_running and pid:
            try:
                with open(f'/proc/{pid}/stat', 'r') as f:
                    stat = f.read()
                starttime = int(stat.split()[22])
                uptime = float(subprocess.run(['cat', '/proc/uptime'], capture_output=True, text=True).stdout.split()[0])
                boot_time = time.time() - uptime
                hz = os.sysconf('SC_CLK_TCK')
                proc_start = boot_time + (starttime / hz)
                age_hours = (time.time() - proc_start) / 3600

                self.log(f"Worker age: {age_hours:.1f} hours")

                if age_hours > 24:
                    self.log(f"⚠ WARNING: Worker running for {age_hours:.1f} hours")
                    # Optional: Restart old worker
                    # return self.restart_worker()
            except Exception as e:
                self.log(f"Error checking process age: {e}")

        return False
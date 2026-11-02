"""
BaseWorker - Abstract base class for supervised long-running workers.

Any long-running or iterative task inherits from BaseWorker to get:
- Signal handling (SIGTERM, SIGINT)
- Heartbeat mechanism
- Atomic state persistence
- Graceful shutdown
"""

import signal
import time
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class WorkerState:
    """Standardized worker state structure"""
    iteration: int
    status: str  # running, paused, success, error
    last_progress_metric: float
    best_progress_metric: float
    applied_mutations: list[str]
    start_time: float
    last_checkpoint_time: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkerState':
        return cls(**data)


class BaseWorker(ABC):
    """
    Abstract base class for supervised workers.

    Subclasses must implement:
    - run_iteration(): Execute one atomic work unit
    - on_shutdown(): Persist in-flight state before exit
    """

    def __init__(
        self,
        state_file: str,
        heartbeat_file: str,
        heartbeat_interval: int = 30
    ):
        self.state_file = Path(state_file)
        self.heartbeat_file = Path(heartbeat_file)
        self.heartbeat_interval = heartbeat_interval
        self.running = True
        self.last_heartbeat = 0

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Load existing state if available
        self.state = self._load_state()

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.running = False
        self.log(f"Received signal {signum}, shutting down...")
        self.on_shutdown()

    def log(self, message: str):
        """Log to stdout (can be overridden for file logging)"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")

    def update_heartbeat(self):
        """Update heartbeat file"""
        current_time = time.time()
        if current_time - self.last_heartbeat < self.heartbeat_interval:
            return  # Skip if too soon

        with open(self.heartbeat_file, 'w') as f:
            f.write(str(current_time))
        self.last_heartbeat = current_time

    def _load_state(self) -> WorkerState:
        """Load state from file"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                return WorkerState.from_dict(data)
            except Exception as e:
                self.log(f"Error loading state: {e}, starting fresh")
        return WorkerState(
            iteration=0,
            status="running",
            last_progress_metric=0,
            best_progress_metric=0,
            applied_mutations=[],
            start_time=time.time(),
            last_checkpoint_time=0
        )

    def save_state(self):
        """Atomically save state to file"""
        temp_file = self.state_file.with_suffix('.tmp')
        try:
            with open(temp_file, 'w') as f:
                json.dump(self.state.to_dict(), f, indent=2)
            os.replace(temp_file, self.state_file)
            self.state.last_checkpoint_time = time.time()
        except Exception as e:
            self.log(f"Error saving state: {e}")

    def apply_mutation(self, mutation_name: str):
        """Record a mutation/fix application"""
        if mutation_name not in self.state.applied_mutations:
            self.state.applied_mutations.append(mutation_name)
            self.save_state()

    def update_progress(self, progress_metric: float):
        """Update progress metrics"""
        self.state.last_progress_metric = progress_metric
        if progress_metric > self.state.best_progress_metric:
            self.state.best_progress_metric = progress_metric

    def run(self, max_iterations: int = 100):
        """
        Main worker loop.

        This is the standard run loop that:
        1. Checks running flag
        2. Updates heartbeat
        3. Runs one iteration
        4. Saves state
        5. Sleeps briefly
        """
        self.log(f"Worker started (state file: {self.state_file})")
        self.log(f"Resuming from iteration {self.state.iteration}")

        while self.running and self.state.iteration < max_iterations:
            # Update heartbeat
            self.update_heartbeat()

            # Run one iteration
            iteration_start = time.time()
            try:
                self.state.iteration += 1
                self.state.status = "running"

                success = self.run_iteration()

                if success:
                    self.state.status = "success"
                    self.save_state()
                    self.log("🎉 Success achieved, exiting")
                    break
            except Exception as e:
                self.log(f"Error in iteration {self.state.iteration}: {e}")
                self.state.status = "error"
                self.save_state()
                # Continue to next iteration unless critical error
                time.sleep(1)
                continue

            # Save state after iteration
            self.save_state()

            iteration_time = time.time() - iteration_start
            self.log(f"Iteration {self.state.iteration} complete in {iteration_time:.1f}s")

            # Small sleep to prevent CPU spinning
            time.sleep(0.1)

        # Final shutdown
        if not self.running:
            self.log("Worker stopped by signal")
        elif self.state.iteration >= max_iterations:
            self.log(f"Worker stopped after max iterations ({max_iterations})")

    @abstractmethod
    def run_iteration(self) -> bool:
        """
        Run one atomic work unit.

        Returns:
            True: Task completed successfully
            False: Task not yet complete, continue iterating
        """
        pass

    @abstractmethod
    def on_shutdown(self):
        """
        Persist in-flight state before exiting.

        Called when SIGTERM/SIGINT received or before normal exit.
        Subclasses should override to save task-specific state.
        """
        self.save_state()
        self.log("State saved, shutdown complete")
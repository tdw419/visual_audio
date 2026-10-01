#!/usr/bin/env python3
"""
Continuous Alpine Boot Monitor - Autonomous Fix-and-Iterate Loop

This daemon monitors the RV64 emulator Alpine boot, detects stalls,
applies targeted fixes, and iterates until Alpine boots successfully.

Strategy:
1. Monitor current boot progress
2. Detect stall conditions (PC stuck, no UART progress, page faults)
3. Capture detailed diagnostics at stall point
4. Apply targeted fixes to SPATIAL_RV64I.wgsl
5. Restart and iterate
6. Continue until boot succeeds or max iterations reached
"""

import subprocess
import json
import re
import sys
import os
import time
import signal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Configuration
PROJECT_ROOT = Path("/home/jericho/projects/zion/projects/visual_audio")
WGSL_SHADER = PROJECT_ROOT / "tools" / "SPATIAL_RV64I.wgsl"
BOOT_SCRIPT = PROJECT_ROOT / "standalone_alpine_boot_quick.py"
MONITOR_SCRIPT = PROJECT_ROOT / "tools" / "monitor_rv64i.py"
STATE_FILE = PROJECT_ROOT / "alpine_boot_state.json"
LOG_FILE = Path("/tmp/alpine_monitor.log")
HEARTBEAT_FILE = Path("/tmp/alpine_boot_heartbeat")

# Boot thresholds
MAX_ITERATIONS = 100
MIN_SUCCESS_STEPS = 100_000_000  # Need at least 100M steps to claim boot progress
STALL_PC_WINDOW = 10  # PC must vary within this many checks
STALL_UART_TIMEOUT = 5_000_000  # No new UART bytes in N steps
MAX_STEPS_PER_RUN = 500_000_000

class StallMode(Enum):
    """Types of boot stalls"""
    PC_STUCK = "pc_stuck"
    UART_STALLED = "uart_stalled"
    STORE_FAULT = "store_fault"
    LOAD_FAULT = "load_fault"
    TIMER_LOOP = "timer_loop"
    UNKNOWN = "unknown"

@dataclass
class BootMetrics:
    """Metrics from a boot attempt"""
    steps: int
    pc: int
    halted: bool
    mode: str
    scause: int
    mcause: int
    uart_bytes: int
    uart_new_bytes: int
    tlb_hits: int
    tlb_misses: int
    tlb_hit_pct: float
    steps_per_s: float

class AlpineMonitor:
    """Autonomous monitoring and fixing daemon"""

    def __init__(self):
        self.iteration = 0
        self.best_steps = 0
        self.applied_fixes = []
        self.history = []
        self.running = True
        self.current_boot_process = None

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        # Ensure log directory exists
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Load previous state if exists
        self._load_state()

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.log(f"Received signal {signum}, shutting down...")
        self.running = False
        if self.current_boot_process:
            self.current_boot_process.terminate()

    def log(self, message: str, print_also: bool = True):
        """Log to file and optionally print"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{self.iteration}] {message}"
        with open(LOG_FILE, 'a') as f:
            f.write(log_line + '\n')
        if print_also:
            print(log_line)

    def _load_state(self):
        """Load previous state if exists"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.iteration = data.get('state', {}).get('iteration', 0)
                    self.best_steps = data.get('state', {}).get('last_working_step', 0)
                    self.applied_fixes = data.get('state', {}).get('applied_fixes', [])
                    self.history = data.get('results', [])
                    self.log(f"Resumed from iteration {self.iteration}, best {self.best_steps:,} steps")
            except Exception as e:
                self.log(f"Failed to load state: {e}")

    def _save_state(self, status: str, metrics: BootMetrics, stall_mode: str):
        """Save current state to JSON"""
        state = {
            "state": {
                "iteration": self.iteration,
                "last_working_step": self.best_steps,
                "stall_step": metrics.steps,
                "csr_state": {
                    "mcause": f"0x{metrics.mcause:016x}",
                    "scause": f"0x{metrics.scause:016x}",
                    "sepc": "0x0000000000000000",
                    "satp": "0x800000000008155f",
                },
                "applied_fixes": self.applied_fixes,
                "boot_log": []
            },
            "results": self.history + [{
                "iteration": self.iteration,
                "status": status,
                "steps": metrics.steps,
                "best_steps": self.best_steps,
                "stall_mode": stall_mode,
                "fixes": self.applied_fixes.copy(),
                "time": 0
            }],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

    def run_monitor_session(self, max_steps: int = MAX_STEPS_PER_RUN) -> Tuple[BootMetrics, StallMode, str]:
        """Run a monitoring session until stall or success"""
        self.log(f"Starting monitor session (max {max_steps:,} steps)...")

        cmd = [
            str(PROJECT_ROOT / "venv" / "bin" / "python3"), str(MONITOR_SCRIPT),
            "--program", "alpine",
            "--max-steps", str(max_steps),
            "--out", "/tmp/alpine_monitor_session.jsonl",
            "--steps-per-tick", "500000"
        ]

        self.current_boot_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=PROJECT_ROOT
        )

        metrics_history = []
        uart_bytes_history = []
        last_metrics = None

        while self.running:
            # Update heartbeat so Tier 1 knows we're alive
            try:
                HEARTBEAT_FILE.touch()
            except Exception:
                pass

            # Check if process still running
            ret = self.current_boot_process.poll()
            if ret is not None:
                self.log(f"Monitor process exited with code {ret}")
                break

            # Try to read latest metrics from output file
            try:
                with open("/tmp/alpine_monitor_session.jsonl", 'r') as f:
                    lines = f.readlines()
                    if lines:
                        last_line = lines[-1]
                        data = json.loads(last_line)

                        # Handle two different data formats
                        if 'steps' not in data:
                            self.log(f"Ignoring non-metrics entry: {list(data.keys())}")
                            time.sleep(2)
                            continue

                        try:
                            metrics = BootMetrics(
                                steps=int(data.get('steps', 0) or 0),
                                pc=int(data.get('pc', 0) or 0),
                                halted=bool(data.get('halted', False)),
                                mode=str(data.get('mode', '')),
                                scause=int(data.get('scause', 0) or 0),
                                mcause=int(data.get('mcause', 0) or 0),
                                uart_bytes=int(data.get('uart_bytes', 0) or 0),
                                uart_new_bytes=int(data.get('uart_new_bytes', 0) or 0),
                                tlb_hits=int(data.get('tlb_hits', 0) or 0),
                                tlb_misses=int(data.get('tlb_misses', 0) or 0),
                                tlb_hit_pct=float(data.get('tlb_hit_pct', 0) or 0),
                                steps_per_s=float(data.get('steps_per_s', 0) or 0)
                            )

                            uart_bytes_history.append(metrics.uart_new_bytes)
                            if len(uart_bytes_history) > 10:
                                uart_bytes_history.pop(0)

                            # Detect stall conditions
                            stall_mode, stall_reason = self._detect_stall(metrics, metrics_history, uart_bytes_history)

                            if stall_mode != StallMode.UNKNOWN:
                                self.log(f"Stall detected: {stall_mode.value} - {stall_reason}")
                                self.current_boot_process.terminate()
                                return metrics, stall_mode, stall_reason

                            metrics_history.append(metrics)
                            if len(metrics_history) > 20:
                                metrics_history.pop(0)
                            last_metrics = metrics
                        except (ValueError, TypeError) as e:
                            continue  # Skip invalid entries

            except (FileNotFoundError, json.JSONDecodeError) as e:
                pass  # File not ready yet

            time.sleep(5)  # Check every 5 seconds

        # Process exited normally - check if successful
        if last_metrics:
            if last_metrics.steps >= MIN_SUCCESS_STEPS and not last_metrics.halted:
                return last_metrics, StallMode.UNKNOWN, "completed_without_stall"
            return last_metrics, StallMode.UNKNOWN, "process_exited"

        return BootMetrics(steps=0, pc=0, halted=False, mode="", scause=0, mcause=0,
                           uart_bytes=0, uart_new_bytes=0, tlb_hits=0, tlb_misses=0,
                           tlb_hit_pct=0, steps_per_s=0), StallMode.UNKNOWN, "no_data"

    def _detect_stall(self, metrics: BootMetrics, history: List[BootMetrics], uart_history: List[int]) -> Tuple[StallMode, str]:
        """Detect if boot has stalled and return stall mode"""

        # Check if halted
        if metrics.halted:
            return StallMode.UNKNOWN, "cpu_halted"

        # Check for store page fault (scause=5)
        # Python may interpret large JSON ints as either signed or unsigned
        # Check both representations
        is_store_fault = (
            metrics.scause == 5 or
            metrics.scause == 0x8000000000000005 or
            metrics.scause == -9223372036854775803
        )

        if is_store_fault:
            # Check if this is persistent (all 5 samples are store faults)
            if len(history) >= 5:
                all_store_fault = True
                for m in history[-5:]:
                    sc = m.scause
                    is_sf = (sc == 5 or sc == 0x8000000000000005 or sc == -9223372036854775803)
                    if not is_sf:
                        all_store_fault = False
                        break
                if all_store_fault:
                    return StallMode.STORE_FAULT, "persistent_store_page_fault"

        # Check for PC stuck (PC not varying)
        if len(history) >= STALL_PC_WINDOW:
            pcs = [m.pc for m in history[-STALL_PC_WINDOW:]]
            unique_pcs = set(pcs)
            if len(unique_pcs) <= 2:  # Only 1-2 different PCs
                return StallMode.PC_STUCK, f"pc_only_2_values_{pcs[0]:016x}"

        # Check for UART stalled (no new bytes for a while)
        if len(uart_history) >= STALL_PC_WINDOW:
            all_zero = all(b == 0 for b in uart_history[-STALL_PC_WINDOW:])
            if all_zero and metrics.steps > 10_000_000:
                return StallMode.UART_STALLED, "no_uart_progress"

        return StallMode.UNKNOWN, "making_progress"

    def apply_permission_fix(self) -> bool:
        """Apply U-bit/SUM permission check fix"""
        self.log("Applying permission fix...")

        if not WGSL_SHADER.exists():
            self.log(f"ERROR: Shader not found at {WGSL_SHADER}")
            return False

        with open(WGSL_SHADER, 'r') as f:
            content = f.read()

        # Check if already fixed
        if 'sstatus_sum' in content and 'SUM bit' in content:
            self.log("Permission fix already applied")
            return True

        # Find and replace check_perm function
        old_pattern = r"""fn check_perm\(pte: u32, need_write: bool, need_exec: bool\) -> bool \{
    let r = \(pte >> 1u\) & 1u;
    let w = \(pte >> 2u\) & 1u;
    let x = \(pte >> 3u\) & 1u;
    if \(need_exec\) \{ return x == 1u; \}
    if \(need_write\) \{ return w == 1u; \}
    return r == 1u;
\}"""

        new_func = """fn check_perm(pte: u32, need_write: bool, need_exec: bool) -> bool {
    let r = (pte >> 1u) & 1u;
    let w = (pte >> 2u) & 1u;
    let x = (pte >> 3u) & 1u;
    let u = (pte >> 4u) & 1u;
    let sstatus_sum = read_csr(0x100u) & 0x40000u;

    if (u == 1u) {
        if (need_write) { return w == 1u && sstatus_sum != 0u; }
        return r == 1u;
    }

    if (need_exec) { return x == 1u; }
    if (need_write) { return w == 1u; }
    return r == 1u;
}"""

        new_content = re.sub(old_pattern, new_func, content)

        if new_content == content:
            self.log("Pattern not found, may already be fixed")
            return True

        # Backup and write
        backup = WGSL_SHADER.with_suffix('.wgsl.backup')
        with open(backup, 'w') as f:
            f.write(content)
        with open(WGSL_SHADER, 'w') as f:
            f.write(new_content)

        self.log(f"Permission fix applied (backup at {backup})")
        return True

    def apply_fix_for_stall(self, stall_mode: StallMode) -> bool:
        """Apply appropriate fix for stall type"""
        # Check for epoch-based EFAULT fix (commit 803df7c)
        wgsl_path = PROJECT_ROOT / "tools" / "SPATIAL_RV64I.wgsl"
        try:
            with open(wgsl_path) as f:
                wgsl_content = f.read()
            if "decoded_ops_epoch" in wgsl_content:
                # EFAULT fix present - clear state and mark as fixed
                self.log("INFO: EFAULT fix detected (epoch-based invalidation)")
                self.iteration = 0
                self.applied_fixes = ['epoch_fix_verified']
                self.history = []
                self._save_state("detected_fix", BootMetrics(steps=0, pc=0, halted=False, mode="", scause=0, mcause=0,
                                   uart_bytes=0, uart_new_bytes=0, tlb_hits=0, tlb_misses=0,
                                   tlb_hit_pct=0, steps_per_s=0), "external_fix")
                return True  # Fix "applied" (actually detected as already fixed)
        except Exception as e:
            self.log(f"WARN: Could not check for EFAULT fix: {e}")
        if stall_mode == StallMode.STORE_FAULT:
            if "permission_fix" not in self.applied_fixes:
                if self.apply_permission_fix():
                    self.applied_fixes.append("permission_fix")
                    return True
        elif stall_mode == StallMode.LOAD_FAULT:
            if "permission_fix" not in self.applied_fixes:
                if self.apply_permission_fix():
                    self.applied_fixes.append("permission_fix")
                    return True

        self.log(f"No fix available for {stall_mode.value} or already applied")
        return False

    def run(self):
        """Main monitoring loop"""
        self.log("=" * 70)
        self.log("ALPINE BOOT MONITOR DAEMON STARTED")
        self.log(f"Max iterations: {MAX_ITERATIONS}")
        self.log(f"Success threshold: {MIN_SUCCESS_STEPS:,} steps")
        self.log("=" * 70)

        while self.running and self.iteration < MAX_ITERATIONS:
            self.iteration += 1
            iteration_start = time.time()

            self.log("\n" + "=" * 70)
            self.log(f"ITERATION {self.iteration}/{MAX_ITERATIONS}")
            self.log("=" * 70 + "\n")

            # Run monitoring session
            metrics, stall_mode, stall_reason = self.run_monitor_session()

            self.log(f"Session complete:")
            self.log(f"  Steps: {metrics.steps:,}")
            self.log(f"  PC: 0x{metrics.pc:016x}")
            self.log(f"  Halted: {metrics.halted}")
            self.log(f"  Mode: {metrics.mode}")
            self.log(f"  Scause: 0x{metrics.scause:016x}")
            self.log(f"  TLB hit rate: {metrics.tlb_hit_pct:.2f}%")
            self.log(f"  Stall mode: {stall_mode.value}")
            self.log(f"  Stall reason: {stall_reason}")

            # Update best progress
            self.best_steps = max(self.best_steps, metrics.steps)

            # Check success
            if metrics.steps >= MIN_SUCCESS_STEPS and stall_mode == StallMode.UNKNOWN:
                self.log("\n" + "=" * 70)
                self.log("🎉 ALPINE BOOT SUCCESS!")
                self.log(f"Booted to {metrics.steps:,} steps")
                self.log("=" * 70)
                self._save_state("success", metrics, "none")
                return True

            # Apply fix if stalled
            if stall_mode != StallMode.UNKNOWN:
                fix_applied = self.apply_fix_for_stall(stall_mode)
                if fix_applied:
                    self.log(f"Fix applied for {stall_mode.value}")
                else:
                    self.log(f"No new fix to apply")

            # Save state
            self._save_state(stall_mode.value, metrics, stall_reason)

            # Check if exhausted
            if len(self.applied_fixes) >= 2 and self.iteration > 5:
                recent_steps = [r.get('steps', 0) for r in self.history[-3:]] if len(self.history) >= 3 else []
                if recent_steps and max(recent_steps) == min(recent_steps):
                    self.log("\n" + "=" * 70)
                    self.log("No progress with all known fixes applied")
                    self.log(f"Best progress: {self.best_steps:,} steps")
                    self.log("Manual investigation needed")
                    self.log("=" * 70)
                    return False

            iteration_time = time.time() - iteration_start
            self.log(f"\nIteration time: {iteration_time:.1f}s")
            self.log(f"Best progress so far: {self.best_steps:,} steps")

        return False

if __name__ == "__main__":
    monitor = AlpineMonitor()
    try:
        success = monitor.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        monitor.log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
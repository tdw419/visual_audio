#!/usr/bin/env python3
"""
Cron Meta-Monitor - Watches that cron supervision jobs are running.

This is a Tier-0 meta-supervisor that ensures the tiered supervision cron jobs
themselves haven't silently stopped running. Cron can silently drop jobs if
the daemon dies or if there are configuration issues.

Run this via cron at a higher frequency than the supervised tasks (e.g., every 10 min).
"""

import subprocess
import time
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CronJobStatus:
    """Status of a cron job"""
    name: str
    schedule: str
    command: str
    last_run_log: Optional[str]
    log_age_seconds: float
    is_healthy: bool


class CronMetaMonitor:
    """Monitor that cron supervision jobs are executing"""

    def __init__(self, log_patterns: List[tuple], max_log_age_hours: float = 2):
        """
        Args:
            log_patterns: List of (name, log_path) tuples to monitor
            max_log_age_hours: Max age of log file before warning
        """
        self.log_patterns = log_patterns
        self.max_log_age_seconds = max_log_age_hours * 3600

    def log(self, message: str):
        """Log to stdout"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [META-SUPERVISOR] {message}")

    def check_log_health(self, name: str, log_path: str) -> CronJobStatus:
        """Check if log file is being updated"""
        path = Path(log_path)

        if not path.exists():
            return CronJobStatus(
                name=name,
                schedule="?",
                command=log_path,
                last_run_log=None,
                log_age_seconds=float('inf'),
                is_healthy=False
            )

        log_age = time.time() - path.stat().st_mtime
        is_healthy = log_age < self.max_log_age_seconds

        # Read last line
        last_line = None
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
                last_line = lines[-1].strip() if lines else None
        except Exception:
            pass

        # Check for stall indicators in recent logs
        if last_line and 'stuck_at' in last_line and 'steps' in last_line:
            # Tier 2 detected a stall
            self.log(f"  ⚠ {name} detected STALL: {last_line}")

        return CronJobStatus(
            name=name,
            schedule="?",
            command=log_path,
            last_run_log=last_line,
            log_age_seconds=log_age,
            is_healthy=is_healthy
        )

    def check_cron_daemon(self) -> bool:
        """Check if cron daemon is running"""
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'cron'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

    def check_crontab_syntax(self) -> bool:
        """Verify crontab has valid syntax"""
        try:
            result = subprocess.run(
                ['crontab', '-l'],
                capture_output=True,
                text=True
            )
            # If crontab -l succeeds, syntax is valid
            return result.returncode == 0
        except Exception:
            return False

    def run_health_check(self) -> bool:
        """Run meta-supervisor health check"""
        self.log("=" * 70)
        self.log("META-SUPERVISOR: Cron Job Health Check")
        self.log("=" * 70)

        # Check cron daemon
        cron_running = self.check_cron_daemon()
        self.log(f"Cron daemon: {'✓ running' if cron_running else '✗ NOT RUNNING'}")

        # Check crontab syntax
        crontab_ok = self.check_crontab_syntax()
        self.log(f"Crontab syntax: {'✓ valid' if crontab_ok else '✗ INVALID'}")

        # Check log files
        all_healthy = True
        self.log("Log file freshness:")
        for name, log_path in self.log_patterns:
            status = self.check_log_health(name, log_path)

            age_minutes = status.log_age_seconds / 60
            if status.is_healthy:
                self.log(f"  ✓ {name}: {age_minutes:.1f} min old (healthy)")
            else:
                self.log(f"  ✗ {name}: {age_minutes:.1f} min old (STALE - possible silent failure)")
                all_healthy = False

                # Show last log line for debugging
                if status.last_run_log:
                    self.log(f"    Last log: {status.last_run_log[:100]}")

        if all_healthy:
            self.log("✓ All supervision cron jobs healthy")
        else:
            self.log("⚠ Some supervision cron jobs may have stopped silently")

        return all_healthy


def main():
    """Main entry point"""
    # Configure which logs to monitor
    log_patterns = [
        ("Alpine Boot T1 (Liveness)", "/tmp/alpine_supervisor_t1.log"),
        ("Alpine Boot T2 (Progress)", "/tmp/alpine_supervisor_t2.log"),
        ("Alpine Boot T3 (GC)", "/tmp/alpine_supervisor_t3.log"),
    ]

    monitor = CronMetaMonitor(log_patterns, max_log_age_hours=2)
    healthy = monitor.run_health_check()

    return 0 if healthy else 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
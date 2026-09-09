#!/usr/bin/env python3
"""
supervisor-cli - CLI tool for tiered supervision of supervised workers.

Usage:
    supervisor-cli check-liveness --config task_spec.json
    supervisor-cli audit-progress --config task_spec.json
    supervisor-cli sweep-and-report --config task_spec.json
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Tuple, Callable

# Add project tools to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from supervisor_engine import SupervisorEngine, SupervisorConfig


# Alpine Boot Progress Validator
def alpine_boot_progress_validator(state: dict) -> Tuple[bool, str]:
    """
    Validate Alpine boot monitor progress.

    The supervisor engine passes the loaded state dict directly.
    Reads monitor state and checks:
    - Recent iterations are making SUCCESSFUL forward progress
    - No significant regressions
    - No stall loops of failures at same barrier
    """
    # State dict is already loaded by the engine
    if not state:
        return True, "no_monitor_state_yet"

    results = state.get('results', [])
    if not results:
        return True, "no_results_yet"

    # Get recent results (last 5)
    recent_results = results[-5:] if len(results) >= 5 else results

    if len(recent_results) < 2:
        return True, "insufficient_history"

    # Check 1: Stall loop - same failure mode repeating?
    stall_modes = [r.get('stall_mode', 'unknown') for r in recent_results]
    if len(stall_modes) >= 5 and len(set(stall_modes)) == 1:
        mode = list(set(stall_modes))[0]
        steps = recent_results[-1].get('steps', 0)
        return False, f"stall_loop_{mode}_5x_at_{steps:,}_steps"

    # Check 2: Is LAST iteration successful?
    last_result = recent_results[-1]
    last_status = last_result.get('status', '')

    # Successful = status is NOT one of the failure modes
    failure_modes = {'uart_stalled', 'pc_stuck', 'store_fault', 'timeout'}
    if last_status in failure_modes:
        steps = last_result.get('steps', 0)
        best = last_result.get('best_steps', 0)
        return False, f"failed_at_{steps:,}_steps ({last_status})_best_was_{best:,}"

    # Check 3: Forward progress in successful iterations?
    successful_results = [r for r in recent_results if r.get('status') not in failure_modes]
    if len(successful_results) >= 2:
        successful_steps = [r.get('steps', 0) for r in successful_results]
        if successful_steps[-1] <= successful_steps[0]:
            return False, f"no_successful_progress_{successful_steps[-1]:,}_steps"

    # Check 4: Significant regression in current iteration?
    best_steps_list = [r.get('best_steps', 0) for r in recent_results]
    current_best = best_steps_list[-1]
    previous_best = max(best_steps_list[:-1]) if len(best_steps_list) > 1 else 0

    current_steps = recent_results[-1].get('steps', 0)
    if current_steps < current_best * 0.5:
        return False, f"regression_{current_steps:,}v{current_best:,}"

    return True, f"progressing_to_{current_best:,}_steps"


def alpine_boot_success_detector(state: dict) -> bool:
    """
    Detect if Alpine boot has succeeded (100M+ steps).

    The supervisor engine passes the loaded state dict directly.
    """
    if not state:
        return False

    state_data = state.get('state', {})
    return state_data.get('last_working_step', 0) >= 100_000_000


def load_config(config_file: str) -> tuple:
    """
    Load task specification from JSON config.
    """
    with open(config_file, 'r') as f:
        config_data = json.load(f)

    return (
        config_data.get('worker_cmd', []),
        config_data.get('state_file', ''),
        config_data.get('heartbeat_file', ''),
        config_data.get('supervisor_state_file', ''),
        config_data
    )


def main():
    parser = argparse.ArgumentParser(description='Supervise long-running workers')
    subparsers = parser.add_subparsers(dest='command', help='Supervision tier')

    # Tier 1: Watchdog
    parser_watchdog = subparsers.add_parser('check-liveness', help='Fast crash detection')
    parser_watchdog.add_argument('--config', required=True, help='Task specification JSON')

    # Tier 2: Progress auditor
    parser_progress = subparsers.add_parser('audit-progress', help='Progress verification')
    parser_progress.add_argument('--config', required=True, help='Task specification JSON')

    # Tier 3: GC and success handler
    parser_gc = subparsers.add_parser('sweep-and-report', help='Garbage collection and success')
    parser_gc.add_argument('--config', required=True, help='Task specification JSON')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load configuration
    try:
        worker_cmd, state_file, heartbeat_file, supervisor_state_file, config_data = load_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    # Build supervisor config with progress/success evaluators
    supervisor_config = SupervisorConfig(
        max_heartbeat_age=config_data.get('max_heartbeat_age', 120),
        max_restart_backoff=config_data.get('max_restart_backoff', 300),
        max_restarts_per_hour=config_data.get('max_restarts_per_hour', 6),
        progress_evaluator=alpine_boot_progress_validator,
        success_evaluator=alpine_boot_success_detector
    )

    # Create engine
    engine = SupervisorEngine(
        worker_cmd=worker_cmd,
        state_file=state_file,
        heartbeat_file=heartbeat_file,
        supervisor_state_file=supervisor_state_file,
        config=supervisor_config
    )

    # Run appropriate tier
    if args.command == 'check-liveness':
        success = engine.run_tier1_watchdog()
        sys.exit(0 if success else 1)

    elif args.command == 'audit-progress':
        success = engine.run_tier2_progress_auditor()
        sys.exit(0 if success else 1)

    elif args.command == 'sweep-and-report':
        success = engine.run_tier3_gc_and_success()
        sys.exit(0 if success else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
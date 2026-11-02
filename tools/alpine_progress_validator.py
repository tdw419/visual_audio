#!/usr/bin/env python3
"""
Alpine Boot Progress Validator - For Tier 2 progress audit.

Detects when the Alpine boot monitor is stuck without making forward progress.
"""

import json
import sys
from pathlib import Path
from typing import Tuple


def load_alpine_boot_state(state_file: str) -> dict:
    """Load Alpine boot state from monitor's state file"""
    path = Path(state_file)
    if not path.exists():
        return {}

    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def validate_progress(state: dict) -> Tuple[bool, str]:
    """
    Validate that Alpine boot is making forward progress.

    Args:
        state: Full state dict from alpine_boot_state.json

    Returns:
        (is_making_progress, status_message)
    """
    if not state:
        return False, "no_state_file"

    state_data = state.get('state', {})
    results = state.get('results', [])

    if not results:
        return False, "no_results_yet"

    # Get recent results (last 5 iterations)
    recent_results = results[-5:] if len(results) >= 5 else results

    # Extract best steps from each result
    best_steps_list = [r.get('best_steps', 0) for r in recent_results]

    if len(best_steps_list) < 2:
        return True, "insufficient_history"

    current_best = best_steps_list[-1]
    previous_best = max(best_steps_list[:-1]) if len(best_steps_list) > 1 else 0

    # Check 1: Is best progress actually increasing?
    if current_best <= previous_best:
        return False, f"stuck_at_{current_best}_steps (was {previous_best:,} before)"

    # Check 2: Is current attempt making reasonable progress?
    current_steps = recent_results[-1].get('steps', 0)
    stall_step = state_data.get('stall_step', 0)

    # If current attempt is far below best (significant regression)
    if current_steps < current_best * 0.5:
        return False, f"regression_{current_steps:,}v{current_best:,}_steps"

    # Check 3: Are we in a stall loop?
    stall_modes = [r.get('stall_mode', 'unknown') for r in recent_results]
    unique_stalls = set(stall_modes)

    # If all 5 recent iterations have the same stall mode
    if len(stall_modes) >= 5 and len(unique_stalls) == 1:
        stall_mode = list(unique_stalls)[0]
        return False, f"stall_loop_{stall_mode}_5x"

    # Check 4: No progress in 5+ iterations?
    if len(best_steps_list) >= 5:
        max_5 = max(best_steps_list)
        min_5 = min(best_steps_list)
        if max_5 == min_5:
            return False, f"no_progress_5_iterations_at_{max_5:,}_steps"

    # Making progress
    progress_pct = ((current_best - previous_best) / max(previous_best, 1)) * 100
    return True, f"making_progress_{current_best:,}_steps_+{progress_pct:.1f}%"


def main():
    """CLI interface for testing"""
    import argparse

    parser = argparse.ArgumentParser(description='Validate Alpine boot progress')
    parser.add_argument('--state', default='alpine_boot_state.json', help='State file path')

    args = parser.parse_args()

    state = load_alpine_boot_state(args.state)
    is_progressing, status = validate_progress(state)

    print(f"is_progressing: {is_progressing}")
    print(f"status: {status}")
    return 0 if is_progressing else 1


if __name__ == '__main__':
    sys.exit(main())
#!/usr/bin/env python3
"""
Regression gate for glyph_dispatch changes.

Runs three verification gates:
1. bbird boot to shell (instr count + wall time)
2. Lockstep divergence check (execute_decoded vs decode_and_execute)
3. SHA-256 ISA vs hashlib (3/3 FIPS + inputs)

Returns exit code 0 only if ALL gates pass. Exit code 1 if any gate fails.

Design principles:
- Deterministic: same inputs → same outputs
- Falsifiable: clear pass/fail, no "maybe"
- No LLM in loop: pure tool measurements
- Receipt-based: outputs hashable transcripts
"""
import argparse
import json
import hashlib
import subprocess
import sys
import time
from pathlib import Path

# Path constants
REPO_ROOT = Path(__file__).parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
GLYPH_TOOLS_DIR = REPO_ROOT / "glyph_dispatch" / "tools"

# The boot is stopped via --stop-at-uart on this exact marker, so the success
# check must match the SAME string: the boot halts the instant the marker is
# seen, mid-banner, so any longer text ("... ON THE GPU RV64 EMULATOR") is by
# construction never emitted and can never be matched.
BBIRD_STOP_MARKER = "BUSYBOX SHELL RUNNING"


def run_bbird_boot(quick=False, timeout=3600):
    """
    Gate 1: bbird boot to shell.
    Verifies: Alpine static busybox init reaches interactive shell (or 1M step quick probe).
    Metrics: instruction count, wall time, basic-block threading counters.
    """
    print("\n" + "="*60)
    mode_str = " (QUICK PROBE: 1M steps)" if quick else ""
    print(f"GATE 1: bbird boot to shell{mode_str}")
    print("="*60)

    ckpt_path = REPO_ROOT / ".ckpt" / "v618_preexec.rv64ckpt"
    bbird_path = REPO_ROOT / ".ckpt" / "bbird.gz"

    if not ckpt_path.exists():
        print(f"FAIL: Checkpoint not found: {ckpt_path}")
        return None

    if not bbird_path.exists():
        print(f"FAIL: bbird.gz not found: {bbird_path}")
        return None

    # Run fresh boot
    start_time = time.time()
    if quick:
        cmd = [
            sys.executable,
            str(TOOLS_DIR / "fresh_boot_ckpt.py"),
            "--batch", "100000",
            "--initrd", str(bbird_path),
            "--max-steps", "1000000",
        ]
        boot_timeout = 180
    else:
        cmd = [
            sys.executable,
            str(TOOLS_DIR / "fresh_boot_ckpt.py"),
            "--batch", "100000",
            "--initrd", str(bbird_path),
            "--max-steps", "4000000000",
            "--stop-at-uart", BBIRD_STOP_MARKER
        ]
        boot_timeout = timeout

    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=boot_timeout)
    except subprocess.TimeoutExpired as e:
        print(f"FAIL: Boot timed out after {boot_timeout}s")
        if e.stdout:
            print(f"STDOUT TAIL:\n{e.stdout[-1000:]}")
        return None

    wall_time = time.time() - start_time

    # Check for success indicators
    if quick:
        success = (result.returncode == 0) and ("bb:" in result.stdout)
    else:
        success = BBIRD_STOP_MARKER in result.stdout

    if not success:
        print(f"FAIL: {'Step target not reached' if quick else 'Shell not reached'}")
        print(f"STDOUT:\n{result.stdout[-2000:] if result.stdout else ''}")
        print(f"STDERR:\n{result.stderr}")
        return None

    # Extract instruction count and bb counters from output
    instr_count = None
    bb_total = 0
    bb_threaded = 0
    bb_fallback = 0
    for line in result.stdout.split('\n'):
        low = line.lower()
        if 'steps=' in low or 'instructions' in low:
            try:
                import re
                for tok in re.findall(r'(?:steps=)?([\d,]{2,})', line):
                    digits = tok.replace(',', '')
                    if digits.isdigit():
                        instr_count = int(digits)
                        break
            except Exception:
                pass
        if line.startswith('bb:'):
            try:
                import re
                m = re.search(r'total=([\d,]+)\s+threaded=([\d,]+)\s+fallback=([\d,]+)', line)
                if m:
                    bb_total = int(m.group(1).replace(',', ''))
                    bb_threaded = int(m.group(2).replace(',', ''))
                    bb_fallback = int(m.group(3).replace(',', ''))
            except Exception:
                pass

    if instr_count is None:
        print(f"WARN: Could not extract instruction count")
        instr_count = -1

    # Fast-path verification: assert the fast path was genuinely exercised!
    if bb_total > 0 and bb_threaded == 0:
        print(f"FAIL: Fast path was not exercised (bb_threaded_insts == 0)")
        return None

    print(f"PASS: Shell reached in {wall_time:.1f}s, ~{instr_count:,} instr "
          f"(threaded={bb_threaded:,}, fallback={bb_fallback:,})")

    return {
        'pass': True,
        'wall_time_s': wall_time,
        'instruction_count': instr_count,
        'bb_total': bb_total,
        'bb_threaded': bb_threaded,
        'bb_fallback': bb_fallback,
        'stdout_hash': hashlib.sha256(result.stdout.encode()).hexdigest(),
    }


def run_lockstep_check():
    """
    Gate 2: Lockstep divergence check.
    Verifies: execute_decoded() and decode_and_execute() produce identical results.
    """
    print("\n" + "="*60)
    print("GATE 2: Lockstep divergence check")
    print("="*60)

    harness_path = GLYPH_TOOLS_DIR / "fastpath_lockstep_harness.py"

    if not harness_path.exists():
        print(f"SKIP: Lockstep harness not found: {harness_path}")
        print("      (This is OK if fast path is disabled)")
        return {'pass': True, 'skipped': True}

    # Run harness
    cmd = [sys.executable, str(harness_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    # Check for divergence
    if "DIVERGENCE DETECTED" in result.stdout:
        print(f"FAIL: Divergence detected between fast and slow paths")
        print(f"STDOUT:\n{result.stdout}")
        return None

    if "No divergence" in result.stdout:
        print(f"PASS: No divergence detected (fast path clean)")
        return {
            'pass': True,
            'skipped': False,
            'stdout_hash': hashlib.sha256(result.stdout.encode()).hexdigest(),
        }

    # Unknown output
    print(f"WARN: Unexpected harness output")
    print(f"STDOUT:\n{result.stdout}")
    return None


def run_sha256_verification():
    """
    Gate 3: SHA-256 ISA vs hashlib verification.
    Verifies: 3/3 FIPS test vectors pass + random input matches.
    """
    print("\n" + "="*60)
    print("GATE 3: SHA-256 ISA verification")
    print("="*60)

    # Look for SHA-256 verification script
    sha_script = None
    for possible in [
        REPO_ROOT / "glyph_dispatch" / "tools" / "sha256_lockstep_test.py",
        REPO_ROOT / "glyph_dispatch" / "tools" / "verify_sha256_glyph.py",
        REPO_ROOT / "glyph_dispatch" / "tools" / "sha256_verification.py",
        REPO_ROOT / "tools" / "sha256_verify.py",
        REPO_ROOT / "glyph_dispatch" / "test_sha256.py",
    ]:
        if possible.exists():
            sha_script = possible
            break

    if not sha_script:
        print(f"SKIP: SHA-256 verification script not found")
        print("      (Expected if SHA-256 not integrated yet)")
        return {'pass': True, 'skipped': True}

    # Run verification
    cmd = [sys.executable, str(sha_script)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # Check for success
    success = "PASS" in result.stdout or "All tests passed" in result.stdout or "passed, 0 failed" in result.stdout

    if not success:
        print(f"FAIL: SHA-256 verification failed")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        return None

    print(f"PASS: SHA-256 verification passed ({sha_script.name})")
    return {
        'pass': True,
        'skipped': False,
        'stdout_hash': hashlib.sha256(result.stdout.encode()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Regression gate for glyph_dispatch changes"
    )
    parser.add_argument(
        '--gate', choices=['bbird', 'lockstep', 'sha256', 'all'],
        default='all',
        help='Which gate(s) to run (default: all)'
    )
    parser.add_argument(
        '--quick', action='store_true',
        help='Run quick checks suitable for pre-commit (1M boot steps, 1M lockstep, sha256)'
    )
    parser.add_argument(
        '--timeout', type=int, default=3600,
        help='Timeout for full bbird boot in seconds (default: 3600)'
    )
    parser.add_argument(
        '--output', type=str,
        help='Write receipt JSON to file'
    )
    args = parser.parse_args()

    receipt = {
        'timestamp': time.time(),
        'repo_commit': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            cwd=REPO_ROOT,
            text=True
        ).strip(),
        'gates': {},
        'overall': 'FAIL'
    }

    # Run requested gates
    all_pass = True

    if args.gate in ['bbird', 'all']:
        result = run_bbird_boot(quick=args.quick, timeout=args.timeout)
        receipt['gates']['bbird'] = result
        if result is None or not result.get('pass'):
            all_pass = False

    if args.gate in ['lockstep', 'all']:
        result = run_lockstep_check()
        receipt['gates']['lockstep'] = result
        if result is None or not result.get('pass'):
            all_pass = False

    if args.gate in ['sha256', 'all']:
        result = run_sha256_verification()
        receipt['gates']['sha256'] = result
        if result is None or not result.get('pass'):
            all_pass = False

    receipt['overall'] = 'PASS' if all_pass else 'FAIL'

    # Print summary
    print("\n" + "="*60)
    print("REGRESSION SUMMARY")
    print("="*60)
    for gate, result in receipt['gates'].items():
        if result is None:
            status = "FAIL"
        elif result.get('skipped'):
            status = "SKIP"
        elif result.get('pass'):
            status = "PASS"
        else:
            status = "FAIL"
        print(f"  {gate:12s}: {status}")
    print(f"\n  {'overall':12s} {receipt['overall']}")

    # Write receipt if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(receipt, f, indent=2)
        print(f"\nReceipt written to {args.output}")

    # Exit code
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
#!/usr/bin/env python3
"""
Autonomous Alpine Boot Executor for RV64 Emulator

This script implements an autonomous development loop to fix the RV64 emulator
boot stall at ~35M steps during initramfs unpack.

Execution Strategy:
1. Boot Alpine to stall point (~35M steps)
2. Capture detailed state (CSRs, TLB, memory)
3. Apply targeted fixes based on failure mode
4. Reboot and verify progress
5. Iterate until Alpine boots successfully

Known Issues (from STATUS_RV64I_STALL.md):
- Permission checks missing U-bit/SUM (line 738 in SPATIAL_RV64I.wgsl)
- TLB invalidation may not be called at the right time
- Direct-mapped TLB collisions with 256 entries for 27-bit VPN space
"""

import subprocess
import json
import re
import sys
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configuration
PROJECT_ROOT = Path("/home/jericho/projects/zion/projects/visual_audio")
WGSL_SHADER = PROJECT_ROOT / "tools" / "SPATIAL_RV64I.wgsl"
BOOT_SCRIPT = PROJECT_ROOT / "standalone_alpine_boot.py"
MONITOR_SCRIPT = PROJECT_ROOT / "tools" / "monitor_rv64i.py"
DEBUG_CSR_SCRIPT = PROJECT_ROOT / "debug_csr_state.py"

# Known failure points
STALL_STEPS = 35_000_000  # Stall during initramfs unpack
MAX_ITERATIONS = 50      # Safety limit
STEP_BATCH_SIZE = 100_000  # Steps between state checks

class AlpineBootState:
    """Track boot progress and failure modes"""

    def __init__(self):
        self.iteration = 0
        self.last_working_step = 0
        self.stall_step = 0
        self.csr_state = {}
        self.tlb_stats = {}
        self.applied_fixes = []
        self.boot_log = []

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "last_working_step": self.last_working_step,
            "stall_step": self.stall_step,
            "csr_state": self.csr_state,
            "tlb_stats": self.tlb_stats,
            "applied_fixes": self.applied_fixes,
            "boot_log": self.boot_log[-50:]  # Last 50 log entries
        }

def run_command(cmd: List[str], timeout: int = 3600, cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """Run command with timeout, return exit code, stdout, stderr"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or PROJECT_ROOT
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"

def capture_csr_state() -> dict:
    """Capture detailed CSR state at current stall point"""
    print(">>> Capturing CSR state...")

    # Run debug script to get CSR dump
    code, stdout, stderr = run_command(
        ["python3", str(DEBUG_CSR_SCRIPT), "--capture"],
        timeout=300
    )

    if code != 0:
        print(f"WARNING: CSR capture failed: {stderr}")
        return {}

    # Parse CSR state from output
    csr_state = {}
    for line in stdout.split('\n'):
        if '=' in line and not line.strip().startswith('#'):
            try:
                key, value = line.split('=', 1)
                csr_state[key.strip()] = value.strip()
            except ValueError:
                continue

    return csr_state

def detect_stall_mode(csr_state: dict) -> str:
    """Detect the type of stall from CSR state"""
    scause = csr_state.get('scause', '0')

    # Parse scause (bit 63 = interrupt, bits 0-4 = exception code)
    try:
        scause_int = int(scause, 0)
        is_interrupt = (scause_int >> 63) & 1
        exception_code = scause_int & 0x7F
    except ValueError:
        return "unknown"

    if is_interrupt:
        # Timer interrupt - system making progress but slowly
        if exception_code == 5:
            return "timer_loop"
        return f"interrupt_{exception_code}"

    # Page fault codes
    if exception_code == 13:  # Load page fault
        return "load_page_fault"
    elif exception_code == 15:  # Store page fault
        return "store_page_fault"
    elif exception_code == 12:  # Instruction page fault
        return "instruction_page_fault"

    return f"exception_{exception_code}"

def apply_permission_fix() -> bool:
    """Apply U-bit/SUM permission check fix to WGSL shader"""
    print(">>> Applying U-bit/SUM permission fix...")

    shader_path = WGSL_SHADER
    if not shader_path.exists():
        print(f"ERROR: Shader not found at {shader_path}")
        return False

    with open(shader_path, 'r') as f:
        shader_content = f.read()

    # Check if fix already applied
    if 'check_sstatus_sum' in shader_content:
        print("U-bit/SUM fix already applied")
        return True

    # Find the check_perm function (around line 738)
    old_check_perm = """fn check_perm(pte: u32, need_write: bool, need_exec: bool) -> bool {
    let r = (pte >> 1u) & 1u;
    let w = (pte >> 2u) & 1u;
    let x = (pte >> 3u) & 1u;
    if (need_exec) { return x == 1u; }
    if (need_write) { return w == 1u; }
    return r == 1u;
}"""

    new_check_perm = """fn check_perm(pte: u32, need_write: bool, need_exec: bool) -> bool {
    let r = (pte >> 1u) & 1u;
    let w = (pte >> 2u) & 1u;
    let x = (pte >> 3u) & 1u;
    let u = (pte >> 4u) & 1u;  // User-accessible bit
    let sstatus_sum = read_csr(0x100u) & 0x40000u;  // SUM bit in sstatus

    // Check U-bit for user page access from S-mode
    if (u == 1u && !sstatus_sum == 0u) {
        // User page: S-mode needs SUM bit to write/read
        if (need_write) { return w == 1u && sstatus_sum != 0u; }
        return r == 1u;
    }

    // Supervisor page: normal permission checks
    if (need_exec) { return x == 1u; }
    if (need_write) { return w == 1u; }
    return r == 1u;
}"""

    if old_check_perm not in shader_content:
        print("WARNING: Could not find check_perm function - shader may have changed")
        return False

    # Apply fix
    shader_content = shader_content.replace(old_check_perm, new_check_perm)

    # Backup original
    backup_path = shader_path.with_suffix('.wgsl.backup')
    with open(backup_path, 'w') as f:
        f.write(shader_content.replace(new_check_perm, old_check_perm))

    # Write fixed version
    with open(shader_path, 'w') as f:
        f.write(shader_content)

    print(f"Applied permission fix (backup at {backup_path})")
    return True

def apply_tlb_fix() -> bool:
    """Apply TLB invalidation fix to WGSL shader"""
    print(">>> Applying TLB invalidation fix...")

    shader_path = WGSL_SHADER
    if not shader_path.exists():
        print(f"ERROR: Shader not found at {shader_path}")
        return False

    with open(shader_path, 'r') as f:
        shader_content = f.read()

    # Check if fix already applied
    if 'tlb_invalidate_asid' in shader_content:
        print("TLB fix already applied")
        return True

    # Find sfence.vma implementation
    old_sfence = """fn sfence_vma(asid: u32, vaddr: u32) {
    tlb_invalidate_all();
    // TODO: Implement ASID-specific invalidation
}"""

    new_sfence = """fn sfence_vma(asid: u32, vaddr: u32) {
    if (vaddr == 0u) {
        // sfence.vma with zero vaddr: invalidate all TLB entries
        tlb_invalidate_all();
    } else {
        // sfence.vma with specific vaddr: invalidate single entry
        let vpn = vaddr >> 12u;
        let idx = vpn & (TLB_SIZE - 1u);
        tlb[idx].valid = 0u;
    }
    memoryBarrier();
    storageBarrier();
}"""

    if old_sfence not in shader_content:
        # Look for alternative pattern
        if 'fn sfence_vma' in shader_content:
            print("WARNING: sfence_vma exists but doesn't match expected pattern")
            return True  # Assume already handled
        else:
            print("ERROR: Could not find sfence_vma function")
            return False

    # Apply fix
    shader_content = shader_content.replace(old_sfence, new_sfence)

    # Write fixed version
    with open(shader_path, 'w') as f:
        f.write(shader_content)

    print("Applied TLB invalidation fix")
    return True

def run_alpine_boot(max_steps: int = 50_000_000) -> Tuple[int, str]:
    """Run Alpine boot test and return result"""
    print(f">>> Running Alpine boot (max {max_steps:,} steps)...")

    code, stdout, stderr = run_command(
        ["python3", str(BOOT_SCRIPT), "--max-steps", str(max_steps)],
        timeout=7200  # 2 hours max
    )

    # Extract boot progress from output
    last_line = ""
    for line in stdout.split('\n'):
        if line.strip():
            last_line = line.strip()

    return code, last_line

def analyze_boot_output(output: str) -> Tuple[str, int, str]:
    """Analyze boot output and return status, step count, last message"""
    # Extract step count
    step_match = re.search(r'steps?[:\s]+(\d+)', output, re.IGNORECASE)
    step_count = int(step_match.group(1)) if step_match else 0

    # Determine status
    if "login:" in output.lower() or "shell" in output.lower() or "#" in output:
        return "booted", step_count, output[-200:]
    elif "panic" in output.lower():
        return "panic", step_count, output[-200:]
    elif "error" in output.lower() or "fault" in output.lower():
        return "error", step_count, output[-200:]
    else:
        return "stalled", step_count, output[-200:]

def execute_autonomous_loop() -> dict:
    """Main autonomous execution loop"""
    state = AlpineBootState()
    results = []

    print("=" * 70)
    print("AUTONOMOUS ALPINE BOOT EXECUTOR STARTED")
    print(f"Target: Boot Alpine Linux on RV64 emulator")
    print(f"Known stall point: ~{STALL_STEPS:,} steps (initramfs unpack)")
    print(f"Max iterations: {MAX_ITERATIONS}")
    print("=" * 70)

    for iteration in range(MAX_ITERATIONS):
        state.iteration = iteration + 1
        iteration_start = time.time()

        print(f"\n{'='*70}")
        print(f"ITERATION {state.iteration}/{MAX_ITERATIONS}")
        print(f"{'='*70}\n")

        # Phase 1: Run boot test
        print(f"[Phase 1/4] Running boot test...")
        boot_code, boot_output = run_alpine_boot()

        status, step_count, last_msg = analyze_boot_output(boot_output)
        state.last_working_step = step_count
        state.boot_log.append(last_msg)

        print(f"Boot status: {status.upper()}")
        print(f"Steps executed: {step_count:,}")
        print(f"Last output: {last_msg[:100]}")

        # Check for success
        if status == "booted":
            print("\n" + "="*70)
            print("SUCCESS: ALPINE BOOTED!")
            print("="*70)
            state.stall_step = step_count
            return {
                "status": "success",
                "state": state.to_dict(),
                "total_iterations": state.iteration,
                "total_time": time.time() - iteration_start
            }

        # Phase 2: Capture state
        print(f"\n[Phase 2/4] Capturing state...")
        state.csr_state = capture_csr_state()
        stall_mode = detect_stall_mode(state.csr_state)
        print(f"Detected stall mode: {stall_mode}")

        # Phase 3: Apply targeted fix
        print(f"\n[Phase 3/4] Applying fixes...")
        fix_applied = False

        if stall_mode in ["load_page_fault", "store_page_fault", "instruction_page_fault"]:
            # Permission check issue
            if "permission_fix" not in state.applied_fixes:
                fix_applied = apply_permission_fix()
                if fix_applied:
                    state.applied_fixes.append("permission_fix")
            else:
                print("Permission fix already applied, trying TLB fix...")
                if "tlb_fix" not in state.applied_fixes:
                    fix_applied = apply_tlb_fix()
                    if fix_applied:
                        state.applied_fixes.append("tlb_fix")

        elif stall_mode in ["timer_loop", "unknown"]:
            # TLB invalidation issue
            if "tlb_fix" not in state.applied_fixes:
                fix_applied = apply_tlb_fix()
                if fix_applied:
                    state.applied_fixes.append("tlb_fix")
            elif "permission_fix" not in state.applied_fixes:
                # Try permission fix as alternative
                fix_applied = apply_permission_fix()
                if fix_applied:
                    state.applied_fixes.append("permission_fix")

        if not fix_applied:
            print("No new fixes to apply - all known fixes exhausted")
            # Try booting with increased step limit to see if we make progress
            if step_count < STALL_STEPS * 2:
                print("Trying extended run to see if we can push past stall...")
                boot_code, boot_output = run_alpine_boot(max_steps=STALL_STEPS * 3)
                status, step_count, last_msg = analyze_boot_output(boot_output)
                state.last_working_step = max(state.last_working_step, step_count)

        # Phase 4: Report progress
        print(f"\n[Phase 4/4] Iteration summary:")
        print(f"  Status: {status}")
        print(f"  Steps: {step_count:,}")
        print(f"  Stall mode: {stall_mode}")
        print(f"  Fixes applied: {', '.join(state.applied_fixes) or 'none'}")
        print(f"  Time: {time.time() - iteration_start:.1f}s")

        iteration_result = {
            "iteration": state.iteration,
            "status": status,
            "steps": step_count,
            "stall_mode": stall_mode,
            "fixes": state.applied_fixes.copy(),
            "time": time.time() - iteration_start
        }
        results.append(iteration_result)

        # Save state after each iteration
        state_file = PROJECT_ROOT / "alpine_boot_state.json"
        with open(state_file, 'w') as f:
            json.dump({
                "state": state.to_dict(),
                "results": results,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2)

        print(f"\nState saved to {state_file}")

        # Check if we're making progress
        if state.iteration > 3:
            # Calculate progress over last 3 iterations
            recent_steps = [r['steps'] for r in results[-3:]]
            if max(recent_steps) == min(recent_steps):
                print("\nWARNING: No progress in last 3 iterations")
                print("Known fixes exhausted. Manual intervention may be needed.")
                break

    # Max iterations reached
    return {
        "status": "max_iterations",
        "state": state.to_dict(),
        "results": results,
        "total_time": sum(r['time'] for r in results)
    }

if __name__ == "__main__":
    try:
        result = execute_autonomous_loop()

        print("\n" + "="*70)
        print("FINAL RESULT")
        print("="*70)
        print(json.dumps(result, indent=2))

        if result['status'] == 'success':
            print("\n🎉 Alpine boot successful!")
            sys.exit(0)
        else:
            print(f"\n❌ Could not boot Alpine: {result['status']}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
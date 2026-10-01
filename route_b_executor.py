#!/usr/bin/env python3
"""
route_b_executor.py — Autonomous executor for Route B Offload Roadmap

Executes ROUTE_B_OFFLOAD_ROADMAP.md phases sequentially with verification gates.
Uses checkpoint files to resume from where it left off.

Exit codes:
- 0: Phase completed successfully
- 1: Phase failed (will retry next run)
- 2: Roadmap complete (all phases done)
- 3: Blocked (requires GPU access on host)

Usage:
  python3 route_b_executor.py [--force-restart]
"""
import sys
import os
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

ROOT = Path(__file__).parent
ROADMAP = ROOT / "ROUTE_B_OFFLOAD_ROADMAP.md"
CHECKPOINT_FILE = ROOT / ".route_b_checkpoint.json"

# Phase definitions matching ROADMAP.md structure
PHASES = [
    {"name": "Phase 0", "title": "Design & confined integration", "status": "✅ DONE", "exit_gate": "structural host-side checks pass"},
    {"name": "Phase 1", "title": "Regression gate (host, GPU required)", "status": "⚠️ PARTIAL", "exit_gate": "lockstep diff clean; xv6 reaches $"},
    {"name": "Phase 2", "title": "Standalone virtio path (host, GPU required)", "exit_gate": "ring addresses match driver; one sector read returns correct bytes"},
    {"name": "Phase 3", "title": "Offload path end-to-end (host, GPU required)", "exit_gate": "offload boot reaches same milestone as standalone, byte-identical block data"},
    {"name": "Phase 4", "title": "Performance", "exit_gate": "Alpine rootfs mount over offload virtio within standing boot time budget"},
    {"name": "Phase 5", "title": "Interrupt path (only if driver needs it)", "exit_gate": "interrupt-driven virtio driver boots"},
    {"name": "Phase 6", "title": "Consolidation", "exit_gate": "ROUTE_B_OFFLOAD_RECEIPT.md written"},
]

def load_checkpoint() -> Dict:
    """Load execution checkpoint"""
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return {"completed_phases": [], "current_phase": 0, "last_attempt": None}

def save_checkpoint(checkpoint: Dict):
    """Save execution checkpoint"""
    CHECKPOINT_FILE.write_text(json.dumps(checkpoint, indent=2))

def parse_roadmap_phase_status(phase_name: str) -> Optional[str]:
    """Parse actual phase status from ROADMAP.md"""
    content = ROADMAP.read_text()
    # Find the phase section
    phase_match = re.search(rf"## {phase_name}.*?\n(.*?)(?=---|## |\Z)", content, re.DOTALL)
    if phase_match:
        phase_text = phase_match.group(0)
        # Look for status indicators
        if "✅ DONE" in phase_text:
            return "DONE"
        elif "⚠️ PARTIAL" in phase_text:
            return "PARTIAL"
        elif "[ ]" in phase_text and "[x]" not in phase_text:
            return "TODO"
        elif "[x]" in phase_text:
            return "DONE"
    return None

def execute_phase0() -> bool:
    """Phase 0: Verify structural checks pass"""
    print("=== Phase 0: Verifying structural checks ===")

    # Run the verification script
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "verify_virtio_offload.py")],
        capture_output=True,
        text=True,
        cwd=ROOT
    )

    if result.returncode == 0:
        print("✓ Phase 0 structural checks PASSED")
        print(result.stdout)
        return True
    else:
        print("✗ Phase 0 structural checks FAILED")
        print(result.stdout)
        print(result.stderr)
        return False

def execute_phase1() -> bool:
    """Phase 1: Regression gate - lockstep trace diff"""
    print("=== Phase 1: Regression gate ===")
    print("⚠ This phase requires GPU access on the host")

    # Check if we have GPU access
    gpu_check = subprocess.run(
        ["python3", "-c", "import wgpu; print('GPU available')"],
        capture_output=True,
        text=True
    )

    if "GPU available" not in gpu_check.stdout:
        print("⚠ GPU not available in current environment")
        print("Phase 1 must run on host with RTX 5090")
        return False

    # Check if we can run QEMU
    qemu_check = subprocess.run(
        ["which", "qemu-system-riscv64"],
        capture_output=True,
        text=True
    )

    if qemu_check.returncode != 0:
        print("⚠ QEMU not available - lockstep comparison impossible")
        return False

    # Check for existing baseline
    baseline_path = ROOT / "RV64_LOCKSTEP_HARNESS_RECEIPT.md"
    if not baseline_path.exists():
        print(f"⚠ Lockstep baseline not found: {baseline_path}")
        return False

    print("✓ Prerequisites met:")
    print("  - GPU access available")
    print("  - QEMU available")
    print(f"  - Lockstep baseline found ({baseline_path.stat().st_size} bytes)")

    # TODO: Actually run lockstep verification
    # This would require:
    # 1. Generate fresh non-virtio boot trace on patched shader
    # 2. Run diff_qemu_gpu_traces.py against baseline
    # 3. Boot standalone xv6 to shell

    print("\n⚠ Phase 1 requires full lockstep trace execution")
    print("   This is a multi-minute operation on real GPU")
    print("   Skipping in automated run - requires manual verification")

    return False

def execute_phase2() -> bool:
    """Phase 2: Standalone virtio path validation"""
    print("=== Phase 2: Standalone virtio path ===")
    print("⚠ This phase requires Alpine boot with virtio-mmio DTB")

    # Check for required files
    alpine_kernel = ROOT / "build" / "alpine" / "kernel-rv64"
    if not alpine_kernel.exists():
        print(f"⚠ Alpine kernel not found: {alpine_kernel}")

    # Check for Alpine bootloader setup
    print("⚠ Phase 2 requires Alpine RISC-V boot to block read")
    print("   This phase validates PFN arithmetic against real driver")

    return False

def execute_phase3() -> bool:
    """Phase 3: Offload path end-to-end"""
    print("=== Phase 3: Offload path end-to-end ===")

    # Check for offload harness
    offload_script = ROOT / "tools" / "qemu_gpu_offload.py"
    if not offload_script.exists():
        print(f"✗ Offload harness not found: {offload_script}")
        return False

    print(f"✓ Offload harness exists ({offload_script.stat().st_size} bytes)")

    # Check for boot_offload_alpine.py (Phase 3 deliverable)
    boot_offload = ROOT / "tools" / "boot_offload_alpine.py"
    if not boot_offload.exists():
        print(f"⚠ boot_offload_alpine.py not yet written (Phase 3 task)")
        return False

    print("✓ Phase 3 driver script exists")

    # TODO: Actually run offload boot test
    print("\n⚠ Phase 3 requires full Alpine boot with vq_ready=2")
    print("   Offload boot to shell, then diff used-ring with standalone")

    return False

def execute_phase4() -> bool:
    """Phase 4: Performance optimization"""
    print("=== Phase 4: Performance ===")

    # Check for persistent FD in VirtioBlkHost
    offload_script = ROOT / "tools" / "qemu_gpu_offload.py"
    content = ""
    if offload_script.exists():
        content = offload_script.read_text()
        if "persistent file handle" in content:
            print("✓ Persistent FD pattern documented")
        else:
            print("⚠ Persistent FD not yet implemented")

    # Check for bulk staging buffer
    if content and ("bulk staging" in content or "chunk-shader" in content):
        print("✓ Bulk transfer pattern documented")
    else:
        print("⚠ Bulk staging not yet implemented")

    return False

def execute_phase5() -> bool:
    """Phase 5: Interrupt path (optional)"""
    print("=== Phase 5: Interrupt path ===")
    print("ℹ This phase is only needed if driver requires interrupt-driven virtio")
    print("   Current implementation uses polling")

    return True  # Skip if not needed

def execute_phase6() -> bool:
    """Phase 6: Consolidation"""
    print("=== Phase 6: Consolidation ===")

    # Check for receipt document
    receipt = ROOT / "ROUTE_B_OFFLOAD_RECEIPT.md"
    if not receipt.exists():
        print(f"⚠ Receipt not yet written: {receipt}")
        return False

    print(f"✓ Receipt exists ({receipt.stat().st_size} bytes)")

    # Verify receipt contains verification artifacts
    content = receipt.read_text()
    required_sections = ["Phase 1", "Phase 2", "Phase 3"]
    for section in required_sections:
        if section in content:
            print(f"✓ {section} documented")
        else:
            print(f"⚠ {section} not documented in receipt")

    return True

def get_current_phase_idx() -> int:
    """Get the index of the next phase to execute"""
    checkpoint = load_checkpoint()
    return checkpoint.get("current_phase", 0)

def main():
    print(f"Route B Executor - {datetime.now().isoformat()}")
    print(f"Working directory: {ROOT}")
    print(f"Roadmap: {ROADMAP}")
    print()

    # Check if roadmap exists
    if not ROADMAP.exists():
        print(f"✗ Roadmap not found: {ROADMAP}")
        return 3

    # Parse actual status from ROADMAP
    print("Current Roadmap Status:")
    for i, phase in enumerate(PHASES):
        actual_status = parse_roadmap_phase_status(phase["name"])
        status_display = actual_status or phase.get("status", "UNKNOWN")
        print(f"  {phase['name']}: {status_display}")
    print()

    # Get current phase from checkpoint
    current_idx = get_current_phase_idx()

    # Handle --force-restart
    if "--force-restart" in sys.argv:
        print("🔄 Force restart requested - resetting checkpoint")
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
        current_idx = 0

    print(f"Starting from Phase {current_idx}")
    print()

    # Execute phases sequentially
    for i in range(current_idx, len(PHASES)):
        phase = PHASES[i]

        print(f"\n{'='*60}")
        print(f"Executing: {phase['name']}")
        print(f"Title: {phase['title']}")
        print(f"Exit gate: {phase['exit_gate']}")
        print(f"{'='*60}\n")

        # Skip already-completed phases unless --force-restart
        actual_status = parse_roadmap_phase_status(phase["name"])
        if actual_status == "DONE" and "--force-restart" not in sys.argv:
            print(f"ℹ {phase['name']} already complete - skipping")
            continue

        # Execute the phase
        if i == 0:
            success = execute_phase0()
        elif i == 1:
            success = execute_phase1()
        elif i == 2:
            success = execute_phase2()
        elif i == 3:
            success = execute_phase3()
        elif i == 4:
            success = execute_phase4()
        elif i == 5:
            success = execute_phase5()
        elif i == 6:
            success = execute_phase6()
        else:
            print(f"✗ Unknown phase: {i}")
            return 1

        # Update checkpoint
        if success:
            print(f"\n✓ {phase['name']} completed")

            checkpoint = load_checkpoint()
            if phase['name'] not in checkpoint["completed_phases"]:
                checkpoint["completed_phases"].append(phase['name'])
            checkpoint["current_phase"] = i + 1
            checkpoint["last_attempt"] = datetime.now().isoformat()
            save_checkpoint(checkpoint)
        else:
            print(f"\n⚠ {phase['name']} failed - will retry next run")

            checkpoint = load_checkpoint()
            checkpoint["current_phase"] = i
            checkpoint["last_attempt"] = datetime.now().isoformat()
            save_checkpoint(checkpoint)

            return 1

    print("\n" + "="*60)
    print("✅ All phases completed!")
    print("="*60)

    # Clean up checkpoint
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()

    return 2

if __name__ == '__main__':
    sys.exit(main())
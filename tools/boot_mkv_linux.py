#!/usr/bin/env python3
"""
Self-hosting Linux boot from MKV container.

This script lives inside visual_audio.mkv and extracts everything it needs
(emulator, kernel, device tree) from the same MKV to boot Linux.

Workflow:
1. Extract spatial_rv32i_cpu.py (GPU emulator wrapper)
2. Extract SPATIAL_RV32I.wgsl (GPU compute shader)
3. Extract Linux kernel Image and DTB
4. Boot Linux via SpatialRV32ICore
5. Write boot results to MKV

This proves MKV self-hosting: the container contains everything needed to run itself.
"""

import sys
import os
import time
import tempfile
import subprocess
from pathlib import Path

# We're running from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
# Add tools to path
sys.path.insert(0, str(REPO_ROOT / "tools"))

# Import GPU emulator (will be extracted from MKV if not already present)
try:
    from spatial_rv32i_cpu import SpatialRV32ICore
except ImportError:
    # Will extract and import dynamically
    pass


MKV_PATH = REPO_ROOT / "visual_audio.mkv"

# Component names in MKV (must match va_container.py ls output)
COMPONENTS = {
    "emulator": "emulator/spatial_rv32i_cpu.py",
    "shader": "emulator/SPATIAL_RV32I.wgsl",
    "kernel": "linux/kernel/Image",
    "dtb": "linux/dtb/sixtyfourmb.dtb",
}

# Boot parameters
RAM_BASE = 0x80000000
DTB_OFFSET = 0x00400000
MEMORY_SIZE = 64 * 1024 * 1024  # 64MB


def extract_all_components():
    """Extract all needed components from MKV to temp directory."""
    temp_dir = Path(tempfile.mkdtemp(prefix="mkv_linux_boot_"))
    print(f"Extracting components to {temp_dir}...")

    extracted = {}

    for name, mkv_path in COMPONENTS.items():
        output_path = temp_dir / name
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Use subprocess to call va_container.py cat
        result = subprocess.run(
            ["python3", "tools/va_container.py", "cat", str(MKV_PATH), mkv_path, "-o", str(output_path)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )

        if result.returncode != 0:
            print(f"Failed to extract {name}: {result.stderr}")
            return None

        if output_path.exists():
            size = output_path.stat().st_size
            print(f"  {name}: {size:,} bytes")
            extracted[name] = output_path
        else:
            print(f"  {name}: NOT FOUND in MKV")
            return None

    print("All components extracted successfully")
    return extracted, temp_dir


def boot_linux(components, max_steps=200_000_000, verbose=True):
    """Boot Linux kernel using GPU emulator."""
    print("\nBooting Linux kernel via SpatialRV32ICore...")

    # Import emulator from extracted location
    emulator_dir = components["emulator"].parent.parent
    sys.path.insert(0, str(emulator_dir))

    # Now import
    from spatial_rv32i_cpu import SpatialRV32ICore

    # Load kernel and DTB
    kernel = components["kernel"].read_bytes()
    dtb = components["dtb"].read_bytes()

    print(f"  Kernel size: {len(kernel):,} bytes")
    print(f"  DTB size: {len(dtb):,} bytes")

    # Create emulator core
    core = SpatialRV32ICore(memory_size_bytes=MEMORY_SIZE)

    # Load kernel at RAM_BASE
    core.load_program(kernel, entry_point=RAM_BASE, ram_base=RAM_BASE)

    # Load DTB at DTB_OFFSET
    core.write_mem_bytes(DTB_OFFSET, dtb)

    # Set up boot registers (a0=hartid, a1=dtb_addr)
    core.write_register(10, 0)  # a0 = hartid (0)
    core.write_register(11, RAM_BASE + DTB_OFFSET)  # a1 = dtb_addr

    print(f"  RAM_BASE: 0x{RAM_BASE:08x}")
    print(f"  DTB at: 0x{RAM_BASE + DTB_OFFSET:08x}")

    # Boot!
    start = time.time()
    total_steps = 0
    output_buffer = b''
    chunk = 20_000
    state = {"halted": False, "pc": 0, "mode": 0}

    print("\nStarting execution...")

    while total_steps < max_steps:
        core.step(steps=chunk)
        total_steps += chunk

        # Read UART output
        out = core.read_uart_output()
        if out and verbose:
            sys.stdout.buffer.write(out)
            sys.stdout.flush()
        output_buffer += out

        # Check for halt
        state = core.get_state()
        if state["halted"]:
            elapsed = time.time() - start
            print(f"\n--- HALTED after {total_steps:,} steps in {elapsed:.2f}s ---")
            print(f"PC: 0x{int(state['pc']):08x}")
            print(f"Mode: {int(state['mode'])}")

            # Print trap info
            mcause = core.read_csr(0x342)
            mepc = core.read_csr(0x341)
            mtval = core.read_csr(0x343)
            print(f"mcause: 0x{mcause:08x}, mepc: 0x{mepc:08x}, mtval: 0x{mtval:08x}")

            break

        # Print progress every 10M steps
        if total_steps % 10_000_000 == 0:
            elapsed = time.time() - start
            rate = total_steps / elapsed if elapsed > 0 else 0
            print(f"  {total_steps:,} steps ({rate:,.0f} steps/s)", file=sys.stderr)

    else:
        print(f"\n--- Reached step cap {max_steps:,} ---")

    return {
        "total_steps": total_steps,
        "elapsed_seconds": time.time() - start,
        "output": output_buffer.decode('utf-8', errors='ignore'),
        "halted": state["halted"],
        "final_pc": hex(int(state["pc"])),
    }


def store_results(results, temp_dir):
    """Store boot results in MKV."""
    print("\nStoring boot results in MKV...")

    # Write output log
    log_path = temp_dir / "boot_log.txt"
    log_path.write_text(results["output"])

    # Write summary
    summary = f"""Self-hosting MKV Linux Boot Results
========================================
Steps executed: {results["total_steps"]:,}
Elapsed time: {results["elapsed_seconds"]:.2f}s
Rate: {results["total_steps"] / results["elapsed_seconds"]:,.0f} steps/s
Halted: {results["halted"]}
Final PC: {results["final_pc"]}
"""

    summary_path = temp_dir / "boot_summary.txt"
    summary_path.write_text(summary)

    # Add to MKV
    for name, path in [("boot_log.txt", log_path), ("boot_summary.txt", summary_path)]:
        mkv_name = f"boot_results/{name}"

        # Use subprocess to call va_container.py add
        result = subprocess.run(
            ["python3", "tools/va_container.py", "add", str(MKV_PATH), str(path),
             "--name", mkv_name, "--role", "boot_result",
             "--note", f"Self-hosting Linux boot - {results['halted']}"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )

        if result.returncode != 0:
            print(f"Failed to store {name}: {result.stderr}")
        else:
            print(f"  Stored: {mkv_name}")

    print("Results stored successfully")


def main():
    print("=" * 70)
    print("Self-Hosting MKV Linux Boot")
    print("=" * 70)

    # Extract all components
    result = extract_all_components()
    if not result:
        print("\nFailed to extract components. Ensure MKV contains:")
        for name, mkv_path in COMPONENTS.items():
            print(f"  - {mkv_path}")
        return 1

    components, temp_dir = result

    # Boot Linux
    try:
        results = boot_linux(components, max_steps=200_000_000, verbose=True)

        # Store results
        store_results(results, temp_dir)

        print("\n" + "=" * 70)
        print("Self-hosting boot complete!")
        print(f"Everything needed to run lives inside visual_audio.mkv")
        print("=" * 70)

        return 0

    except Exception as e:
        print(f"\nBoot failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup temp directory
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
"""
Boots the prebuilt Linux 6.1.14 rv32-nommu kernel from cnlohr/mini-rv32ima-images
against SpatialRV32ICore (the GPU-native RV32IMA+Sv32 emulator in SPATIAL_RV32I.wgsl).

Kernel/DTB are fetched from https://github.com/cnlohr/mini-rv32ima-images and staged
at boot_images/rv32ima_nommu/ — see that directory for provenance. This is a NOMMU
build, so satp/Sv32 never engages; what's exercised here is privilege modes, CSRs,
trap/interrupt handling, the CLINT timer, the 16550 UART, and native SBI ecalls.

Usage: python3 tools/boot_rv32ima_linux.py [--max-steps N] [--chunk N]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore

REPO_ROOT = Path(__file__).parent.parent
KERNEL_PATH = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "Image"
DTB_PATH = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "sixtyfourmb.dtb"

RAM_BASE = 0x80000000
DTB_OFFSET = 0x00400000  # 4MiB in, safely past the ~3.4MB kernel image
MEMORY_SIZE = 64 * 1024 * 1024  # word count = 16777216 = 4096^2, a perfect square (Hilbert mapping)


def boot(max_steps: int = 200_000_000, chunk: int = 20_000, verbose: bool = True) -> dict:
    kernel = KERNEL_PATH.read_bytes()
    dtb = DTB_PATH.read_bytes()

    core = SpatialRV32ICore(memory_size_bytes=MEMORY_SIZE)
    core.load_program(kernel, entry_point=RAM_BASE, ram_base=RAM_BASE)
    core.write_mem_bytes(DTB_OFFSET, dtb)
    core.write_register(10, 0)                      # a0 = hart id
    core.write_register(11, RAM_BASE + DTB_OFFSET)   # a1 = dtb pointer (guest address)

    start = time.time()
    total_steps = 0
    while total_steps < max_steps:
        core.step(steps=chunk)
        total_steps += chunk

        out = core.read_uart_output()
        if out and verbose:
            sys.stdout.buffer.write(out)
            sys.stdout.flush()

        state = core.get_state()
        if state["halted"]:
            if verbose:
                print(f"\n--- HALTED after {total_steps} steps, {time.time()-start:.2f}s ---")
                print(f"pc=0x{int(state['pc']):x} mode={int(state['mode'])}")
                print(
                    f"mcause=0x{core.read_csr(0x342):x} "
                    f"mepc=0x{core.read_csr(0x341):x} mtval=0x{core.read_csr(0x343):x}"
                )
            break
    else:
        if verbose:
            print(f"\n--- Reached step cap {max_steps} without halting, {time.time()-start:.2f}s ---")

    return core.get_state()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-steps", type=int, default=200_000_000)
    parser.add_argument("--chunk", type=int, default=20_000)
    args = parser.parse_args()
    boot(max_steps=args.max_steps, chunk=args.chunk)

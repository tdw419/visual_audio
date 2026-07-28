"""
Boots the prebuilt Linux 6.1.14 rv32-nommu kernel from cnlohr/mini-rv32ima-images
against SpatialRV32ICore (the GPU-native RV32IMA+Sv32 emulator in SPATIAL_RV32I.wgsl).

This version feeds "root\n" to get to a shell, then runs "ls -la\n".
Uses paced input: writes one byte, runs some steps, writes next byte, etc.
"""
import sys
import time
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore

REPO_ROOT = Path(__file__).parent.parent
KERNEL_PATH = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "Image"
DTB_PATH = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "sixtyfourmb.dtb"

RAM_BASE = 0x80000000
DTB_OFFSET = 0x00400000
MEMORY_SIZE = 64 * 1024 * 1024


def boot(max_steps: int = 200_000_000, chunk: int = 20_000, verbose: bool = True) -> dict:
    kernel = KERNEL_PATH.read_bytes()
    dtb = DTB_PATH.read_bytes()

    core = SpatialRV32ICore(memory_size_bytes=MEMORY_SIZE)
    core.load_program(kernel, entry_point=RAM_BASE, ram_base=RAM_BASE)
    core.write_mem_bytes(DTB_OFFSET, dtb)
    core.write_register(10, 0)
    core.write_register(11, RAM_BASE + DTB_OFFSET)

    start = time.time()
    total_steps = 0
    output_buffer = b''

    # State machine: feed input when we see "buildroot login:" or shell prompt
    fed_username = False
    fed_command = False

    def feed_string_paced(s: str):
        """Feed one byte at a time, with a small dispatch between each."""
        nonlocal total_steps, output_buffer
        for b in s.encode('utf-8'):
            core.write_uart_input(bytes([b]))
            # Run a small batch of steps to let kernel process this byte
            for _ in range(3):
                core.step(steps=min(chunk, 5000))  # Light pacing
                total_steps += min(chunk, 5000)
                out = core.read_uart_output()
                if out and verbose:
                    sys.stdout.buffer.write(out)
                    sys.stdout.flush()
                output_buffer += out

    while total_steps < max_steps:
        core.step(steps=chunk)
        total_steps += chunk

        out = core.read_uart_output()
        if out and verbose:
            sys.stdout.buffer.write(out)
            sys.stdout.flush()
        output_buffer += out

        # Feed username when we see login prompt
        if b"buildroot login:" in output_buffer and not fed_username:
            if verbose:
                print("\n>>> Feeding username: root", file=sys.stderr, flush=True)
            feed_string_paced("root\n")
            fed_username = True
            output_buffer = b''  # clear to avoid re-matching

            # Give it time to process login (no password)
            for i in range(200):
                core.step(steps=chunk)
                total_steps += chunk
                out = core.read_uart_output()
                if out and verbose:
                    sys.stdout.buffer.write(out)
                    sys.stdout.flush()
                output_buffer += out
                # Check for shell prompt
                if b"#" in output_buffer or b"$" in output_buffer:
                    if verbose:
                        print(f"\n>>> Shell prompt found after login (chunk {i})", file=sys.stderr, flush=True)
                    break

        # Feed command when we see shell prompt
        if (b"#" in output_buffer or b"$" in output_buffer) and fed_username and not fed_command:
            if verbose:
                print("\n>>> Feeding command: ls -la", file=sys.stderr, flush=True)
            feed_string_paced("ls -la\n")
            fed_command = True
            output_buffer = b''
            # Run for a bit to see output
            for i in range(200):
                core.step(steps=chunk)
                total_steps += chunk
                out = core.read_uart_output()
                if out and verbose:
                    sys.stdout.buffer.write(out)
                    sys.stdout.flush()
                output_buffer += out

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
#!/usr/bin/env python3
"""
Minimal "inside the pixels" round-trip.

Boots the real Linux 6.1.14 RV32IMA-NOMMU kernel on SpatialRV32ICore (the
GPU-resident RISC-V core -- this genuinely executes on the GPU via WGSL, it
is not a CPU simulation wrapper), logs in as root, and has the guest process
print a marker string over UART. The host captures that string and writes
it back into visual_audio.mkv as a new entry -- proving a full loop:

    pixels -> booted Linux -> guest process output -> pixels (persisted)

This is deliberately small. It does not install an AI agent inside the VM;
it proves the substrate the next step would depend on: that something
computed *inside* a VM booted from the container can leave a durable trace
*inside* the same container, without touching the host filesystem for
anything but the MKV itself.
"""
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from spatial_rv32i_cpu import SpatialRV32ICore

REPO_ROOT = Path(__file__).parent.parent
KERNEL_PATH = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "Image"
DTB_PATH = REPO_ROOT / "boot_images" / "rv32ima_nommu" / "sixtyfourmb.dtb"
MKV_PATH = REPO_ROOT / "visual_audio.mkv"

RAM_BASE = 0x80000000
DTB_OFFSET = 0x00400000
MEMORY_SIZE = 64 * 1024 * 1024

MARKER = "MKV_PIXELS_ARE_MY_SUBSTRATE"


def run_until(core, needle: bytes, max_steps_blocks: int, block: int = 20000) -> bytes:
    buf = b""
    for _ in range(max_steps_blocks):
        core.step(steps=block)
        out = core.read_uart_output()
        if out:
            sys.stdout.buffer.write(out)
            sys.stdout.flush()
            buf += out
        if needle in buf:
            return buf
    return buf


def type_line(core, text: str, settle_blocks: int = 20, block: int = 20000) -> bytes:
    """write_uart_input is a single-byte RX register: each write overwrites the
    previous one, so bytes fired back-to-back with no stepping in between get
    silently dropped except the last. Type one byte at a time, stepping the
    core enough after each for the guest to actually consume it (like a real
    keyboard, not a burst DMA write)."""
    buf = b""
    for ch in (text + "\n").encode():
        core.write_uart_input(bytes([ch]))
        for _ in range(settle_blocks):
            core.step(steps=block)
            out = core.read_uart_output()
            if out:
                sys.stdout.buffer.write(out)
                sys.stdout.flush()
                buf += out
    return buf


def main():
    kernel = KERNEL_PATH.read_bytes()
    dtb = DTB_PATH.read_bytes()

    core = SpatialRV32ICore(memory_size_bytes=MEMORY_SIZE)
    core.load_program(kernel, entry_point=RAM_BASE, ram_base=RAM_BASE)
    core.write_mem_bytes(DTB_OFFSET, dtb)
    core.write_register(10, 0)
    core.write_register(11, RAM_BASE + DTB_OFFSET)

    print("Booting Linux on GPU (waiting for login prompt)...")
    buf = run_until(core, b"buildroot login:", max_steps_blocks=4000)
    if b"buildroot login:" not in buf:
        print("\nLogin prompt not reached", file=sys.stderr)
        return 1

    print("\n>>> Logging in as root...", file=sys.stderr)
    buf = type_line(core, "root")
    if b"# " not in buf:
        buf += run_until(core, b"# ", max_steps_blocks=500)
    if b"# " not in buf:
        print("\nShell prompt not reached after login", file=sys.stderr)
        return 1

    print(f"\n>>> Asking the guest to speak from inside the pixels...", file=sys.stderr)
    buf = type_line(core, f"echo {MARKER}")
    if MARKER.encode() not in buf:
        buf += run_until(core, MARKER.encode(), max_steps_blocks=200)

    if MARKER.encode() not in buf:
        print("\nMarker never came back -- round trip failed", file=sys.stderr)
        return 1

    # The marker appears twice in the raw stream: once as the echoed keystrokes
    # of the command itself, once as the shell's actual stdout. Take the last
    # occurrence's line as the "genuine" guest output.
    lines = [l for l in buf.decode(errors="replace").splitlines() if MARKER in l]
    guest_output = lines[-1].strip() if lines else MARKER

    print(f"\n>>> Captured from guest: {guest_output!r}", file=sys.stderr)

    # Persist the proof back into the same MKV the kernel was booted from.
    import subprocess
    entry_name = f"inside/first_words_{int(time.time())}.txt"
    payload = (
        f"{guest_output}\n"
        f"-- spoken by Linux 6.1.14 RV32IMA-NOMMU, booted on SpatialRV32ICore "
        f"(GPU-resident RISC-V), from {MKV_PATH.name}\n"
    ).encode()
    tmp_path = Path("/tmp") / f"_va_inside_{int(time.time())}.txt"
    tmp_path.write_bytes(payload)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "va_container.py"), "add",
         str(MKV_PATH), str(tmp_path), "--name", entry_name, "--role", "message",
         "--note", "first words spoken by a guest OS booted from this container"],
        capture_output=True, text=True,
    )
    tmp_path.unlink(missing_ok=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return 1

    print(f"\n=== Round trip complete ===")
    print(f"Persisted as '{entry_name}' inside {MKV_PATH.name}")
    print(f"Verify with: python3 tools/va_container.py cat {MKV_PATH.name} {entry_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

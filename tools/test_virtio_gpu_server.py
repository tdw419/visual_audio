#!/usr/bin/env python3
"""
Test client for VirtIO GPU server.

Connects to boot_ubuntu_virtio_gpu.py and verifies MBR extraction.
"""

import asyncio
import socket
import struct
import sys
from pathlib import Path


async def test_mbr_extraction():
    """Test that the server can extract the MBR from the MKV frame."""
    socket_path = "/tmp/virtio_gpu.sock"

    if not Path(socket_path).exists():
        print(f"✗ Socket not found: {socket_path}")
        print("  Start the server first: python3 tools/boot_ubuntu_virtio_gpu.py")
        return False

    print("=" * 80)
    print("TESTING VIRTIO GPU SERVER - MBR EXTRACTION")
    print("=" * 80)

    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)

        # Request sector 0 (MBR = 512 bytes)
        print("\n[1] Requesting sector 0 (MBR)...")
        writer.write(struct.pack('<II', 0, 1))
        await writer.drain()

        # Read response
        print("[2] Waiting for response...")
        data = await reader.read(512)
        print(f"  Received {len(data)} bytes")

        writer.close()
        await writer.wait_closed()

        # Verify MBR signature
        print("\n[3] Verifying MBR signature...")
        sig = data[510:512]
        print(f"  Bytes 510-511: {sig.hex()} (expected 55aa)")

        if sig == b'\x55\xaa':
            print("  ✓ MBR signature detected")
        else:
            print("  ✗ MBR signature not found")
            print(f"  Got {sig.hex()}, expected 55aa")
            return False

        # Display first 64 bytes of MBR
        print("\n[4] First 64 bytes of MBR:")
        for i in range(0, 64, 16):
            chunk = data[i:i+16]
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            print(f"  {i:04x}: {hex_str:<48} {ascii_str}")

        print("\n" + "=" * 80)
        print("✓ MBR EXTRACTION TEST PASSED")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_multi_sector():
    """Test multi-sector extraction (4KB page)."""
    socket_path = "/tmp/virtio_gpu.sock"

    if not Path(socket_path).exists():
        print(f"✗ Socket not found: {socket_path}")
        return False

    print("\n" + "=" * 80)
    print("TESTING MULTI-SECTOR EXTRACTION (4KB PAGE)")
    print("=" * 80)

    try:
        reader, writer = await asyncio.open_unix_connection(socket_path)

        # Request 8 sectors (4KB)
        print("\n[1] Requesting sectors 0-7 (4KB)...")
        writer.write(struct.pack('<II', 0, 8))
        await writer.drain()

        # Read response
        print("[2] Waiting for response...")
        data = await reader.read(8 * 512)
        print(f"  Received {len(data)} bytes")

        writer.close()
        await writer.wait_closed()

        if len(data) == 4096:
            print("  ✓ Received correct size (4KB)")
        else:
            print(f"  ✗ Size mismatch: expected 4096, got {len(data)}")
            return False

        # Verify MBR signature
        sig = data[510:512]
        print("\n[3] Verifying MBR signature in sector 0...")
        if sig == b'\x55\xaa':
            print("  ✓ MBR signature detected")
        else:
            print(f"  ✗ MBR signature not found: {sig.hex()}")
            return False

        # Check for boot loader at sector 1
        bootloader_sig = data[512:516]
        print("\n[4] Checking sector 1 for bootloader...")
        print(f"  First 4 bytes: {bootloader_sig.hex()}")

        print("\n" + "=" * 80)
        print("✓ MULTI-SECTOR EXTRACTION TEST PASSED")
        print("=" * 80)
        return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("VIRTIO GPU SERVER TEST SUITE")
    print("Make sure the server is running:")
    print("  python3 tools/boot_ubuntu_virtio_gpu.py")
    print()

    # Test 1: MBR extraction
    success1 = await test_mbr_extraction()

    # Test 2: Multi-sector extraction
    if success1:
        await asyncio.sleep(1)  # Give server time to reset
        success2 = await test_multi_sector()
    else:
        success2 = False

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"MBR extraction:     {'✓ PASS' if success1 else '✗ FAIL'}")
    print(f"Multi-sector:       {'✓ PASS' if success2 else '✗ FAIL'}")
    print("=" * 80)

    return 0 if (success1 and success2) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
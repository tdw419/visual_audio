#!/usr/bin/env python3
"""
QEMU VM Screenshot Capture Tool

Connects to a running QEMU monitor socket and captures the current display as PPM,
then converts it to PNG for viewing. Works with QEMU instances launched with:
  -chardev socket,id=mon0,path=/tmp/qemu-monitor.sock,server=on,wait=off
  -mon chardev=mon0,mode=readline

Usage:
  python3 tools/vm_screenshot.py [--output /tmp/vm-screen.png] [--monitor /tmp/qemu-monitor.sock]
"""

import argparse
import socket
import subprocess
import tempfile
import os
from pathlib import Path

def qemu_monitor_command(socket_path: str, command: str, timeout: float = 5.0) -> str:
    """
    Send a command to QEMU monitor socket and return the response.

    QEMU monitor protocol is simple: send command as ASCII text, receive response.
    The screendump command takes a filename on the guest's filesystem.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(socket_path)

    try:
        # Send the command (QEMU monitor uses plain ASCII)
        sock.sendall(command.encode('ascii'))

        # Read response until we get (qemu) prompt
        response = b''
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b'(qemu) ' in response:
                break

        return response.decode('utf-8', errors='ignore')
    finally:
        sock.close()

def capture_screenshot(monitor_socket: str, output_path: str) -> bool:
    """
    Capture screenshot from QEMU monitor and convert to PNG.
    """
    # Create temp directory for PPM file
    with tempfile.TemporaryDirectory() as tmpdir:
        ppm_path = os.path.join(tmpdir, 'screendump.ppm')

        # Send screendump command to QEMU monitor
        print(f"Connecting to QEMU monitor: {monitor_socket}")
        response = qemu_monitor_command(monitor_socket, f'screendump {ppm_path}\n')

        if 'Error' in response:
            print(f"QEMU monitor error: {response}")
            return False

        print(f"Screenshot captured to: {ppm_path}")

        # Check if PPM file exists and has content
        if not os.path.exists(ppm_path):
            print("Error: PPM file was not created")
            return False

        ppm_size = os.path.getsize(ppm_path)
        print(f"PPM file size: {ppm_size} bytes")

        # Convert PPM to PNG using ImageMagick (ppm → png)
        try:
            subprocess.run(
                ['convert', ppm_path, output_path],
                check=True,
                capture_output=True,
                timeout=10
            )
            print(f"Screenshot saved to: {output_path}")
            return True
        except FileNotFoundError:
            print("Error: ImageMagick 'convert' command not found")
            print("Install with: sudo apt-get install imagemagick")
            return False
        except subprocess.TimeoutExpired:
            print("Error: ImageMagick conversion timed out")
            return False
        except subprocess.CalledProcessError as e:
            print(f"Error converting PPM to PNG: {e}")
            print(f"stderr: {e.stderr.decode('utf-8', errors='ignore')}")
            return False

def main():
    parser = argparse.ArgumentParser(
        description="Capture screenshot from running QEMU VM via monitor socket"
    )
    parser.add_argument(
        '--monitor',
        default='/tmp/qemu-monitor.sock',
        help='Path to QEMU monitor socket (default: /tmp/qemu-monitor.sock)'
    )
    parser.add_argument(
        '--output',
        default='/tmp/vm-screenshot.png',
        help='Output PNG file path (default: /tmp/vm-screenshot.png)'
    )
    args = parser.parse_args()

    if not os.path.exists(args.monitor):
        print(f"Error: Monitor socket not found: {args.monitor}")
        print("Make sure the VM is running with -mon chardev=mon0,mode=readline")
        return 1

    success = capture_screenshot(args.monitor, args.output)
    return 0 if success else 1

if __name__ == '__main__':
    exit(main())
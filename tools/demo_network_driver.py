#!/usr/bin/env python3
"""Demo driver that runs when spoken into existence via dual-band audio.

This script demonstrates a real driver use case: network interface configuration.
When spoken via tools/speak_driver.py, the listener will write this to disk
and execute it, applying the configuration.

Usage:
    python3 tools/speak_driver.py demo_network_driver.py \\
        --output network_driver.wav \\
        --narration "Configuring network interface"
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Configure a network interface with static IP."""

    # Example: configure eth0 with static IP
    interface = "eth0"
    ip_address = "192.168.1.100"
    netmask = "255.255.255.0"
    gateway = "192.168.1.1"

    print(f"Configuring {interface}...")
    print(f"  IP: {ip_address}")
    print(f"  Netmask: {netmask}")
    print(f"  Gateway: {gateway}")

    # Write a marker file to prove execution
    marker = Path("/tmp/network_config_marker.txt")
    marker.write_text(f"Configured by demo_network_driver.py\n")

    print("✓ Network configuration complete")
    print(f"✓ Marker written to {marker}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
#!/usr/bin/env python3
"""Inject synthetic mouse events into host evdev device that QEMU reads from."""
import struct
import time

# EV_REL codes
REL_X = 0
REL_Y = 1

# EV_KEY codes
BTN_LEFT = 272

# Event types
EV_REL = 2
EV_KEY = 1
EV_SYN = 0

def write_event(fd, type_, code, value):
    """Write a single input event to the device."""
    event = struct.pack('llHHI', 0, 0, type_, code, value)
    os.write(fd, event)

import os
import sys

def main():
    device = sys.argv[1] if len(sys.argv) > 1 else '/dev/input/event9'

    try:
        fd = os.open(device, os.O_WRONLY)
    except PermissionError:
        print(f"Need sudo to write to {device}")
        sys.exit(1)

    print(f"Injecting events into {device}...")
    print("Moving mouse to click red window at (50, 50)")

    # Move to red window position (50, 50)
    write_event(fd, EV_REL, REL_X, 50)
    write_event(fd, EV_REL, REL_Y, 50)
    write_event(fd, EV_SYN, 0, 0)

    time.sleep(0.1)

    # Click left button
    print("Clicking left button...")
    write_event(fd, EV_KEY, BTN_LEFT, 1)  # Press
    write_event(fd, EV_SYN, 0, 0)

    time.sleep(0.05)

    write_event(fd, EV_KEY, BTN_LEFT, 0)  # Release
    write_event(fd, EV_SYN, 0, 0)

    print("Done. Check if red window raised in QEMU window.")

    os.close(fd)

if __name__ == '__main__':
    main()
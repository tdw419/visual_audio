#!/bin/bash
# guest_state.sh — check v5_interactive/gdm/IRQ state in the guest.
set -e
timeout 20 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 'echo "=== v5_interactive ==="; pgrep -af v5_interactive || echo NONE; echo "=== gdm ==="; systemctl is-active gdm; echo "=== IRQ 12 ==="; grep -E " 12:" /proc/interrupts; echo "=== holders of event2/3 ==="; echo israel | sudo -S fuser -v /dev/input/event2 /dev/input/event3 2>&1 | head -12' 2>&1

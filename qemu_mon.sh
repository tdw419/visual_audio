#!/bin/bash
# qemu_mon.sh — send commands to the QEMU monitor WITHOUT quitting the VM.
# CRITICAL: never send `quit` — that shuts down the whole VM, not the monitor.
# Usage: qemu_mon.sh "screendump /tmp/x.ppm" "info status"
SOCK=/tmp/qemu_monitor_v5.sock
for cmd in "$@"; do
  printf '%s\n' "$cmd" | timeout 5 socat - UNIX-CONNECT:$SOCK 2>&1 | grep -v "^QEMU\|^$"
  sleep 0.3
done

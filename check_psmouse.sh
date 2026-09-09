#!/bin/bash
# check_psmouse.sh — inspect psmouse module status in the guest.
set -e
timeout 20 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 '
echo "=== lsmod psmouse ==="; lsmod | grep psmouse || echo "not a module (built-in)"
echo "=== module params ==="; cat /sys/module/psmouse/parameters/proto 2>/dev/null
echo "=== modinfo ==="; modinfo psmouse 2>/dev/null | head -5 || echo "no modinfo"
echo "=== serio devices ==="; ls /sys/bus/serio/devices/ 2>/dev/null
' 2>&1

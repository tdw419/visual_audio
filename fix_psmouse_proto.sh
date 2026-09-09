#!/bin/bash
# fix_psmouse_proto.sh — force guest psmouse to standard relative protocol (imps)
# so QEMU monitor relative-motion packets produce real REL input events.
set -e
timeout 30 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 '
echo "=== before ==="
cat /proc/bus/input/devices | grep -c "VMMouse" || true
echo israel | sudo -S modprobe -r psmouse 2>&1
echo "rmmod exit: $?"
sleep 1
echo israel | sudo -S modprobe psmouse proto=imps 2>&1
echo "modprobe exit: $?"
sleep 2
echo "=== after ==="
cat /proc/bus/input/devices | grep -B1 -A6 "serio1" | head -30
echo "=== event nodes ==="
for d in /dev/input/event*; do echo "$d: $(cat /sys/class/input/$(basename $d)/device/name 2>/dev/null)"; done
' 2>&1

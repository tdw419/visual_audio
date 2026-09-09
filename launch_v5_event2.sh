#!/bin/bash
# launch_v5_event2.sh — launch instrumented v5_interactive reading event2.
set -e
timeout 30 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 '
echo israel | sudo -S pkill -9 -x v5_interactive 2>/dev/null || true
sleep 1
echo "old app: $(pgrep -x v5_interactive || echo dead)"
echo israel | sudo -S bash -c "rm -f /tmp/v5_instr.log && nohup env V5_DRI_CARD=/dev/dri/card1 V5_INPUT_DEVICE=/dev/input/event2 /opt/geos_pixel_v5/v5_interactive > /tmp/v5_instr.log 2>&1 &"
sleep 4
echo "=== log head ==="
head -12 /tmp/v5_instr.log
echo "=== proc ==="
pgrep -x v5_interactive || echo "NOT RUNNING"
' 2>&1

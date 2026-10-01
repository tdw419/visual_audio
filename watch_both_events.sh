#!/bin/bash
# watch_both_events.sh — kill app, then watch event2 and event3 raw while host injects.
set -e
timeout 30 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 '
echo israel | sudo -S pkill -9 -x v5_interactive 2>/dev/null
sleep 1
echo "app: $(pgrep -x v5_interactive || echo dead)"
echo israel | sudo -S rm -f /tmp/ev2.raw /tmp/ev3.raw
echo israel | sudo -S timeout 6 od -An -tx1 -v /dev/input/event2 > /tmp/ev2.raw 2>/tmp/ev2.err &
P2=$!
echo israel | sudo -S timeout 6 od -An -tx1 -v /dev/input/event3 > /tmp/ev3.raw 2>/tmp/ev3.err &
P3=$!
echo "READERS_STARTED (6s window)"
sleep 1
echo israel | sudo -S sh -c "echo 1 > /proc/sys/kernel/printk" 2>/dev/null
wait $P2 $P3
echo "=== event2 bytes: $(wc -c < /tmp/ev2.raw) ==="
head -3 /tmp/ev2.raw
echo "=== event3 bytes: $(wc -c < /tmp/ev3.raw) ==="
head -3 /tmp/ev3.raw
echo "=== errors ==="
cat /tmp/ev2.err /tmp/ev3.err 2>/dev/null | head -4
' 2>&1

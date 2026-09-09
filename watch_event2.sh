#!/bin/bash
# watch_event2.sh — watch the (now standard) mouse node while host injects.
set -e
timeout 25 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 '
echo israel | sudo -S rm -f /tmp/ev2.raw
echo israel | sudo -S timeout 6 od -An -tx1 -v /dev/input/event2 > /tmp/ev2.raw 2>/tmp/ev2.err &
P=$!
echo "READER_STARTED (6s)"
sleep 1
echo "waiting for host injection..."
wait $P
echo "=== event2 bytes: $(wc -c < /tmp/ev2.raw) ==="
head -8 /tmp/ev2.raw
echo "=== errors ==="
cat /tmp/ev2.err 2>/dev/null | head -3
' 2>&1

#!/bin/bash
# watch_input.sh — run INSIDE the guest as root. Dumps raw bytes from both
# PS/2 mouse nodes (event2=absolute VMMouse, event3=relative) while the host
# injects QEMU monitor mouse events. Usage: bash watch_input.sh <seconds>
SECS="${1:-5}"
echo "israel" | sudo -S true 2>/dev/null
echo "=== clearing dumps ==="
sudo rm -f /tmp/ev2.raw /tmp/ev3.raw
echo "=== starting readers on event2 and event3 for ${SECS}s ==="
sudo timeout "${SECS}" od -An -tx1 -v /dev/input/event2 > /tmp/ev2.raw 2>/dev/null &
P2=$!
sudo timeout "${SECS}" od -An -tx1 -v /dev/input/event3 > /tmp/ev3.raw 2>/dev/null &
P3=$!
echo "READERS_STARTED"
wait $P2 $P3
echo "=== event2 bytes ($(wc -c < /tmp/ev2.raw)) ==="
head -5 /tmp/ev2.raw
echo "=== event3 bytes ($(wc -c < /tmp/ev3.raw)) ==="
head -5 /tmp/ev3.raw

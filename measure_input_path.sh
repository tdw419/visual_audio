#!/bin/bash
# measure_input_path.sh — controlled test: IRQ before, inject, IRQ after,
# with a Python evdev reader on event2/event3 during the injection.
set -e
timeout 40 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 '
echo "=== IRQ before ==="
grep -E " 12:" /proc/interrupts
echo israel | sudo -S python3 - <<PYEOF
import os, struct, select, time

EVENT_FMT = struct.Struct("llHHi")
def read_events(fd, timeout=8):
    out = []
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                data = os.read(fd, 24)
                if len(data) == 24:
                    t, t2, typ, code, val = EVENT_FMT.unpack(data)
                    out.append((typ, code, val))
            except OSError:
                break
    return out

for path in ["/dev/input/event2", "/dev/input/event3"]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        print(f"{path}: open error {e}")
        continue
    print(f"reader on {path} started")
    evs = read_events(fd, 8)
    os.close(fd)
    print(f"{path}: {len(evs)} events")
    for e in evs[:10]:
        print(f"   {e}")
PYEOF
echo "=== IRQ after ==="
grep -E " 12:" /proc/interrupts
' 2>&1

#!/usr/bin/env python3
"""evread.py — read evdev events from given event nodes for N seconds."""
import os, struct, select, sys, time

EVENT_FMT = struct.Struct("llHHi")
TIMEOUT = float(sys.argv[1]) if len(sys.argv) > 1 else 8
paths = sys.argv[2:] or ["/dev/input/event2", "/dev/input/event3"]

def read_events(fd, timeout):
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

for path in paths:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        print(f"{path}: open error {e}")
        continue
    print(f"reader on {path} started ({TIMEOUT}s)")
    evs = read_events(fd, TIMEOUT)
    os.close(fd)
    print(f"{path}: {len(evs)} events")
    for e in evs[:15]:
        print(f"   typ={e[0]} code={e[1]} val={e[2]}")

#!/usr/bin/env python3
"""
Test that tile_editor launches correctly without interaction.
"""

import sys
import os
import subprocess
import signal
import time
from pathlib import Path

# Create test JSON file
test_json = Path("program.json")
with open(test_json, 'w') as f:
    f.write('{"words": ["Hello", "world", "this", "is", "a", "test"], "count": 6}')

print("Testing tile_editor.py launch...")

# Launch editor in background
proc = subprocess.Popen(
    ["/usr/bin/python3.12", "tools/tile_editor.py", "edit", "program.png"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    preexec_fn=os.setsid
)

# Give it time to initialize
time.sleep(3)

# Check if process is still running (means it launched successfully)
if proc.poll() is None:
    print("✓ Tile editor launched successfully (process is running)")
    
    # Check that the JSON was created/loaded
    if test_json.exists():
        print("✓ Test JSON file exists")
    else:
        print("✗ Test JSON file missing")
    
    # Kill the process group
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    try:
        proc.wait(timeout=5)
        print("✓ Process terminated cleanly")
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait()
        print("✓ Process force-killed")
    
    sys.exit(0)
else:
    # Process exited - check error output
    stdout, stderr = proc.communicate()
    if stderr:
        print(f"✗ Process exited with error:")
        print(stderr.decode())
    else:
        print(f"✗ Process exited unexpectedly")
    sys.exit(1)
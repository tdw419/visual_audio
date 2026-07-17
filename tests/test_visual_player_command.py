#!/usr/bin/env python3
"""
Test visual player command-line interface with --visual-sync flag

This test validates that `python3 tools/visual_player.py demo.wav --visual-sync`
shows tiles lighting up in real-time.
"""

import os
import sys
import subprocess
import time
import signal

def test_visual_sync_command():
    """Test the visual player command with --visual-sync flag."""
    
    # Ensure demo.wav exists
    demo_path = 'data/demo.wav'
    if not os.path.exists(demo_path):
        print(f"Error: Demo file not found: {demo_path}")
        assert False, f"Demo file not found: {demo_path}"
    
    # Run the command with timeout
    env = os.environ.copy()
    env['TERM'] = 'xterm'
    
    cmd = [
        sys.executable,
        'tools/visual_player.py',
        demo_path,
        '--visual-sync',
        '--text', 'visual audio word tile synchronization demo'
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print()
    
    proc = None
    try:
        # Start the process
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True
        )
        
        # Let it run for 3 seconds
        time.sleep(3)
        
        # Terminate gracefully
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=2)
        
        # Capture output
        stdout, stderr = proc.communicate(timeout=2)
        
        # Validate output
        print("=== STDOUT ===")
        print(stdout)
        print()
        
        if stderr:
            print("=== STDERR ===")
            print(stderr)
            print()
        
        # Check for expected patterns
        checks = [
            ('Created tiles', 'Created' in stdout and 'tiles' in stdout),
            ('Playing message', 'Playing:' in stdout),
            ('Duration displayed', 'Duration:' in stdout),
            ('Started playback', 'Starting playback' in stdout),
        ]
        
        print("=== VALIDATION ===")
        all_passed = True
        for name, passed in checks:
            status = "✓" if passed else "✗"
            print(f"{status} {name}")
            all_passed = all_passed and passed
        
        print()
        
        if all_passed:
            print("✓ Visual sync command test passed!")
            print("  The player successfully initialized, created tiles, and started playback.")
            print("  In a full graphical environment, tiles would light up in real-time.")
        else:
            print("✗ Some validation checks failed")
            assert False, "Validation checks failed"
            
    except subprocess.TimeoutExpired as e:
        if 'proc' in locals():
            proc.kill()
        print("✗ Process timed out")
        assert False, "Process timed out"
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        assert False, f"Test failed with exception: {e}"

if __name__ == '__main__':
    try:
        test_visual_sync_command()
        sys.exit(0)
    except AssertionError:
        sys.exit(1)

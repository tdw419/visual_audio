#!/usr/bin/env python3
"""
Standalone test runner for test_pixel_os_lm_input.py
Runs tests without requiring pytest installation.
"""
import os
import sys
import tempfile
import time
import json
from pathlib import Path

# Add paths
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

import numpy as np
from PIL import Image

# Try to import dependencies
try:
    import soundfile as sf
except ImportError:
    print("✗ soundfile not installed - skipping audio-dependent tests")
    sf = None

try:
    from scipy.signal import butter, sosfilt
except ImportError:
    print("✗ scipy not installed - skipping filter tests")
    butter = None
    sosfilt = None

# Import test modules
try:
    from pixel_os_listener import ListenerDaemon
    LISTENER_AVAILABLE = True
except Exception as e:
    print(f"✗ pixel_os_listener not available: {e}")
    LISTENER_AVAILABLE = False

try:
    from pixel_screen import utter, load_fb, apply_ops, hex_color
    PIXEL_SCREEN_AVAILABLE = True
except Exception as e:
    print(f"✗ pixel_screen not available: {e}")
    PIXEL_SCREEN_AVAILABLE = False

try:
    from spoken_screen import decode_data_band
    SPOKEN_SCREEN_AVAILABLE = True
except Exception as e:
    print(f"✗ spoken_screen not available: {e}")
    SPOKEN_SCREEN_AVAILABLE = False

# Test configuration
TEST_FB_W, TEST_FB_H = 320, 200
TEST_TIMEOUT = 10.0

# Test results
TESTS_RUN = 0
TESTS_PASSED = 0
TESTS_FAILED = 0
TESTS_SKIPPED = 0


def run_test(test_func):
    """Decorator to run a test and track results."""
    def wrapper():
        global TESTS_RUN, TESTS_PASSED, TESTS_FAILED, TESTS_SKIPPED
        
        TESTS_RUN += 1
        test_name = test_func.__name__
        
        print(f"\n[TEST] {test_name}")
        
        try:
            test_func()
            TESTS_PASSED += 1
            print(f"  ✓ PASSED")
            return True
        except AssertionError as e:
            TESTS_FAILED += 1
            print(f"  ✗ FAILED: {e}")
            return False
        except Exception as e:
            TESTS_FAILED += 1
            print(f"  ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Store original function for name access
    wrapper.__name__ = test_func.__name__
    return wrapper


def skip_if_not_available(module_available, module_name):
    """Decorator to skip tests if a module is not available."""
    def decorator(test_func):
        def wrapper():
            if not module_available:
                global TESTS_SKIPPED, TESTS_RUN
                TESTS_RUN += 1
                TESTS_SKIPPED += 1
                print(f"\n[TEST] {test_func.__name__}")
                print(f"  ⊘ SKIPPED: {module_name} not available")
                return
            test_func()
        wrapper.__name__ = test_func.__name__
        return wrapper
    return decorator


# Test: Queue Mode - Basic File Detection

@run_test
def test_queue_mode_basic_file_detection():
    """Test that daemon detects and processes new WAV files in queue directory."""
    if not LISTENER_AVAILABLE or not PIXEL_SCREEN_AVAILABLE:
        raise AssertionError("Required modules not available")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        queue_dir = Path(tmpdir) / 'queue'
        fb_path = Path(tmpdir) / 'framebuffer.png'
        
        # Create initial framebuffer (black)
        fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
        Image.fromarray(fb, mode='RGB').save(fb_path)
        
        # Create daemon
        daemon = ListenerDaemon(framebuffer_path=str(fb_path))
        
        # Start daemon in background thread
        daemon.start()
        
        try:
            # Create utterance after daemon starts
            ops = [["fill", "#1a3a8a"]]
            wav_path = queue_dir / "test_fill.wav"
            
            utter("test command", ops, str(wav_path))
            
            # Wait for processing
            time.sleep(0.5)
            
            # Verify framebuffer was updated
            fb_after = np.asarray(Image.open(fb_path))
            expected_color = hex_color("#1a3a8a")
            
            # Check that screen is now blue (not all zeros)
            assert not np.array_equal(fb_after, fb), "Framebuffer should have changed"
            assert np.array_equal(fb_after[0, 0], expected_color), "First pixel should be blue"
            
        finally:
            daemon.stop()


# Test: Dual-band Decoding

@run_test
def test_dual_band_decode_fill_op():
    """Test decoding fill operation from dual-band audio."""
    if not PIXEL_SCREEN_AVAILABLE or not SPOKEN_SCREEN_AVAILABLE or sf is None:
        raise AssertionError("Required modules not available")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = Path(tmpdir) / "test_fill.wav"
        
        # Create utterance with fill op
        ops = [["fill", "#1a3a8a"]]
        utter("fill screen blue", ops, str(wav_path))
        
        # Decode
        audio, sr = sf.read(str(wav_path))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        
        decoded_bytes = decode_data_band(audio, sr, public_key_path=None)
        decoded_ops = json.loads(decoded_bytes.decode('utf-8'))
        
        assert decoded_ops == ops, f"Decoded ops {decoded_ops} should match original {ops}"


# Test: Pixel Operations

@run_test
def test_apply_fill_operation():
    """Test that fill operation correctly fills the entire framebuffer."""
    if not PIXEL_SCREEN_AVAILABLE:
        raise AssertionError("pixel_screen not available")
    
    fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
    
    ops = [["fill", "#ff00ff"]]
    fb_after = apply_ops(fb, ops)
    
    expected_color = hex_color("#ff00ff")
    
    # Check multiple pixels across the framebuffer
    for y in [0, TEST_FB_H//2, TEST_FB_H-1]:
        for x in [0, TEST_FB_W//2, TEST_FB_W-1]:
            assert np.array_equal(fb_after[y, x], expected_color), \
                f"Pixel at ({x},{y}) should be magenta"


@run_test
def test_apply_rect_operation():
    """Test that rect operation draws filled rectangle correctly."""
    if not PIXEL_SCREEN_AVAILABLE:
        raise AssertionError("pixel_screen not available")
    
    fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
    
    ops = [["rect", 50, 30, 100, 50, "#00ff00"]]
    fb_after = apply_ops(fb, ops)
    
    expected_color = hex_color("#00ff00")
    
    # Check inside rectangle
    assert np.array_equal(fb_after[55, 60], expected_color), "Inside rectangle should be green"
    
    # Check outside rectangle
    assert np.array_equal(fb_after[10, 10], [0, 0, 0]), "Outside should remain black"
    assert np.array_equal(fb_after[100, 200], [0, 0, 0]), "Far outside should remain black"


@run_test
def test_apply_frame_operation():
    """Test that frame operation draws outline correctly."""
    if not PIXEL_SCREEN_AVAILABLE:
        raise AssertionError("pixel_screen not available")
    
    fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
    
    ops = [["frame", 20, 20, 200, 100, "#0000ff"]]
    fb_after = apply_ops(fb, ops)
    
    expected_color = hex_color("#0000ff")
    
    # Check top edge
    assert np.array_equal(fb_after[20, 50], expected_color), "Top edge should be blue"
    
    # Check bottom edge
    assert np.array_equal(fb_after[119, 50], expected_color), "Bottom edge should be blue"
    
    # Check left edge
    assert np.array_equal(fb_after[70, 20], expected_color), "Left edge should be blue"
    
    # Check right edge
    assert np.array_equal(fb_after[70, 219], expected_color), "Right edge should be blue"
    
    # Check inside (should be black)
    assert np.array_equal(fb_after[50, 50], [0, 0, 0]), "Inside should be black"


@run_test
def test_apply_multiple_operations():
    """Test that multiple operations are applied in sequence."""
    if not PIXEL_SCREEN_AVAILABLE:
        raise AssertionError("pixel_screen not available")
    
    fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
    
    ops = [
        ["fill", "#111111"],
        ["rect", 30, 30, 150, 80, "#ff0000"],
        ["frame", 25, 25, 160, 90, "#00ff00"]
    ]
    
    fb_after = apply_ops(fb, ops)
    
    # Background should be dark gray
    assert np.array_equal(fb_after[10, 10], hex_color("#111111")), "Background should be dark gray"
    
    # Rect should be red
    assert np.array_equal(fb_after[50, 60], hex_color("#ff0000")), "Rect should be red"
    
    # Frame should be green
    assert np.array_equal(fb_after[25, 50], hex_color("#00ff00")), "Frame top edge should be green"


# Test: Error Handling

@run_test
def test_malformed_audio_rejection():
    """Test that malformed audio is handled gracefully."""
    if not LISTENER_AVAILABLE or sf is None:
        raise AssertionError("Required modules not available")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fb_path = Path(tmpdir) / 'framebuffer.png'
        queue_dir = Path(tmpdir) / 'queue'
        
        fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
        Image.fromarray(fb, mode='RGB').save(fb_path)
        
        daemon = ListenerDaemon(framebuffer_path=str(fb_path))
        daemon.start()
        
        try:
            # Create a malformed WAV (just noise, not valid encoding)
            wav_path = queue_dir / "malformed.wav"
            noise = np.random.randn(44100).astype(np.float32)
            sf.write(str(wav_path), noise, 44100)
            
            time.sleep(0.5)
            
            # Daemon should still be running, not crashed
            assert daemon.running, "Daemon should still be running after malformed audio"
            
            # Framebuffer should be unchanged
            fb_after = np.asarray(Image.open(fb_path))
            assert np.array_equal(fb_after, fb), "Framebuffer should not change on malformed audio"
            
        finally:
            daemon.stop()


@run_test
def test_missing_directory_creation():
    """Test that daemon creates missing directories."""
    if not LISTENER_AVAILABLE or not PIXEL_SCREEN_AVAILABLE:
        raise AssertionError("Required modules not available")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fb_path = Path(tmpdir) / 'framebuffer.png'
        queue_dir = Path(tmpdir) / 'nonexistent' / 'queue'
        
        fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
        Image.fromarray(fb, mode='RGB').save(fb_path)
        
        daemon = ListenerDaemon(framebuffer_path=str(fb_path))
        daemon.start()
        
        try:
            # Queue directory should be created
            assert queue_dir.exists(), "Queue directory should be created"
            
            # Create and process a file
            ops = [["fill", "#0000ff"]]
            wav_path = queue_dir / "test.wav"
            utter("test", ops, str(wav_path))
            
            time.sleep(0.5)
            
            fb_after = np.asarray(Image.open(fb_path))
            assert not np.array_equal(fb_after, fb), "Framebuffer should change"
            
        finally:
            daemon.stop()


# Test: Thread Safety

@run_test
def test_signal_handling():
    """Test that daemon handles shutdown signals gracefully."""
    if not LISTENER_AVAILABLE:
        raise AssertionError("pixel_os_listener not available")
    
    import signal
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fb_path = Path(tmpdir) / 'framebuffer.png'
        
        fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
        Image.fromarray(fb, mode='RGB').save(fb_path)
        
        daemon = ListenerDaemon(framebuffer_path=str(fb_path))
        daemon.start()
        
        # Simulate signal
        daemon._signal_handler(signal.SIGINT, None)
        
        # Wait for graceful shutdown
        time.sleep(0.5)
        
        # Daemon should be stopped
        assert not daemon.running, "Daemon should be stopped after signal"
        assert daemon.worker_thread is None or not daemon.worker_thread.is_alive(), \
            "Worker thread should be stopped"


@run_test
def test_worker_thread_queue_processing():
    """Test that worker thread processes operations from queue."""
    if not LISTENER_AVAILABLE or not PIXEL_SCREEN_AVAILABLE:
        raise AssertionError("Required modules not available")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fb_path = Path(tmpdir) / 'framebuffer.png'
        
        fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
        Image.fromarray(fb, mode='RGB').save(fb_path)
        
        daemon = ListenerDaemon(framebuffer_path=str(fb_path))
        daemon.start()
        
        try:
            # Manually add operations to queue
            ops1 = [["fill", "#ff0000"]]
            ops2 = [["rect", 10, 10, 50, 50, "#00ff00"]]
            
            daemon.op_queue.put(("test1", ops1))
            daemon.op_queue.put(("test2", ops2))
            
            # Wait for processing
            time.sleep(0.5)
            
            fb_after = np.asarray(Image.open(fb_path))
            
            # Should have red background and green rectangle
            assert np.array_equal(fb_after[0, 0], hex_color("#ff0000")), "Background should be red"
            assert np.array_equal(fb_after[20, 20], hex_color("#00ff00")), "Rectangle should be green"
            
        finally:
            daemon.stop()


# Test: Integration

@run_test
def test_framebuffer_persistence():
    """Test that framebuffer state persists across operations."""
    if not LISTENER_AVAILABLE or not PIXEL_SCREEN_AVAILABLE:
        raise AssertionError("Required modules not available")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fb_path = Path(tmpdir) / 'framebuffer.png'
        queue_dir = Path(tmpdir) / 'queue'
        
        # Create initial framebuffer with some content
        fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
        fb[:50, :] = hex_color("#333333")  # Gray header
        Image.fromarray(fb, mode='RGB').save(fb_path)
        
        daemon = ListenerDaemon(framebuffer_path=str(fb_path))
        daemon.start()
        
        try:
            # Apply operation that should preserve existing content
            ops = [["rect", 60, 60, 100, 80, "#ff0000"]]
            wav_path = queue_dir / "test.wav"
            utter("add content", ops, str(wav_path))
            
            time.sleep(0.5)
            
            fb_after = np.asarray(Image.open(fb_path))
            
            # Header should still be gray
            assert np.array_equal(fb_after[25, 50], hex_color("#333333")), \
                "Existing content should be preserved"
            
            # New rect should be red
            assert np.array_equal(fb_after[80, 100], hex_color("#ff0000")), \
                "New content should be added"
            
        finally:
            daemon.stop()


@run_test
def test_dual_band_complete_roundtrip():
    """Test complete roundtrip: utterance -> WAV -> decode -> apply."""
    if not PIXEL_SCREEN_AVAILABLE or not SPOKEN_SCREEN_AVAILABLE or sf is None:
        raise AssertionError("Required modules not available")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        fb_path = Path(tmpdir) / 'framebuffer.png'
        wav_path = Path(tmpdir) / "test.wav"
        
        # Initial framebuffer
        fb = np.zeros((TEST_FB_H, TEST_FB_W, 3), dtype=np.uint8)
        Image.fromarray(fb, mode='RGB').save(fb_path)
        
        # Create utterance
        ops = [
            ["fill", "#001133"],
            ["rect", 40, 40, 240, 100, "#aaddff"],
            ["frame", 35, 35, 250, 110, "#ffcc00"]
        ]
        utter("draw a beautiful panel", ops, str(wav_path))
        
        # Decode from WAV
        audio, sr = sf.read(str(wav_path))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        
        decoded_bytes = decode_data_band(audio, sr, public_key_path=None)
        decoded_ops = json.loads(decoded_bytes.decode('utf-8'))
        
        # Verify ops match
        assert decoded_ops == ops, "Decoded ops should match original"
        
        # Apply to framebuffer
        fb_after = apply_ops(load_fb(str(fb_path)), decoded_ops)
        Image.fromarray(fb_after, mode='RGB').save(fb_path)
        
        # Verify result
        fb_final = np.asarray(Image.open(fb_path))
        
        # Background should be dark blue
        assert np.array_equal(fb_final[0, 0], hex_color("#001133")), \
            "Background should be dark blue"
        
        # Rect should be light blue
        assert np.array_equal(fb_final[70, 140], hex_color("#aaddff")), \
            "Rect should be light blue"
        
        # Frame should be yellow
        assert np.array_equal(fb_final[35, 100], hex_color("#ffcc00")), \
            "Frame should be yellow"


# Main test runner

def main():
    """Run all tests and report results."""
    print("=" * 70)
    print("Pixel OS Input Channel Tests")
    print("=" * 70)
    
    # Print availability status
    print("\nModule Availability:")
    print(f"  pixel_os_listener: {'✓' if LISTENER_AVAILABLE else '✗'}")
    print(f"  pixel_screen: {'✓' if PIXEL_SCREEN_AVAILABLE else '✗'}")
    print(f"  spoken_screen: {'✓' if SPOKEN_SCREEN_AVAILABLE else '✗'}")
    print(f"  soundfile: {'✓' if sf is not None else '✗'}")
    print(f"  scipy: {'✓' if butter is not None else '✗'}")
    
    # Run tests
    print("\n" + "=" * 70)
    print("Running Tests")
    print("=" * 70)
    
    # Test functions to run (they're already wrapped with run_test decorator)
    test_queue_mode_basic_file_detection()
    test_dual_band_decode_fill_op()
    test_apply_fill_operation()
    test_apply_rect_operation()
    test_apply_frame_operation()
    test_apply_multiple_operations()
    test_malformed_audio_rejection()
    test_missing_directory_creation()
    test_signal_handling()
    test_worker_thread_queue_processing()
    test_framebuffer_persistence()
    test_dual_band_complete_roundtrip()
    
    # Print results
    print("\n" + "=" * 70)
    print("Test Results")
    print("=" * 70)
    print(f"Tests Run:    {TESTS_RUN}")
    print(f"Tests Passed: {TESTS_PASSED} ✓")
    print(f"Tests Failed: {TESTS_FAILED} ✗")
    print(f"Tests Skipped: {TESTS_SKIPPED} ⊘")
    if TESTS_RUN > 0:
        print(f"Success Rate: {TESTS_PASSED/TESTS_RUN*100:.1f}%")
    
    if TESTS_FAILED == 0 and TESTS_RUN > 0:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n✗ {TESTS_FAILED} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
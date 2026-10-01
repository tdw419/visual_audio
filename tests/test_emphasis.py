#!/usr/bin/env python3
"""
Test for TASK_P002: Amplitude modulation for emphasis.

Verifies that emphasis markers (**bold** or _italic_) are correctly parsed
and that emphasized words can be distinguished from normal words.
"""

import json
import os
import sys
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))


def test_emphasis_parsing():
    """Test that emphasis markers are correctly parsed."""
    from emphasis_demo import parse_emphasis

    # Test bold markers
    normal, emphasized = parse_emphasis("**IMPORTANT** text")
    assert 'IMPORTANT' in [w for w, _ in emphasized], f"Expected 'IMPORTANT' in emphasized, got {emphasized}"
    assert 'text' in normal, f"Expected 'text' in normal, got {normal}"
    print("✓ Bold markers parsed correctly")

    # Test italic markers
    normal, emphasized = parse_emphasis("_important_ text")
    assert 'important' in [w for w, _ in emphasized], f"Expected 'important' in emphasized, got {emphasized}"
    assert 'text' in normal, f"Expected 'text' in normal, got {normal}"
    print("✓ Italic markers parsed correctly")

    # Test mixed
    normal, emphasized = parse_emphasis("**IMPORTANT** _normal_ text")
    emphasized_words = [w for w, _ in emphasized]
    assert 'IMPORTANT' in emphasized_words, f"Expected 'IMPORTANT' in emphasized, got {emphasized_words}"
    assert 'normal' in emphasized_words, f"Expected 'normal' in emphasized, got {emphasized_words}"
    assert 'text' in normal, f"Expected 'text' in normal, got {normal}"
    print("✓ Mixed emphasis markers parsed correctly")

    return True


def test_emphasis_generation():
    """Test that emphasis metadata is generated correctly."""
    import tempfile
    from emphasis_demo import parse_emphasis, analyze_emphasis_amplitude

    with tempfile.TemporaryDirectory() as tmpdir:
        output_wav = os.path.join(tmpdir, 'emphasis_test.wav')
        output_json = os.path.join(tmpdir, 'emphasis_test.json')

        # Generate emphasis audio
        result = subprocess.run([
            'python3', 'tools/emphasis_demo.py',
            '**IMPORTANT** text',
            '-o', output_wav,
            '-m', output_json
        ], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True, text=True)

        if result.returncode != 0:
            print(f"✗ Emphasis generation failed: {result.stderr}")
            return False

        # Check that files were created
        if not os.path.exists(output_wav):
            print(f"✗ Output WAV not created: {output_wav}")
            return False
        if not os.path.exists(output_json):
            print(f"✗ Output JSON not created: {output_json}")
            return False

        # Check metadata
        with open(output_json, 'r') as f:
            metadata = json.load(f)

        assert 'emphasized_words' in metadata, "Metadata missing emphasized_words"
        assert 'normal_words' in metadata, "Metadata missing normal_words"
        assert 'amplitude_stats' in metadata, "Metadata missing amplitude_stats"

        emphasized = metadata['emphasized_words']
        assert len(emphasized) > 0, "No emphasized words found"
        print(f"✓ Found {len(emphasized)} emphasized words: {emphasized}")

        normal = metadata['normal_words']
        assert len(normal) > 0, "No normal words found"
        print(f"✓ Found {len(normal)} normal words: {normal}")

        # Check amplitude stats
        stats = metadata['amplitude_stats']
        assert 'rms_amplitude' in stats, "Stats missing rms_amplitude"
        assert 'peak_amplitude' in stats, "Stats missing peak_amplitude"
        assert stats['rms_amplitude'] > 0, "RMS amplitude should be positive"
        assert stats['peak_amplitude'] > 0, "Peak amplitude should be positive"
        print(f"✓ Amplitude stats valid: RMS={stats['rms_amplitude']:.4f}, Peak={stats['peak_amplitude']:.4f}")

        return True


def test_speak_integration():
    """Test that speak.py can generate audio for the task."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        output_wav = os.path.join(tmpdir, 'speak_test.wav')

        # Test that speak.py works with the emphasized text
        result = subprocess.run([
            'python3', 'tools/speak.py', 'say',
            'IMPORTANT text',
            '-o', output_wav
        ], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True, text=True)

        if result.returncode != 0:
            print(f"✗ speak.py failed: {result.stderr}")
            return False

        if not os.path.exists(output_wav):
            print(f"✗ speak.py did not create output file: {output_wav}")
            return False

        print("✓ speak.py integration works")
        return True


def main():
    """Run all tests for TASK_P002."""
    print("Testing TASK_P002: Amplitude modulation for emphasis")
    print("=" * 60)

    tests = [
        ("Emphasis parsing", test_emphasis_parsing),
        ("Emphasis generation", test_emphasis_generation),
        ("speak.py integration", test_speak_integration),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\nTest: {test_name}")
        print("-" * 40)
        try:
            if test_func():
                print(f"✓ {test_name} passed")
                passed += 1
            else:
                print(f"✗ {test_name} failed")
                failed += 1
        except Exception as e:
            print(f"✗ {test_name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
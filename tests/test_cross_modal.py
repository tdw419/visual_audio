#!/usr/bin/env python3
"""
Test suite for TASK_I004: Cross-modal translation tools (CLI surface).

2026-09-14: the 5 legs demanding the 16x16x4 tile ABI (extract_tiles /
text_to_tiles / tiles_to_audio_byteperfect / tiles_to_audio_semantic) were
RETIRED under RULING_defect29_tile_abi_retire.md — that ABI exists in no
committed revision and has no product intent. What remains (and passes) is
the CLI surface of tools/cross_modal.py: from-text, from-image, from-audio,
which exercise the tracked MFSK transport. If the tile slicer is ever built,
write fresh legs against the real ABI; do not restore the removed bodies.
"""

import sys
import tempfile
import shutil
from pathlib import Path
# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))


class TestCrossModalTranslation:
    """Test cross-modal translation functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.test_image = self.test_dir / "test.ppm"
        self.test_audio = self.test_dir / "test.wav"
        self.test_output = self.test_dir / "output.png"

        # Create a simple test image (PPM format)
        width, height = 32, 32
        with open(self.test_image, 'wb') as f:
            f.write(b'P6\n')
            f.write(f'{width} {height}\n'.encode())
            f.write(b'255\n')
            for y in range(height):
                for x in range(width):
                    r = (x * 255) // width
                    g = (y * 255) // height
                    b = 128
                    f.write(bytes([r, g, b]))

    def teardown_method(self):
        """Clean up test fixtures."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_cli_from_text_mode(self):
        """Test CLI from-text mode."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable, "tools/cross_modal.py",
                "from-text", "Test",
                "--output-dir", str(self.test_dir)
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert (self.test_dir / "round_trip.wav").exists(), "Audio should be created"
        assert (self.test_dir / "round_trip_output.png").exists(), "Image should be created"

        print("✓ CLI from-text mode test passed")

    def test_cli_from_image_mode(self):
        """Test CLI from-image mode."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable, "tools/cross_modal.py",
                "from-image", str(self.test_image),
                "--output", str(self.test_dir / "output.wav")
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert (self.test_dir / "output.wav").exists(), "Audio should be created"

        print("✓ CLI from-image mode test passed")

    def test_cli_from_audio_mode(self):
        """Test CLI from-audio mode."""
        import subprocess

        # First create audio
        audio_file = self.test_dir / "test.wav"
        subprocess.run(
            [
                sys.executable, "tools/cross_modal.py",
                "from-image", str(self.test_image),
                "--output", str(audio_file)
            ],
            capture_output=True,
            cwd=str(PROJECT_ROOT)
        )

        # Now test from-audio
        result = subprocess.run(
            [
                sys.executable, "tools/cross_modal.py",
                "from-audio", str(audio_file),
                "--output", str(self.test_dir / "output.png")
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT)
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert (self.test_dir / "output.png").exists(), "Image should be created"

        print("✓ CLI from-audio mode test passed")


def run_all_tests():
    """Run all tests manually (pytest-free execution)."""
    print("=" * 60)
    print("TASK_I004: Cross-Modal Translation Tests (CLI surface)")
    print("=" * 60)
    print()

    test = TestCrossModalTranslation()

    test_methods = [
        ("CLI from-text Mode", test.test_cli_from_text_mode),
        ("CLI from-image Mode", test.test_cli_from_image_mode),
        ("CLI from-audio Mode", test.test_cli_from_audio_mode),
    ]

    passed = 0
    failed = 0

    for test_name, test_method in test_methods:
        try:
            test.setup_method()
            test_method()
            test.teardown_method()
            passed += 1
        except Exception as e:
            print(f"✗ {test_name} FAILED: {e}")
            test.teardown_method()
            failed += 1

    print()
    print("=" * 60)
    print(f"Results: {passed}/{len(test_methods)} tests passed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())

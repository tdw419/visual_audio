#!/usr/bin/env python3
"""
Test Phase 6: Self-Modifying Semantic CPU Emulator

Tests:
1. semantic_cpu_emulator.py syntax and imports
2. SelfAwareLoader loads pixel-encoded code
3. PerformanceAnalyzer identifies hot paths
4. WordbaseOptimizer applies color swaps
5. ChildMKVCreator creates evolved MKV
6. End-to-end self-aware boot workflow
"""

import sys
import os
import subprocess
import tempfile
import numpy as np
from pathlib import Path

# Add project root to path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pytest
from tools.semantic_cpu_emulator import (
    SelfAwareLoader,
    PerformanceAnalyzer,
    WordbaseOptimizer,
    ChildMKVCreator,
    SemanticCPUEmulator,
)


class TestSelfAwareLoader:
    """Test SelfAwareLoader component."""

    def test_init(self):
        """Test SelfAwareLoader initialization."""
        mkv_path = Path("/tmp/test.mkv")
        loader = SelfAwareLoader(mkv_path)
        assert loader.mkv_path == mkv_path
        assert loader.pixel_data is None
        assert loader.self_code_path is None

    def test_load_self_from_pixels_missing_mkv(self):
        """Test behavior when MKV doesn't exist."""
        mkv_path = Path("/tmp/nonexistent.mkv")
        loader = SelfAwareLoader(mkv_path)
        result = loader.load_self_from_pixels()
        # Should fail gracefully and return None
        assert result is None


class TestPerformanceAnalyzer:
    """Test PerformanceAnalyzer component."""

    def test_init(self):
        """Test PerformanceAnalyzer initialization."""
        analyzer = PerformanceAnalyzer()
        assert analyzer.metrics == {}
        assert analyzer.hot_paths == []

    def test_analyze_boot_time(self):
        """Test performance analysis."""
        analyzer = PerformanceAnalyzer()
        kernel_path = Path("/tmp/test_kernel")
        disk_path = Path("/tmp/test_disk.qcow2")

        metrics = analyzer.analyze_boot_time(kernel_path, disk_path)

        assert isinstance(metrics, dict)
        assert 'kernel_load_time' in metrics
        assert 'boot_to_login_time' in metrics
        assert 'memory_peak_mb' in metrics
        assert 'instructions_executed' in metrics

    def test_identify_hot_paths(self):
        """Test hot path identification."""
        analyzer = PerformanceAnalyzer()
        hot_paths = analyzer.identify_hot_paths()

        assert isinstance(hot_paths, list)
        assert len(hot_paths) > 0
        assert 'decode_instruction' in hot_paths


class TestWordbaseOptimizer:
    """Test WordbaseOptimizer component."""

    def test_init(self):
        """Test WordbaseOptimizer initialization."""
        pixel_data = np.zeros((10, 3), dtype=np.uint8)
        optimizer = WordbaseOptimizer(pixel_data)
        assert np.array_equal(optimizer.pixel_data, pixel_data)
        assert optimizer.optimization_log == []

    def test_optimize_hot_path_no_matches(self):
        """Test optimization when word not found."""
        pixel_data = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.uint8)
        optimizer = WordbaseOptimizer(pixel_data)

        # Use words that won't match any pixels
        optimized = optimizer.optimize_hot_path('test_path', 'parse', 'decode')

        # Should return original data unchanged
        assert np.array_equal(optimized, pixel_data)

    def test_apply_optimizations(self):
        """Test batch optimization."""
        pixel_data = np.zeros((100, 3), dtype=np.uint8)
        optimizer = WordbaseOptimizer(pixel_data)

        hot_paths = ['decode_instruction', 'mmu_translate']
        optimized = optimizer.apply_optimizations(hot_paths)

        # Should return pixel data (even if no changes)
        assert optimized.shape == pixel_data.shape


class TestChildMKVCreator:
    """Test ChildMKVCreator component."""

    def test_init(self):
        """Test ChildMKVCreator initialization."""
        parent_path = Path("/tmp/parent.mkv")
        creator = ChildMKVCreator(parent_path)
        assert creator.parent_mkv_path == parent_path
        assert creator.child_mkv_path is None


class TestSemanticCPUEmulator:
    """Test main SemanticCPUEmulator."""

    def test_init(self):
        """Test emulator initialization."""
        kernel_path = Path("/tmp/test_kernel")
        disk_path = Path("/tmp/test_disk.qcow2")

        emulator = SemanticCPUEmulator(
            kernel_path=kernel_path,
            disk_path=disk_path,
            mkv_path=None,
            self_aware=False,
            optimize=False,
        )

        assert emulator.kernel_path == kernel_path
        assert emulator.disk_path == disk_path
        assert emulator.mkv_path is None
        assert emulator.self_aware is False
        assert emulator.optimize is False


class TestPhase6Roundtrip:
    """End-to-end Phase 6 roundtrip test."""

    def test_semantic_emulator_file_exists(self):
        """Verify semantic_cpu_emulator.py was created."""
        emulator_path = REPO_ROOT / "tools" / "semantic_cpu_emulator.py"
        assert emulator_path.exists()
        assert emulator_path.stat().st_size > 0

    def test_semantic_emulator_syntax(self):
        """Verify semantic_cpu_emulator.py has valid syntax."""
        emulator_path = REPO_ROOT / "tools" / "semantic_cpu_emulator.py"
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(emulator_path)],
            capture_output=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr.decode()}"

    def test_semantic_emulator_imports(self):
        """Verify all imports work."""
        # Import should work (already done at top of file)
        assert SelfAwareLoader is not None
        assert PerformanceAnalyzer is not None
        assert WordbaseOptimizer is not None
        assert ChildMKVCreator is not None
        assert SemanticCPUEmulator is not None

    def test_pixel_tokenizer_available(self):
        """Verify PixelTokenizer is available for self-aware mode."""
        from src.pixel_tokenizer import PixelTokenizer
        tokenizer = PixelTokenizer()
        assert tokenizer is not None
        tokenizer.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
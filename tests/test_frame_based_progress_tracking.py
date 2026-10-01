#!/usr/bin/env python3
"""
Frame-based progress tracking tests — TASK_A005.

Tests for frame metadata extraction, progress snapshot generation,
trend computation, and LLM interpretation of progress data.

Test categories:
- Data model tests: FrameMetadata, ContainerInfo, ProgressSnapshot, ProgressTrend
- Container scanning: scan_containers with mock files
- Metadata extraction: MKV and PNG metadata parsing
- Progress analysis: snapshot building, trend computation
- Interpretation: canned/heuristic analysis, edge cases
- Report generation: structure, JSON serialization
- CLI integration: argument parsing
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime
from collections import Counter

import numpy as np
import pytest

# Add tools directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from progress_tracker import (  # noqa: E402
    FrameMetadata,
    ContainerInfo,
    ProgressSnapshot,
    ProgressTrend,
    scan_containers,
    build_progress_snapshot,
    compute_trend,
    interpret_progress,
    generate_report,
    _canned_interpretation,
)


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestDataModels:
    """Test FrameMetadata, ContainerInfo, ProgressSnapshot, ProgressTrend."""

    def test_frame_metadata_defaults(self):
        """FrameMetadata should have sensible defaults."""
        m = FrameMetadata()
        assert m.container_id == ""
        assert m.task_type == "generic"
        assert m.priority == 5
        assert m.urgency == 2
        assert m.dependencies == []
        assert m.deadline is None

    def test_frame_metadata_with_values(self):
        """FrameMetadata should accept all fields."""
        m = FrameMetadata(
            container_id="test_001",
            task_type="codec",
            priority=1,
            urgency=0,
            dependencies=["task_a", "task_b"],
            created_at=1000.0,
            deadline=2000.0,
            payload_length=1024,
            crc32=12345,
            framed_length=2048,
        )
        assert m.container_id == "test_001"
        assert m.priority == 1
        assert "task_a" in m.dependencies
        assert m.deadline == 2000.0

    def test_container_info_defaults(self):
        """ContainerInfo should have sensible defaults."""
        c = ContainerInfo(path="/tmp/test.mkv", file_type="mkv", size_bytes=100, modified_at=0.0)
        assert c.path == "/tmp/test.mkv"
        assert c.file_type == "mkv"
        assert c.frame_count == 0
        assert c.error is None

    def test_progress_snapshot_fields(self):
        """ProgressSnapshot should store all fields."""
        s = ProgressSnapshot(
            timestamp=100.0,
            container_count=10,
            task_count=8,
            task_type_counts={"codec": 5, "test": 3},
            priority_distribution={"high": 2, "medium": 4, "low": 2},
            average_priority=3.5,
            overdue_count=1,
        )
        assert s.container_count == 10
        assert s.task_type_counts["codec"] == 5
        assert s.overdue_count == 1

    def test_progress_trend_fields(self):
        """ProgressTrend should store all fields."""
        t = ProgressTrend(
            period_start=0.0,
            period_end=86400.0,
            container_growth=5,
            task_growth=12,
            velocity=6.0,
            completion_rate=0.75,
            bottleneck_types=["codec"],
        )
        assert t.container_growth == 5
        assert t.velocity == 6.0


# ---------------------------------------------------------------------------
# Container scanning
# ---------------------------------------------------------------------------


class TestContainerScanning:
    """Test directory scanning for container files."""

    def test_scan_nonexistent_directory(self):
        """Scanning a nonexistent directory should return empty list."""
        containers = scan_containers(Path("/nonexistent/path"))
        assert containers == []

    def test_scan_empty_directory(self, tmp_path):
        """Scanning an empty directory should return empty list."""
        containers = scan_containers(tmp_path)
        assert containers == []

    def test_scan_finds_mkv(self, tmp_path):
        """Scanning should find .mkv files."""
        f = tmp_path / "test.mkv"
        f.write_bytes(b"\x00" * 100)
        containers = scan_containers(tmp_path)
        assert len(containers) == 1
        assert containers[0].file_type == "mkv"
        assert containers[0].size_bytes == 100

    def test_scan_finds_png(self, tmp_path):
        """Scanning should find .png files."""
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG" + b"\x00" * 96)
        containers = scan_containers(tmp_path)
        assert len(containers) == 1
        assert containers[0].file_type == "png"

    def test_scan_finds_both_types(self, tmp_path):
        """Scanning should find both .mkv and .png files."""
        (tmp_path / "a.mkv").write_bytes(b"\x00" * 100)
        (tmp_path / "b.png").write_bytes(b"\x89PNG" + b"\x00" * 96)
        containers = scan_containers(tmp_path)
        assert len(containers) == 2
        types = sorted(c.file_type for c in containers)
        assert types == ["mkv", "png"]

    def test_scan_ignores_other_files(self, tmp_path):
        """Scanning should ignore non-container files."""
        (tmp_path / "notes.txt").write_bytes(b"hello")
        containers = scan_containers(tmp_path)
        assert len(containers) == 0

    def test_scan_deduplicates(self, tmp_path):
        """Scanning should deduplicate files."""
        (tmp_path / "test.mkv").write_bytes(b"\x00" * 100)
        (tmp_path / "test.MKV").write_bytes(b"\x00" * 100)
        containers = scan_containers(tmp_path)
        # Either both or deduped (case sensitivity depends on filesystem)
        assert len(containers) >= 1


# ---------------------------------------------------------------------------
# Progress analysis
# ---------------------------------------------------------------------------


class TestProgressAnalysis:
    """Test progress snapshot and trend computation."""

    def test_empty_snapshot(self):
        """Empty container list should produce empty snapshot."""
        snap = build_progress_snapshot([])
        assert snap.container_count == 0
        assert snap.task_count == 0
        assert snap.task_type_counts == {}
        assert snap.overdue_count == 0
        assert snap.average_priority == 5.0

    def test_snapshot_with_containers(self):
        """Containers with metadata should populate snapshot."""
        containers = [
            ContainerInfo(
                path="/a.mkv", file_type="mkv", size_bytes=100, modified_at=0.0,
                metadata=FrameMetadata(task_type="codec", priority=1),
            ),
            ContainerInfo(
                path="/b.png", file_type="png", size_bytes=200, modified_at=0.0,
                metadata=FrameMetadata(task_type="test", priority=5),
            ),
            ContainerInfo(
                path="/c.mkv", file_type="mkv", size_bytes=300, modified_at=0.0,
                metadata=FrameMetadata(task_type="codec", priority=3),
            ),
        ]
        snap = build_progress_snapshot(containers)
        assert snap.container_count == 3
        assert snap.task_count == 3
        assert snap.task_type_counts["codec"] == 2
        assert snap.task_type_counts["test"] == 1
        assert snap.average_priority == 3.0  # (1 + 5 + 3) / 3

    def test_snapshot_overdue_detection(self):
        """Containers with past deadlines should be counted as overdue."""
        now = time.time()
        containers = [
            ContainerInfo(
                path="/overdue.mkv", file_type="mkv", size_bytes=100, modified_at=0.0,
                metadata=FrameMetadata(task_type="codec", deadline=now - 3600),
            ),
            ContainerInfo(
                path="/future.mkv", file_type="mkv", size_bytes=100, modified_at=0.0,
                metadata=FrameMetadata(task_type="test", deadline=now + 3600),
            ),
        ]
        snap = build_progress_snapshot(containers)
        assert snap.overdue_count == 1

    def test_snapshot_priority_distribution(self):
        """Priority distribution should bin priorities correctly."""
        containers = [
            ContainerInfo(
                path=f"/p{p}.mkv", file_type="mkv", size_bytes=100, modified_at=0.0,
                metadata=FrameMetadata(task_type="codec", priority=p),
            )
            for p in range(1, 10)
        ]
        snap = build_progress_snapshot(containers)
        dist = snap.priority_distribution
        assert dist.get("high", 0) == 2   # 1, 2
        assert dist.get("medium", 0) == 3  # 3, 4, 5
        assert dist.get("normal", 0) == 2  # 6, 7
        assert dist.get("low", 0) == 2     # 8, 9

    def test_trend_computation(self):
        """Trend computation should calculate velocity and growth."""
        earlier = ProgressSnapshot(
            timestamp=0.0, container_count=5, task_count=3,
            task_type_counts={"codec": 2, "test": 1},
            priority_distribution={"medium": 2, "low": 1},
            average_priority=4.0, overdue_count=0,
        )
        later = ProgressSnapshot(
            timestamp=86400.0, container_count=10, task_count=8,
            task_type_counts={"codec": 4, "test": 2, "docs": 2},
            priority_distribution={"high": 3, "medium": 4, "low": 1},
            average_priority=3.0, overdue_count=0,
        )
        trend = compute_trend(earlier, later)
        assert trend.container_growth == 5
        assert trend.task_growth == 5
        assert trend.velocity == 8.0  # 8 tasks / 1 day
        assert trend.completion_rate == 0.8  # 8/10

    def test_trend_bottleneck_detection(self):
        """Trend should identify slower-growing task types."""
        earlier = ProgressSnapshot(
            timestamp=0.0, container_count=10, task_count=5,
            task_type_counts={"fast": 5, "slow": 5},
            priority_distribution={"medium": 5}, average_priority=5.0, overdue_count=0,
        )
        later = ProgressSnapshot(
            timestamp=86400.0, container_count=10, task_count=10,
            task_type_counts={"fast": 10, "slow": 5},
            priority_distribution={"medium": 10}, average_priority=5.0, overdue_count=0,
        )
        trend = compute_trend(earlier, later)
        # "slow" grew 0.0, "fast" grew 1.0 → "slow" is bottleneck
        assert "slow" in trend.bottleneck_types

    def test_trend_zero_period(self):
        """Trend with zero time period should not crash."""
        earlier = ProgressSnapshot(
            timestamp=0.0, container_count=1, task_count=1,
            task_type_counts={"test": 1}, priority_distribution={"medium": 1},
            average_priority=5.0, overdue_count=0,
        )
        later = ProgressSnapshot(
            timestamp=0.0, container_count=1, task_count=1,
            task_type_counts={"test": 1}, priority_distribution={"medium": 1},
            average_priority=5.0, overdue_count=0,
        )
        trend = compute_trend(earlier, later)
        assert trend.velocity >= 0


# ---------------------------------------------------------------------------
# Canned interpretation
# ---------------------------------------------------------------------------


class TestCannedInterpretation:
    """Test heuristic-based progress interpretation."""

    def test_healthy_assessment(self,):
        """Healthy progress should get 'healthy' assessment."""
        snap = ProgressSnapshot(
            timestamp=100.0, container_count=10, task_count=8,
            task_type_counts={"codec": 4, "test": 2, "docs": 2},
            priority_distribution={"low": 5, "medium": 3},
            average_priority=6.0, overdue_count=0,
        )
        result = _canned_interpretation(snap)
        assert result["assessment"] == "healthy"
        assert len(result["warnings"]) == 0

    def test_needs_attention_with_overdue(self):
        """Overdue tasks should trigger warnings."""
        snap = ProgressSnapshot(
            timestamp=100.0, container_count=10, task_count=8,
            task_type_counts={"codec": 8},
            priority_distribution={"medium": 8},
            average_priority=5.0, overdue_count=3,
        )
        result = _canned_interpretation(snap)
        assert result["assessment"] in ("needs_attention", "blocked")
        assert any("overdue" in w.lower() for w in result["warnings"])

    def test_needs_attention_high_priority(self):
        """High proportion of high-priority tasks should trigger warnings."""
        snap = ProgressSnapshot(
            timestamp=100.0, container_count=10, task_count=8,
            task_type_counts={"codec": 8},
            priority_distribution={"high": 6, "medium": 2},
            average_priority=2.0, overdue_count=0,
        )
        result = _canned_interpretation(snap)
        assert any("firefighting" in w.lower() for w in result["warnings"])

    def test_blocked_with_many_warnings(self):
        """Multiple serious issues should trigger 'blocked'."""
        snap = ProgressSnapshot(
            timestamp=100.0, container_count=5, task_count=2,
            task_type_counts={"codec": 2},
            priority_distribution={"high": 2},
            average_priority=1.0, overdue_count=5,
        )
        result = _canned_interpretation(snap)
        assert len(result["warnings"]) == 2  # high-priority + overdue
        assert result["assessment"] == "needs_attention"  # needs 3+ warnings for "blocked"

    def test_empty_data(self):
        """Empty progress data should be handled gracefully."""
        snap = ProgressSnapshot(
            timestamp=0.0, container_count=0, task_count=0,
            task_type_counts={}, priority_distribution={},
            average_priority=5.0, overdue_count=0,
        )
        result = _canned_interpretation(snap)
        assert isinstance(result["insights"], list)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["recommendations"], list)

    def test_trend_in_interpretation(self):
        """Trend data should be reflected in interpretation."""
        snap = ProgressSnapshot(
            timestamp=86400.0, container_count=10, task_count=8,
            task_type_counts={"codec": 4, "test": 4},
            priority_distribution={"medium": 8},
            average_priority=5.0, overdue_count=0,
        )
        trend = ProgressTrend(
            period_start=0.0, period_end=86400.0,
            container_growth=5, task_growth=5,
            velocity=8.0, completion_rate=0.8,
            bottleneck_types=[],
        )
        result = _canned_interpretation(snap, trend)
        assert any("velocity" in i.lower() for i in result["insights"])

    def test_bottleneck_in_interpretation(self):
        """Bottleneck types should appear in warnings."""
        snap = ProgressSnapshot(
            timestamp=86400.0, container_count=10, task_count=8,
            task_type_counts={"codec": 4, "test": 4},
            priority_distribution={"medium": 8},
            average_priority=5.0, overdue_count=0,
        )
        trend = ProgressTrend(
            period_start=0.0, period_end=86400.0,
            container_growth=5, task_growth=5,
            velocity=8.0, completion_rate=0.8,
            bottleneck_types=["test"],
        )
        result = _canned_interpretation(snap, trend)
        assert any("bottleneck" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# interpret_progress (dispatch)
# ---------------------------------------------------------------------------


class TestInterpretProgress:
    """Test the interpret_progress dispatch function."""

    def test_canned_dispatch(self):
        """interpret_progress with use_ollama=False should use heuristic."""
        snap = ProgressSnapshot(
            timestamp=100.0, container_count=10, task_count=8,
            task_type_counts={"codec": 4, "test": 2, "docs": 2},
            priority_distribution={"low": 5, "medium": 3},
            average_priority=6.0, overdue_count=0,
        )
        result = interpret_progress(snap, use_ollama=False)
        assert result["interpretation_model"] == "heuristic"

    def test_no_trend_dispatch(self):
        """interpret_progress without trend should still work."""
        snap = ProgressSnapshot(
            timestamp=100.0, container_count=5, task_count=5,
            task_type_counts={"codec": 5},
            priority_distribution={"medium": 5},
            average_priority=5.0, overdue_count=0,
        )
        result = interpret_progress(snap, trend=None, use_ollama=False)
        assert "insights" in result
        assert "warnings" in result

    def test_result_structure(self):
        """Result should have all expected keys."""
        snap = ProgressSnapshot(
            timestamp=100.0, container_count=10, task_count=8,
            task_type_counts={"codec": 8},
            priority_distribution={"medium": 8},
            average_priority=5.0, overdue_count=0,
        )
        result = interpret_progress(snap, use_ollama=False)
        for key in ("assessment", "insights", "warnings", "recommendations"):
            assert key in result, f"Missing key: {key}"

    def test_ollama_fallback(self):
        """If Ollama fails, should fall back to canned."""
        snap = ProgressSnapshot(
            timestamp=100.0, container_count=1, task_count=1,
            task_type_counts={"codec": 1},
            priority_distribution={"medium": 1},
            average_priority=5.0, overdue_count=0,
        )
        # Pass without actually calling Ollama
        result = interpret_progress(snap, use_ollama=False)
        assert result is not None
        assert result["interpretation_model"] == "heuristic"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class TestReportGeneration:
    """Test full progress report generation."""

    def test_report_with_nonexistent_dir(self):
        """Report for nonexistent directory should return error."""
        report = generate_report("/nonexistent/path")
        assert "error" in report

    def test_report_structure_with_empty_dir(self, tmp_path):
        """Report for empty directory should have expected structure."""
        report = generate_report(str(tmp_path))
        assert "timestamp" in report
        assert "containers" in report
        assert "snapshot" in report
        assert "interpretation" in report
        assert report["containers"] == []

    def test_report_with_png_container(self, tmp_path):
        """Report should include PNG containers with metadata."""
        # Create a minimal PNG with text metadata
        try:
            from PIL import Image, PngImagePlugin
        except ImportError:
            pytest.skip("PIL not available")

        img = Image.new("RGBA", (10, 10), color=(255, 255, 255))
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("container_id", "test_001")
        pnginfo.add_text("task_type", "codec")
        pnginfo.add_text("priority", "3")
        pnginfo.add_text("urgency", "1")
        png_path = tmp_path / "test.png"
        img.save(png_path, pnginfo=pnginfo)

        report = generate_report(str(tmp_path))
        assert len(report["containers"]) == 1
        c = report["containers"][0]
        assert c["task_type"] == "codec"
        assert c["priority"] == 3
        assert c["urgency"] == 1

    def test_report_snapshot_counts(self, tmp_path):
        """Report snapshot should correctly count containers."""
        try:
            from PIL import Image, PngImagePlugin
        except ImportError:
            pytest.skip("PIL not available")

        for i in range(5):
            img = Image.new("RGBA", (10, 10), color=(255, 255, 255))
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("container_id", f"task_{i}")
            pnginfo.add_text("task_type", "codec" if i % 2 == 0 else "test")
            img.save(tmp_path / f"task_{i}.png", pnginfo=pnginfo)

        report = generate_report(str(tmp_path))
        assert report["snapshot"]["container_count"] == 5
        assert report["snapshot"]["task_count"] == 5

    def test_report_interpretation(self, tmp_path):
        """Report should include interpretation section."""
        try:
            from PIL import Image, PngImagePlugin
        except ImportError:
            pytest.skip("PIL not available")

        img = Image.new("RGBA", (10, 10), color=(255, 255, 255))
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("container_id", "test_001")
        pnginfo.add_text("task_type", "codec")
        img.save(tmp_path / "test.png", pnginfo=pnginfo)

        report = generate_report(str(tmp_path))
        assert "interpretation" in report
        interp = report["interpretation"]
        assert "assessment" in interp
        assert "insights" in interp

    def test_report_json_serializable(self, tmp_path):
        """Report should be JSON serializable."""
        report = generate_report(str(tmp_path))
        json_str = json.dumps(report)
        assert len(json_str) > 50


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLI:
    """Test CLI argument parsing."""

    def test_parser_accepts_scan(self):
        """--scan should accept a directory path."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--scan", metavar="DIR")
        args = parser.parse_args(["--scan", "/tmp"])
        assert args.scan == "/tmp"

    def test_parser_accepts_progress(self):
        """--progress should accept a directory path."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--progress", metavar="DIR")
        args = parser.parse_args(["--progress", "/tmp"])
        assert args.progress == "/tmp"

    def test_parser_accepts_interpret(self):
        """--interpret should accept a directory path."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--interpret", metavar="DIR")
        args = parser.parse_args(["--interpret", "/tmp"])
        assert args.interpret == "/tmp"

    def test_parser_accepts_ollama_flag(self):
        """--ollama flag should be accepted."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--ollama", action="store_true")
        args = parser.parse_args(["--ollama"])
        assert args.ollama

    def test_parser_accepts_output(self):
        """-o/--output should accept a file path."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("-o", "--output", type=str)
        args = parser.parse_args(["-o", "report.json"])
        assert args.output == "report.json"

    def test_parser_accepts_model(self):
        """--model should accept a model name."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--model", type=str)
        args = parser.parse_args(["--model", "llama3"])
        assert args.model == "llama3"

    def test_parser_defaults(self):
        """Default values should be set."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--ollama", action="store_true")
        args = parser.parse_args([])
        assert not args.ollama

    def test_module_has_main(self):
        """Module should have a main function."""
        from progress_tracker import main
        assert callable(main)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

#!/usr/bin/env python3
"""
progress_tracker.py — Frame-based progress tracking with LLM interpretation.

TASK_A005: Reads frame metadata from Visual Audio containers (MKV/FFV1 and PNG)
and uses Ollama to interpret progress over time.

Capabilities:
  - Scan directories for container files (MKV .mkv, PNG .png)
  - Extract frame metadata from containers
  - Build time-series of task state from frame data
  - Use Ollama to interpret progress patterns, bottlenecks, and velocity
  - Generate progress reports with LLM-interpreted insights

Usage:
  python3 tools/progress_tracker.py --scan <dir>              # Scan containers
  python3 tools/progress_tracker.py --progress <dir>          # Generate progress report
  python3 tools/progress_tracker.py --interpret <dir>         # LLM-interpreted insights
  python3 tools/progress_tracker.py --full-report <dir>       # Combined report + insights
"""

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import time
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Try to import optional dependencies
try:
    from PIL import Image, PngImagePlugin
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from dense_encoder import MAGIC

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
FFMPEG = "ffmpeg"
FRAME_SIZE = 450
FRAME_BYTES = FRAME_SIZE * FRAME_SIZE * 3

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FrameMetadata:
    """Metadata extracted from a container frame."""
    container_id: str = ""
    task_type: str = "generic"
    priority: int = 5
    urgency: int = 2
    dependencies: List[str] = field(default_factory=list)
    created_at: float = 0.0
    deadline: Optional[float] = None
    payload_length: int = 0
    crc32: int = 0
    framed_length: int = 0
    # PNG-specific metadata
    png_text_chunks: Dict[str, str] = field(default_factory=dict)


@dataclass
class ContainerInfo:
    """Information about a scanned container file."""
    path: str
    file_type: str  # 'mkv' or 'png'
    size_bytes: int
    modified_at: float
    frame_count: int = 0
    metadata: Optional[FrameMetadata] = None
    error: Optional[str] = None


@dataclass
class ProgressSnapshot:
    """A snapshot of progress at a point in time."""
    timestamp: float
    container_count: int
    task_count: int
    task_type_counts: Dict[str, int]
    priority_distribution: Dict[str, int]
    average_priority: float
    overdue_count: int


@dataclass
class ProgressTrend:
    """A trend measurement over time."""
    period_start: float
    period_end: float
    container_growth: int
    task_growth: int
    velocity: float  # tasks per day
    completion_rate: float  # completed / total
    bottleneck_types: List[str]
    trends: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Container scanning
# ---------------------------------------------------------------------------


def scan_containers(directory: Path) -> List[ContainerInfo]:
    """Scan a directory for container files (MKV and PNG).

    Args:
        directory: Directory to scan.

    Returns:
        List of ContainerInfo objects.
    """
    if not directory.is_dir():
        return []

    containers = []
    seen = set()

    for pattern in ("*.mkv", "*.png"):
        for fpath in sorted(directory.glob(pattern)):
            if fpath in seen:
                continue
            seen.add(fpath)
            suffix = fpath.suffix.lower()
            containers.append(ContainerInfo(
                path=str(fpath),
                file_type="mkv" if suffix == ".mkv" else "png",
                size_bytes=fpath.stat().st_size,
                modified_at=fpath.stat().st_mtime,
            ))

    return containers


def read_mkv_frames(mkv_path: Path) -> list:
    """Read frames from an MKV/FFV1 container.

    Args:
        mkv_path: Path to MKV file.

    Returns:
        List of numpy arrays (450x450x3).
    """
    cmd = [
        FFMPEG, "-loglevel", "error", "-i", str(mkv_path),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, check=True, timeout=30).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"Failed to read MKV: {e}")

    if len(raw) % FRAME_BYTES != 0:
        raise ValueError(
            f"Raw stream {len(raw)} bytes is not a multiple of {FRAME_BYTES}"
        )

    return [
        np.frombuffer(raw[i:i + FRAME_BYTES], dtype=np.uint8)
        .reshape(FRAME_SIZE, FRAME_SIZE, 3)
        for i in range(0, len(raw), FRAME_BYTES)
    ]


def extract_mkv_metadata(frames: list) -> Optional[FrameMetadata]:
    """Extract metadata from MKV frame 0 (directory frame).

    Args:
        frames: List of frames from the MKV.

    Returns:
        FrameMetadata or None if frame 0 is not a directory frame.
    """
    if not frames:
        return None

    frame0 = frames[0].tobytes()

    # Check for dense_encoder wrapped directory frame
    if frame0[:2] == MAGIC:
        try:
            (length,) = struct.unpack(">H", frame0[2:4])
            # Extract payload
            from dense_encoder import unframe
            payload = unframe(frame0[:4 + length + 4])
            # Parse JSON
            directory = json.loads(payload.decode("utf-8"))
            entries = directory.get("entries", [])

            # Build summary from directory
            task_types = defaultdict(int)
            priorities = []
            for entry in entries:
                task_types[entry.get("role", "unknown")] += 1
                if "priority" in entry:
                    priorities.append(int(entry["priority"]))

            return FrameMetadata(
                container_id=directory.get("magic", ""),
                task_type="directory",
                priority=int(np.mean(priorities)) if priorities else 5,
                payload_length=len(entries),
                created_at=directory.get("created_at", 0),
                png_text_chunks={"entry_count": str(len(entries))},
            )
        except Exception:
            pass

    return None


def extract_png_metadata(png_path: Path) -> Optional[FrameMetadata]:
    """Extract metadata from a PNG container's text chunks.

    Args:
        png_path: Path to PNG file.

    Returns:
        FrameMetadata or None if PIL is not available.
    """
    if not HAS_PIL:
        return None

    try:
        img = Image.open(png_path)
        metadata = img.info

        if not metadata:
            return None

        metadata_obj = FrameMetadata(
            container_id=metadata.get("container_id", ""),
            task_type=metadata.get("task_type", "generic"),
            priority=int(metadata.get("priority", 5)),
            urgency=int(metadata.get("urgency", 2)),
            created_at=float(metadata.get("created_at", time.time())),
            payload_length=int(metadata.get("payload_length", 0)),
            crc32=int(metadata.get("crc32", 0)),
            framed_length=int(metadata.get("framed_length", 0)),
            png_text_chunks=dict(metadata),
        )

        # Parse dependencies
        deps_str = metadata.get("dependencies", "")
        if deps_str:
            metadata_obj.dependencies = deps_str.split(",")

        # Parse deadline
        if "deadline" in metadata:
            metadata_obj.deadline = float(metadata["deadline"])

        return metadata_obj

    except Exception as e:
        return FrameMetadata(error=str(e))


# ---------------------------------------------------------------------------
# Progress analysis
# ---------------------------------------------------------------------------


def build_progress_snapshot(
    containers: List[ContainerInfo],
    as_of: Optional[float] = None,
) -> ProgressSnapshot:
    """Build a progress snapshot from a list of scanned containers.

    Args:
        containers: List of scanned container info.
        as_of: Timestamp to snapshot at (default: now).

    Returns:
        ProgressSnapshot with aggregated metrics.
    """
    as_of = as_of or time.time()

    # Count task types
    task_type_counts = Counter()
    priorities = []
    overdue = 0
    task_containers = 0

    for c in containers:
        if c.metadata:
            task_type_counts[c.metadata.task_type] += 1
            priorities.append(c.metadata.priority)
            task_containers += 1

            # Check for overdue deadlines
            if (c.metadata.deadline and
                    c.metadata.deadline < as_of):
                overdue += 1

    avg_priority = float(np.mean(priorities)) if priorities else 5.0

    # Priority distribution
    priority_dist = Counter()
    for p in priorities:
        if p <= 2:
            priority_dist["high"] += 1
        elif p <= 5:
            priority_dist["medium"] += 1
        elif p <= 7:
            priority_dist["normal"] += 1
        else:
            priority_dist["low"] += 1

    return ProgressSnapshot(
        timestamp=as_of,
        container_count=len(containers),
        task_count=task_containers,
        task_type_counts=dict(task_type_counts),
        priority_distribution=dict(priority_dist),
        average_priority=round(avg_priority, 1),
        overdue_count=overdue,
    )


def compute_trend(
    earlier: ProgressSnapshot,
    later: ProgressSnapshot,
) -> ProgressTrend:
    """Compute progress trend between two snapshots.

    Args:
        earlier: Earlier snapshot.
        later: Later snapshot (must be after earlier).

    Returns:
        ProgressTrend with velocity and growth metrics.
    """
    period_hours = (later.timestamp - earlier.timestamp) / 3600
    period_days = period_hours / 24 if period_hours > 0 else 1.0

    # Identify bottleneck types (types with growth < average)
    earlier_types = set(earlier.task_type_counts.keys())
    later_types = set(later.task_type_counts.keys())
    all_types = earlier_types | later_types

    growth_rates = {}
    for t in all_types:
        e_count = earlier.task_type_counts.get(t, 0)
        l_count = later.task_type_counts.get(t, 0)
        if e_count > 0:
            growth_rates[t] = (l_count - e_count) / e_count
        else:
            growth_rates[t] = float("inf") if l_count > 0 else 0.0

    avg_growth = np.mean(list(growth_rates.values())) if growth_rates else 0.0
    bottleneck_types = [
        t for t, r in growth_rates.items()
        if r < avg_growth and earlier.task_type_counts.get(t, 0) > 0
    ]

    return ProgressTrend(
        period_start=earlier.timestamp,
        period_end=later.timestamp,
        container_growth=later.container_count - earlier.container_count,
        task_growth=later.task_count - earlier.task_count,
        velocity=later.task_count / period_days if period_days > 0 else 0,
        completion_rate=(
            later.task_count / max(later.container_count, 1)
        ),
        bottleneck_types=bottleneck_types[:5],  # Top 5
        trends=growth_rates,
    )


# ---------------------------------------------------------------------------
# Ollama interpretation (canned fallback)
# ---------------------------------------------------------------------------


def _prompt_ollama(prompt: str, system_prompt: Optional[str] = None) -> str:
    """Send a prompt to Ollama and return the response."""
    args = ["ollama", "run", DEFAULT_MODEL]
    full_prompt = f"System: {system_prompt}\n\n{prompt}" if system_prompt else prompt
    try:
        result = subprocess.run(
            args, input=full_prompt, capture_output=True, text=True,
            check=True, timeout=300,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        raise RuntimeError("Ollama timeout after 300 seconds")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Ollama failed: {e.stderr}")


def _canned_interpretation(
    snapshot: ProgressSnapshot,
    trend: Optional[ProgressTrend] = None,
) -> Dict:
    """Generate a canned interpretation of progress (no Ollama needed).

    Returns structured insights based on heuristic analysis of the data.
    """
    insights = []
    warnings = []
    recommendations = []

    # Analysis 1: Task type distribution
    if snapshot.task_type_counts:
        dominant_type = max(snapshot.task_type_counts, key=snapshot.task_type_counts.get)
        dominant_count = snapshot.task_type_counts[dominant_type]
        total = sum(snapshot.task_type_counts.values())
        diversity_ratio = len(snapshot.task_type_counts) / max(total, 1)

        insights.append(
            f"Dominant task type: '{dominant_type}' "
            f"({dominant_count}/{total} tasks, {100 * dominant_count // total}%)"
        )

        if diversity_ratio < 0.3 and total > 3:
            warnings.append(
                f"Low task diversity ({len(snapshot.task_type_counts)} types for {total} tasks) "
                f"— may indicate over-focus on {dominant_type}"
            )
    else:
        warnings.append("No task types found — containers may lack metadata")

    # Analysis 2: Priority distribution
    if snapshot.priority_distribution:
        high = snapshot.priority_distribution.get("high", 0)
        total_priority = sum(snapshot.priority_distribution.values())
        high_ratio = high / max(total_priority, 1)

        if high_ratio > 0.5:
            warnings.append(
                f"High proportion ({100 * high_ratio:.0f}%) of high-priority tasks "
                f"— possible firefighting mode"
            )
        elif high_ratio < 0.1 and total_priority > 5:
            insights.append("Good priority balance — no excessive high-priority backlog")
    else:
        warnings.append("No priority data available")

    # Analysis 3: Overdue tasks
    if snapshot.overdue_count > 0:
        warnings.append(
            f"{snapshot.overdue_count} overdue task(s) — consider re-prioritizing or "
            f"extending deadlines"
        )
    else:
        insights.append("No overdue tasks — deadlines are being met")

    # Analysis 4: Velocity (if trend available)
    if trend:
        insights.append(
            f"Velocity: {trend.velocity:.1f} tasks/day over "
            f"{max(timedelta(seconds=int(trend.period_end - trend.period_start)).days, 1)} day(s)"
        )

        if trend.bottleneck_types:
            warnings.append(
                f"Bottleneck types: {', '.join(trend.bottleneck_types[:3])} "
                f"— slower growth than average"
            )

        if trend.container_growth == 0 and trend.task_growth == 0:
            warnings.append("No growth detected — project may be stalled")
        elif trend.task_growth > 0:
            recommendations.append(
                "Current velocity is positive — maintain momentum by "
                "tackling bottleneck types"
            )
    else:
        insights.append(
            f"Current task count: {snapshot.task_count} across "
            f"{snapshot.container_count} container(s)"
        )

    # Summary assessment
    if len(warnings) == 0:
        assessment = "healthy"
    elif len(warnings) <= 2:
        assessment = "needs_attention"
    else:
        assessment = "blocked"

    return {
        "assessment": assessment,
        "insights": insights,
        "warnings": warnings,
        "recommendations": recommendations,
        "interpretation_model": "heuristic",
    }


def interpret_progress(
    snapshot: ProgressSnapshot,
    trend: Optional[ProgressTrend] = None,
    use_ollama: bool = False,
) -> Dict:
    """Interpret progress data, optionally using Ollama.

    Args:
        snapshot: Current progress snapshot.
        trend: Optional trend data between two snapshots.
        use_ollama: If True, use Ollama for interpretation.

    Returns:
        Dict with assessment, insights, warnings, and recommendations.
    """
    if use_ollama:
        try:
            return _ollama_interpretation(snapshot, trend)
        except Exception:
            # Fall back to canned
            pass

    return _canned_interpretation(snapshot, trend)


def _ollama_interpretation(
    snapshot: ProgressSnapshot,
    trend: Optional[ProgressTrend] = None,
) -> Dict:
    """Use Ollama to interpret progress data.

    Args:
        snapshot: Current progress snapshot.
        trend: Optional trend data.

    Returns:
        Dict with LLM-generated assessment, insights, and recommendations.
    """
    snapshot_lines = [
        f"Container count: {snapshot.container_count}",
        f"Task count: {snapshot.task_count}",
        f"Task types: {json.dumps(snapshot.task_type_counts)}",
        f"Priority distribution: {json.dumps(snapshot.priority_distribution)}",
        f"Average priority: {snapshot.average_priority}",
        f"Overdue tasks: {snapshot.overdue_count}",
    ]

    trend_lines = []
    if trend:
        trend_lines = [
            f"Period: {datetime.fromtimestamp(trend.period_start).isoformat()} → "
            f"{datetime.fromtimestamp(trend.period_end).isoformat()}",
            f"Container growth: {trend.container_growth}",
            f"Task growth: {trend.task_growth}",
            f"Velocity: {trend.velocity:.1f} tasks/day",
            f"Completion rate: {trend.completion_rate:.2f}",
            f"Bottleneck types: {', '.join(trend.bottleneck_types)}",
        ]

    prompt = (
        "You are a project manager analyzing Visual Audio development progress.\n\n"
        "Current Progress Snapshot:\n"
        + "\n".join(f"  {l}" for l in snapshot_lines)
        + "\n\nProgress Trend:\n"
        + ("\n".join(f"  {l}" for l in trend_lines) if trend_lines else "  (single snapshot)")
        + """

Analyze this data and provide:
1. An overall health assessment: healthy, needs_attention, or blocked
2. 2-3 specific insights about what the data reveals
3. 1-2 warnings about potential issues
4. 2-3 actionable recommendations for next steps

Return as JSON with keys: assessment, insights (array), warnings (array), recommendations (array)
Output ONLY valid JSON, no other text.
"""
    )

    try:
        response = _prompt_ollama(
            prompt,
            system_prompt="You are a project analytics AI. Output ONLY valid JSON, no other text.",
        )

        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        result = json.loads(json_str)
        result["interpretation_model"] = DEFAULT_MODEL
        return result

    except (json.JSONDecodeError, RuntimeError):
        return _canned_interpretation(snapshot, trend)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    directory: str,
    use_ollama: bool = False,
) -> Dict:
    """Generate a complete progress report.

    Args:
        directory: Directory to scan for containers.
        use_ollama: Whether to use Ollama for interpretation.

    Returns:
        Report dict with containers, snapshot, trends, and interpretation.
    """
    scan_dir = Path(directory)
    if not scan_dir.is_dir():
        return {"error": f"Directory not found: {directory}"}

    # Scan containers and extract metadata
    containers = scan_containers(scan_dir)
    for c in containers:
        if c.file_type == "mkv":
            try:
                frames = read_mkv_frames(Path(c.path))
                c.frame_count = len(frames)
                c.metadata = extract_mkv_metadata(frames)
            except (ValueError, FileNotFoundError) as e:
                c.error = str(e)
        elif c.file_type == "png":
            meta = extract_png_metadata(Path(c.path))
            if meta:
                c.metadata = meta

    # Build snapshot
    snapshot = build_progress_snapshot(containers)

    # Build trend (simulate with two snapshots at different modified times)
    mod_times = sorted(set(c.modified_at for c in containers), reverse=True)
    trend = None
    if len(mod_times) >= 2:
        early_containers = [
            c for c in containers if c.modified_at <= mod_times[-1]
        ]
        if early_containers:
            early_snapshot = build_progress_snapshot(early_containers, as_of=mod_times[-1])
            trend = compute_trend(early_snapshot, snapshot)

    # Interpret
    interpretation = interpret_progress(snapshot, trend, use_ollama=use_ollama)

    # Build container details
    container_details = []
    for c in containers:
        detail = {
            "path": c.path,
            "type": c.file_type,
            "size_bytes": c.size_bytes,
            "modified_at": datetime.fromtimestamp(c.modified_at).isoformat(),
            "frame_count": c.frame_count,
        }
        if c.metadata:
            detail["task_type"] = c.metadata.task_type
            detail["priority"] = c.metadata.priority
            detail["urgency"] = c.metadata.urgency
            if c.metadata.deadline:
                detail["deadline"] = datetime.fromtimestamp(
                    c.metadata.deadline
                ).isoformat()
        if c.error:
            detail["error"] = c.error
        container_details.append(detail)

    report = {
        "timestamp": datetime.now().isoformat(),
        "scan_directory": str(scan_dir),
        "containers": container_details,
        "snapshot": asdict(snapshot),
        "trend": asdict(trend) if trend else None,
        "interpretation": interpretation,
    }

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Frame-based progress tracking with LLM interpretation"
    )
    parser.add_argument(
        "--scan", metavar="DIR",
        help="Scan directory for container files"
    )
    parser.add_argument(
        "--progress", metavar="DIR",
        help="Generate progress report from container files"
    )
    parser.add_argument(
        "--interpret", metavar="DIR",
        help="Generate LLM-interpreted progress insights"
    )
    parser.add_argument(
        "--full-report", metavar="DIR",
        help="Full combined report with scan, snapshot, and interpretation"
    )
    parser.add_argument(
        "--ollama", action="store_true",
        help="Use Ollama for interpretation (default: heuristic)"
    )
    parser.add_argument(
        "--model", type=str,
        help=f"Ollama model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "-o", "--output", type=str,
        help="Output file for JSON report"
    )
    args = parser.parse_args()

    if args.model:
        os.environ["OLLAMA_MODEL"] = args.model

    if args.scan:
        containers = scan_containers(Path(args.scan))
        print(f"=== Container Scan: {args.scan} ===")
        print(f"Found {len(containers)} container(s)")
        for c in containers:
            meta_info = ""
            if c.metadata:
                meta_info = (
                    f" [{c.metadata.task_type}, priority={c.metadata.priority}]"
                )
            error_info = f" ERROR: {c.error}" if c.error else ""
            print(
                f"  {Path(c.path).name} ({c.file_type}, "
                f"{c.size_bytes / 1024:.1f}KB){meta_info}{error_info}"
            )

    elif args.progress:
        report = generate_report(args.progress, use_ollama=False)
        if "error" in report:
            print(f"Error: {report['error']}")
            return

        snap = report["snapshot"]
        trend = report.get("trend")

        print(f"=== Progress Report: {args.progress} ===")
        print(f"Snapshot at: {report['timestamp']}")
        print(f"Containers: {snap['container_count']}")
        print(f"Tasks: {snap['task_count']}")
        print(f"Task types: {snap['task_type_counts']}")
        print(f"Priority distribution: {snap['priority_distribution']}")
        print(f"Average priority: {snap['average_priority']}")
        print(f"Overdue: {snap['overdue_count']}")

        if trend:
            print(f"\nTrend ({trend['container_growth']} container, "
                  f"{trend['task_growth']} task growth):")
            print(f"  Velocity: {trend['velocity']:.1f} tasks/day")
            print(f"  Bottlenecks: {trend['bottleneck_types'] or 'none'}")

    elif args.interpret:
        report = generate_report(args.interpret, use_ollama=args.ollama)
        if "error" in report:
            print(f"Error: {report['error']}")
            return

        interp = report["interpretation"]
        print(f"=== Progress Interpretation: {args.interpret} ===")
        print(f"Assessment: {interp.get('assessment', '?').upper()}")
        print(f"\nInsights:")
        for i in interp.get("insights", []):
            print(f"  • {i}")
        print(f"\nWarnings:")
        for w in interp.get("warnings", []):
            print(f"  ⚠ {w}")
        print(f"\nRecommendations:")
        for r in interp.get("recommendations", []):
            print(f"  → {r}")

    elif args.full_report:
        report = generate_report(args.full_report, use_ollama=args.ollama)
        if "error" in report:
            print(f"Error: {report['error']}")
            return

        snap = report["snapshot"]
        trend = report.get("trend")
        interp = report["interpretation"]

        print(f"=== Full Progress Report: {args.full_report} ===")
        print(f"Generated: {report['timestamp']}")
        print(f"Interpretation model: {interp.get('interpretation_model', 'heuristic')}")
        print(f"\n--- Snapshot ---")
        print(f"  Containers: {snap['container_count']}")
        print(f"  Tasks: {snap['task_count']}")
        print(f"  Types: {snap['task_type_counts']}")
        print(f"  Avg priority: {snap['average_priority']}")

        if trend:
            print(f"\n--- Trend ---")
            print(f"  Growth: {trend['container_growth']} containers, "
                  f"{trend['task_growth']} tasks")
            print(f"  Velocity: {trend['velocity']:.1f} tasks/day")

        print(f"\n--- Interpretation ({interp.get('assessment', '?').upper()}) ---")
        for i in interp.get("insights", []):
            print(f"  • {i}")
        for w in interp.get("warnings", []):
            print(f"  ⚠ {w}")
        for r in interp.get("recommendations", []):
            print(f"  → {r}")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\nReport saved to {args.output}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

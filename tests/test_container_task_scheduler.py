#!/usr/bin/env python3
"""
test_container_task_scheduler.py — Tests for container task scheduler.

Verifies correct task prioritization based on frame metadata.
"""

import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PIL import Image, PngImagePlugin

from tools.task_scheduler import (
    TaskScheduler,
    TaskStatus,
    FrameMetadata,
    Task,
    scan_containers,
)


def create_test_container(
    output_path: Path,
    container_id: str,
    task_type: str = "generic",
    priority: int = 5,
    urgency: int = 2,
    dependencies: list | None = None,
    deadline: float | None = None,
) -> None:
    """
    Create a test container PNG with task metadata.

    Args:
        output_path: Output PNG path
        container_id: Container identifier
        task_type: Task type
        priority: Priority level (0-9)
        urgency: Urgency level (0-3)
        dependencies: List of dependency IDs
        deadline: Optional deadline timestamp
    """
    # Create a simple 10x10 RGBA image
    img = Image.new('RGBA', (10, 10), color=(255, 255, 255, 255))

    # Build metadata
    metadata = {
        'container_id': container_id,
        'task_type': task_type,
        'priority': str(priority),
        'urgency': str(urgency),
        'dependencies': ','.join(dependencies or []),
        'created_at': str(time.time()),
        'payload_length': '0',
        'crc32': '0',
        'framed_length': '0',
    }

    if deadline:
        metadata['deadline'] = str(deadline)

    # Save with metadata using PngInfo
    pnginfo = PngImagePlugin.PngInfo()
    for key, value in metadata.items():
        pnginfo.add_text(key, value)
    img.save(output_path, pnginfo=pnginfo)


def test_basic_task_queuing():
    """Test basic task queuing with different priorities."""
    print("TEST: Basic task queuing...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create containers with different priorities
        create_test_container(
            tmpdir / "low_priority.png",
            "task_low",
            task_type="test",
            priority=8,
            urgency=2,
        )

        create_test_container(
            tmpdir / "high_priority.png",
            "task_high",
            task_type="test",
            priority=1,
            urgency=2,
        )

        create_test_container(
            tmpdir / "medium_priority.png",
            "task_medium",
            task_type="test",
            priority=4,
            urgency=2,
        )

        # Create scheduler and add containers
        scheduler = TaskScheduler()
        scheduler.add_container(tmpdir / "low_priority.png")
        scheduler.add_container(tmpdir / "high_priority.png")
        scheduler.add_container(tmpdir / "medium_priority.png")

        # Get task queue
        queue = scheduler.get_task_queue()

        # Verify ordering (high priority first)
        assert len(queue) == 3, f"Expected 3 tasks, got {len(queue)}"
        assert queue[0].task_id == "task_high", f"Expected task_high first, got {queue[0].task_id}"
        assert queue[1].task_id == "task_medium", f"Expected task_medium second, got {queue[1].task_id}"
        assert queue[2].task_id == "task_low", f"Expected task_low third, got {queue[2].task_id}"

        # Verify all tasks are ready (no dependencies)
        for task in queue:
            assert task.status == TaskStatus.READY, f"Task {task.task_id} should be READY"

        print("  ✓ Tasks ordered correctly by priority")


def test_urgency_override():
    """Test that urgency affects priority score."""
    print("TEST: Urgency override...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Same priority, different urgency
        create_test_container(
            tmpdir / "normal_urgency.png",
            "task_normal",
            task_type="test",
            priority=5,
            urgency=2,  # normal
        )

        create_test_container(
            tmpdir / "high_urgency.png",
            "task_urgent",
            task_type="test",
            priority=5,
            urgency=1,  # high
        )

        create_test_container(
            tmpdir / "immediate_urgency.png",
            "task_immediate",
            task_type="test",
            priority=5,
            urgency=0,  # immediate
        )

        scheduler = TaskScheduler()
        scheduler.add_container(tmpdir / "normal_urgency.png")
        scheduler.add_container(tmpdir / "high_urgency.png")
        scheduler.add_container(tmpdir / "immediate_urgency.png")

        queue = scheduler.get_task_queue()

        # Urgency 0 should come first
        assert queue[0].task_id == "task_immediate", \
            f"Expected immediate urgency first, got {queue[0].task_id}"
        assert queue[1].task_id == "task_urgent", \
            f"Expected high urgency second, got {queue[1].task_id}"
        assert queue[2].task_id == "task_normal", \
            f"Expected normal urgency third, got {queue[2].task_id}"

        print("  ✓ Urgency correctly affects ordering")


def test_dependency_resolution():
    """Test dependency resolution."""
    print("TEST: Dependency resolution...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create tasks with dependencies
        # task_b depends on task_a
        # task_c depends on task_b
        create_test_container(
            tmpdir / "task_a.png",
            "task_a",
            task_type="test",
            priority=5,
            dependencies=[],
        )

        create_test_container(
            tmpdir / "task_b.png",
            "task_b",
            task_type="test",
            priority=5,
            dependencies=["task_a"],
        )

        create_test_container(
            tmpdir / "task_c.png",
            "task_c",
            task_type="test",
            priority=5,
            dependencies=["task_b"],
        )

        scheduler = TaskScheduler()
        scheduler.add_container(tmpdir / "task_a.png")
        scheduler.add_container(tmpdir / "task_b.png")
        scheduler.add_container(tmpdir / "task_c.png")

        # Check initial status
        task_a = scheduler.tasks["task_a"]
        task_b = scheduler.tasks["task_b"]
        task_c = scheduler.tasks["task_c"]

        assert task_a.status == TaskStatus.READY, "task_a should be READY (no deps)"
        assert task_b.status == TaskStatus.PENDING, "task_b should be PENDING (depends on task_a)"
        assert task_c.status == TaskStatus.PENDING, "task_c should be PENDING (depends on task_b)"

        # Complete task_a
        scheduler.mark_completed("task_a")

        # task_b should now be ready
        assert task_b.status == TaskStatus.READY, "task_b should be READY after task_a completed"
        assert task_c.status == TaskStatus.PENDING, "task_c should still be PENDING"

        # Complete task_b
        scheduler.mark_completed("task_b")

        # task_c should now be ready
        assert task_c.status == TaskStatus.READY, "task_c should be READY after task_b completed"

        print("  ✓ Dependencies resolved correctly")


def test_deadline_priority():
    """Test that deadline affects priority."""
    print("TEST: Deadline priority...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        now = time.time()

        # Create tasks with different deadlines
        create_test_container(
            tmpdir / "no_deadline.png",
            "task_no_deadline",
            task_type="test",
            priority=5,
            deadline=None,
        )

        create_test_container(
            tmpdir / "far_deadline.png",
            "task_far_deadline",
            task_type="test",
            priority=5,
            deadline=now + 86400 * 7,  # 7 days
        )

        create_test_container(
            tmpdir / "near_deadline.png",
            "task_near_deadline",
            task_type="test",
            priority=5,
            deadline=now + 1800,  # 30 minutes
        )

        create_test_container(
            tmpdir / "overdue_deadline.png",
            "task_overdue",
            task_type="test",
            priority=5,
            deadline=now - 3600,  # 1 hour ago
        )

        scheduler = TaskScheduler()
        scheduler.add_container(tmpdir / "no_deadline.png")
        scheduler.add_container(tmpdir / "far_deadline.png")
        scheduler.add_container(tmpdir / "near_deadline.png")
        scheduler.add_container(tmpdir / "overdue_deadline.png")

        queue = scheduler.get_task_queue()

        # Overdue should be first
        assert queue[0].task_id == "task_overdue", \
            f"Expected overdue task first, got {queue[0].task_id}"
        # Near deadline should be second
        assert queue[1].task_id == "task_near_deadline", \
            f"Expected near deadline second, got {queue[1].task_id}"

        print("  ✓ Deadlines correctly affect ordering")


def test_concurrency_limit():
    """Test concurrency limit enforcement."""
    print("TEST: Concurrency limit...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create multiple ready tasks
        for i in range(5):
            create_test_container(
                tmpdir / f"task_{i}.png",
                f"task_{i}",
                task_type="test",
                priority=i,
            )

        scheduler = TaskScheduler(max_concurrent=2)

        for i in range(5):
            scheduler.add_container(tmpdir / f"task_{i}.png")

        # Get tasks while respecting concurrency limit
        tasks_running = []
        while True:
            task = scheduler.get_next_task()
            if task is None:
                break
            scheduler.mark_running(task.task_id)
            tasks_running.append(task.task_id)

        # Should only get 2 tasks (concurrency limit)
        assert len(tasks_running) == 2, f"Expected 2 running tasks, got {len(tasks_running)}"

        print("  ✓ Concurrency limit enforced")


def test_statistics():
    """Test scheduler statistics."""
    print("TEST: Statistics...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mix of tasks
        create_test_container(tmpdir / "task1.png", "task1", priority=1)
        create_test_container(tmpdir / "task2.png", "task2", priority=2)
        create_test_container(tmpdir / "task3.png", "task3", priority=3)

        scheduler = TaskScheduler()
        scheduler.add_container(tmpdir / "task1.png")
        scheduler.add_container(tmpdir / "task2.png")
        scheduler.add_container(tmpdir / "task3.png")

        # Complete one task
        scheduler.mark_running("task1")
        scheduler.mark_completed("task1")

        # Mark one as failed
        scheduler.mark_running("task2")
        scheduler.mark_failed("task2", "test error")

        stats = scheduler.get_statistics()

        assert stats['total_tasks'] == 3, f"Expected 3 total tasks, got {stats['total_tasks']}"
        assert stats['completed'] == 1, f"Expected 1 completed, got {stats['completed']}"
        assert stats['failed'] == 1, f"Expected 1 failed, got {stats['failed']}"
        assert stats['ready'] == 1, f"Expected 1 ready, got {stats['ready']}"

        print("  ✓ Statistics calculated correctly")


def test_scan_containers():
    """Test container directory scanning."""
    print("TEST: Scan containers...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create some containers
        create_test_container(tmpdir / "container1.png", "task1")
        create_test_container(tmpdir / "container2.png", "task2")
        # Create a non-PNG file that should be ignored
        (tmpdir / "not_a_png.txt").write_text("test content")

        containers = scan_containers(tmpdir)

        assert len(containers) == 2, f"Expected 2 containers, got {len(containers)}"
        assert all(c.suffix == '.png' for c in containers), "All results should be PNG files"

        print("  ✓ Containers scanned correctly")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("Container Task Scheduler Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_basic_task_queuing,
        test_urgency_override,
        test_dependency_resolution,
        test_deadline_priority,
        test_concurrency_limit,
        test_statistics,
        test_scan_containers,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"  ✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
        print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == '__main__':
    import sys
    sys.exit(0 if run_all_tests() else 1)
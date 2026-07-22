"""
task_scheduler.py — Container task scheduler using frame metadata.

Reads PNG container metadata to prioritize and schedule tasks based on:
- Priority level (0-9, lower = higher priority)
- Urgency level (0-3, lower = higher urgency)
- Deadline (overdue tasks get highest priority)
- Dependencies (tasks wait for dependencies to complete)
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, PngImagePlugin


class TaskStatus(Enum):
    """Task execution status."""
    READY = "ready"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FrameMetadata:
    """Metadata extracted from PNG container."""
    container_id: str
    task_type: str
    priority: int = 5
    urgency: int = 2
    dependencies: List[str] = field(default_factory=list)
    created_at: float = 0.0
    deadline: Optional[float] = None
    payload_length: int = 0
    crc32: int = 0
    framed_length: int = 0


@dataclass
class Task:
    """Task representation."""
    task_id: str
    task_type: str
    priority: int
    urgency: int
    dependencies: List[str]
    created_at: float
    deadline: Optional[float]
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None

    @property
    def priority_score(self) -> float:
        """
        Calculate priority score for sorting.
        Lower score = higher priority.
        """
        score = float(self.priority) * 10.0

        # Urgency modifier: 0=immediate (-30), 1=high (-20), 2=normal (0), 3=low (+10)
        urgency_modifiers = {0: -30.0, 1: -20.0, 2: 0.0, 3: 10.0}
        score += urgency_modifiers.get(self.urgency, 0.0)

        # Deadline modifier
        if self.deadline:
            time_remaining = self.deadline - time.time()
            if time_remaining < 0:
                # Overdue: highest priority
                score -= 100.0
            elif time_remaining < 3600:
                # Less than 1 hour
                score -= 15.0
            elif time_remaining < 86400:
                # Less than 1 day
                score -= 5.0

        return score


class TaskScheduler:
    """
    Container task scheduler that reads frame metadata to prioritize and schedule tasks.
    """

    def __init__(self, max_concurrent: int = 4):
        """
        Initialize the task scheduler.

        Args:
            max_concurrent: Maximum number of tasks that can run concurrently
        """
        self.tasks: Dict[str, Task] = {}
        self.max_concurrent = max_concurrent

    def add_container(self, container_path: Path) -> None:
        """
        Add a PNG container to the scheduler.

        Args:
            container_path: Path to PNG container file
        """
        metadata = self._extract_metadata(container_path)

        # Check if task already exists
        if metadata.container_id in self.tasks:
            return

        # Create task
        task = Task(
            task_id=metadata.container_id,
            task_type=metadata.task_type,
            priority=metadata.priority,
            urgency=metadata.urgency,
            dependencies=metadata.dependencies,
            created_at=metadata.created_at,
            deadline=metadata.deadline,
        )

        self.tasks[task.task_id] = task
        self._update_task_status(task)

    def get_task_queue(self) -> List[Task]:
        """
        Get a sorted list of ready tasks.

        Returns:
            List of tasks sorted by priority score (highest priority first)
        """
        ready_tasks = [t for t in self.tasks.values() if t.status == TaskStatus.READY]
        ready_tasks.sort(key=lambda t: t.priority_score)
        return ready_tasks

    def get_next_task(self) -> Optional[Task]:
        """
        Get the next task to run, respecting concurrency limit.

        Returns:
            Next task to run, or None if no tasks available
        """
        running_count = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)

        if running_count >= self.max_concurrent:
            return None

        queue = self.get_task_queue()
        return queue[0] if queue else None

    def mark_running(self, task_id: str) -> None:
        """
        Mark a task as running.

        Args:
            task_id: Task identifier
        """
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()

    def mark_completed(self, task_id: str) -> None:
        """
        Mark a task as completed.

        Args:
            task_id: Task identifier
        """
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()

            # Update dependent tasks
            self._update_dependent_tasks(task_id)

    def mark_failed(self, task_id: str, error: str) -> None:
        """
        Mark a task as failed.

        Args:
            task_id: Task identifier
            error: Error message
        """
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            task.error = error

    def get_statistics(self) -> Dict[str, int]:
        """
        Get scheduler statistics.

        Returns:
            Dictionary with task counts
        """
        total = len(self.tasks)
        ready = sum(1 for t in self.tasks.values() if t.status == TaskStatus.READY)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        running = sum(1 for t in self.tasks.values() if t.status == TaskStatus.RUNNING)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)

        return {
            'total_tasks': total,
            'ready': ready,
            'pending': pending,
            'running': running,
            'completed': completed,
            'failed': failed,
        }

    def _extract_metadata(self, container_path: Path) -> FrameMetadata:
        """
        Extract metadata from PNG container.

        Args:
            container_path: Path to PNG container file

        Returns:
            FrameMetadata object
        """
        img = Image.open(container_path)

        # Get PNG metadata
        metadata = img.info

        container_id = metadata.get('container_id', '')
        task_type = metadata.get('task_type', 'generic')
        priority = int(metadata.get('priority', 5))
        urgency = int(metadata.get('urgency', 2))

        # Parse dependencies
        deps_str = metadata.get('dependencies', '')
        dependencies = deps_str.split(',') if deps_str else []

        created_at = float(metadata.get('created_at', time.time()))

        # Parse deadline
        deadline = None
        if 'deadline' in metadata:
            deadline = float(metadata['deadline'])

        payload_length = int(metadata.get('payload_length', 0))
        crc32 = int(metadata.get('crc32', 0))
        framed_length = int(metadata.get('framed_length', 0))

        return FrameMetadata(
            container_id=container_id,
            task_type=task_type,
            priority=priority,
            urgency=urgency,
            dependencies=dependencies,
            created_at=created_at,
            deadline=deadline,
            payload_length=payload_length,
            crc32=crc32,
            framed_length=framed_length,
        )

    def _update_task_status(self, task: Task) -> None:
        """
        Update task status based on dependencies.

        Args:
            task: Task to update
        """
        if not task.dependencies:
            task.status = TaskStatus.READY
            return

        # Check if all dependencies are completed
        all_complete = True
        for dep_id in task.dependencies:
            dep = self.tasks.get(dep_id)
            if dep is None or dep.status != TaskStatus.COMPLETED:
                all_complete = False
                break

        if all_complete:
            task.status = TaskStatus.READY
        else:
            task.status = TaskStatus.PENDING

    def _update_dependent_tasks(self, completed_task_id: str) -> None:
        """
        Update tasks that depend on a completed task.

        Args:
            completed_task_id: ID of the completed task
        """
        for task in self.tasks.values():
            if completed_task_id in task.dependencies:
                self._update_task_status(task)


def scan_containers(directory: Path) -> List[Path]:
    """
    Scan directory for PNG container files.

    Args:
        directory: Directory path to scan

    Returns:
        List of PNG file paths
    """
    if not directory.is_dir():
        return []

    return list(directory.glob('*.png'))


if __name__ == '__main__':
    # Example usage
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a simple test container
        img = Image.new('RGBA', (10, 10), color=(255, 255, 255, 255))
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text('container_id', 'test_task')
        pnginfo.add_text('task_type', 'test')
        pnginfo.add_text('priority', '1')
        pnginfo.add_text('urgency', '2')
        img.save(tmpdir / 'test.png', pnginfo=pnginfo)

        # Create scheduler and add container
        scheduler = TaskScheduler()
        scheduler.add_container(tmpdir / 'test.png')

        # Get task queue
        queue = scheduler.get_task_queue()
        print(f"Found {len(queue)} ready task(s)")
        for task in queue:
            print(f"  Task: {task.task_id}, Priority Score: {task.priority_score}")
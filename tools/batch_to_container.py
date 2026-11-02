#!/usr/bin/env python3
"""
Batch tool: Convert code files to pixels and add to container.

Usage:
    # Add all Python scripts from scripts/
    python3 tools/batch_to_container.py --source scripts/ --name-prefix scripts/

    # Add single file with custom name
    python3 tools/batch_to_container.py --source my_tool.py --name tools/my_tool.py

    # Verify all content entries
    python3 tools/batch_to_container.py --verify visual_audio.mkv
"""

import argparse
import subprocess
import sys
from pathlib import Path


def add_to_container(container_path: str, source: Path, name: str, role: str = "content", note: str = "") -> bool:
    """Add a file to the visual audio container."""
    result = subprocess.run([
        "python3", "tools/va_container.py", "add",
        container_path, str(source),
        "--name", name,
        "--role", role,
        "--note", note
    ], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"  ✓ Added: {name}")
        return True
    else:
        print(f"  ✗ Failed: {name}")
        print(f"    Error: {result.stderr}")
        return False


def batch_add(container_path: str, source_dir: Path, name_prefix: str = "", pattern: str = "*.py") -> dict:
    """Batch add files from directory to container."""
    source_files = list(source_dir.glob(pattern))
    
    if not source_files:
        print(f"No files matching '{pattern}' in {source_dir}")
        return {"added": 0, "failed": 0, "total": 0}
    
    print(f"Adding {len(source_files)} files from {source_dir} to {container_path}")
    print(f"Name prefix: {name_prefix}")
    
    results = {"added": 0, "failed": 0, "total": len(source_files)}
    
    for source_file in source_files:
        name = f"{name_prefix}{source_file.name}" if name_prefix else source_file.name
        note = f"Added from {source_dir}"
        
        if add_to_container(container_path, source_file, name, "content", note):
            results["added"] += 1
        else:
            results["failed"] += 1
    
    print(f"\nSummary: {results['added']}/{results['total']} added, {results['failed']} failed")
    return results


def verify_container(container_path: str) -> bool:
    """Verify all entries in container."""
    print(f"Verifying {container_path}...")
    
    result = subprocess.run([
        "python3", "tools/va_container.py", "verify",
        container_path
    ], capture_output=True, text=True)
    
    print(result.stdout)
    
    return result.returncode == 0


def list_container(container_path: str) -> None:
    """List all entries in container."""
    print(f"\nContainer contents: {container_path}")
    
    result = subprocess.run([
        "python3", "tools/va_container.py", "ls",
        container_path
    ], capture_output=True, text=True)
    
    print(result.stdout)


def run_from_container(container_path: str, name: str, args: list | None = None) -> bool:
    """Run code directly from container."""
    cmd = ["python3", "tools/va_container.py", "run", container_path, name]
    if args:
        cmd.extend(args)
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description="Batch convert code to pixels and add to visual_audio.mkv container"
    )
    
    parser.add_argument(
        "--container", "-c",
        default="visual_audio.mkv",
        help="Path to visual_audio.mkv container (default: visual_audio.mkv)"
    )
    
    parser.add_argument(
        "--source", "-s",
        type=Path,
        help="Source file or directory to add"
    )
    
    parser.add_argument(
        "--name", "-n",
        help="Custom name for single file (only with single file)"
    )
    
    parser.add_argument(
        "--name-prefix",
        default="",
        help="Prefix for names in batch mode (e.g., 'tools/')"
    )
    
    parser.add_argument(
        "--pattern", "-p",
        default="*.py",
        help="File pattern for batch mode (default: *.py)"
    )
    
    parser.add_argument(
        "--role", "-r",
        default="content",
        choices=["bootstrap", "spec", "codec", "state", "content", "test", "analysis", "engine", "cache"],
        help="Role for added files (default: content)"
    )
    
    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verify container after adding"
    )
    
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List container contents"
    )
    
    parser.add_argument(
        "--run",
        help="Run code from container by name"
    )
    
    args = parser.parse_args()
    
    # List container
    if args.list:
        list_container(args.container)
        return 0
    
    # Run from container
    if args.run:
        if run_from_container(args.container, args.run):
            return 0
        else:
            return 1
    
    # Verify container
    if args.verify and not args.source:
        if verify_container(args.container):
            return 0
        else:
            return 1
    
    # Add files
    if args.source:
        if args.source.is_file():
            # Single file
            name = args.name or args.source.name
            print(f"Adding single file: {args.source} → {name}")
            if add_to_container(args.container, args.source, name, args.role):
                print(f"✓ Successfully added {name}")
            else:
                print(f"✗ Failed to add {name}")
                return 1
        elif args.source.is_dir():
            # Batch mode
            results = batch_add(
                args.container,
                args.source,
                args.name_prefix,
                args.pattern
            )
            if results["failed"] > 0:
                return 1
        else:
            print(f"Error: {args.source} is not a file or directory")
            return 1
        
        # Verify after adding
        if args.verify:
            print()
            if not verify_container(args.container):
                return 1
        
        # Show updated contents
        print()
        list_container(args.container)
        
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
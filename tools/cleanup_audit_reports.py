#!/usr/bin/env python3
"""
Clean up old container audit reports
Retains recent reports and removes older ones to save disk space
"""

import os
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path

def parse_report_timestamp(filename):
    """Parse timestamp from audit report filename"""
    # Expected format: audit_report_YYYYMMDD_HHMMSS.json
    match = re.match(r'audit_report_(\d{8})_(\d{6})\.json', filename)
    if match:
        date_str = match.group(1)  # YYYYMMDD
        time_str = match.group(2)  # HHMMSS
        return datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
    return None

def cleanup_audit_reports(project_dir, retain_days=30, dry_run=False):
    """
    Clean up audit reports older than retain_days

    Args:
        project_dir: Path to Visual Audio project directory
        retain_days: Number of days to retain reports (default: 30)
        dry_run: If True, only print what would be deleted (default: False)

    Returns:
        Dictionary with cleanup statistics
    """
    project_path = Path(project_dir)
    if not project_path.exists():
        return {"error": f"Project directory not found: {project_dir}"}

    cutoff_date = datetime.now() - timedelta(days=retain_days)

    # Find all audit report files
    reports = []
    for file_path in project_path.glob("audit_report_*.json"):
        timestamp = parse_report_timestamp(file_path.name)
        if timestamp:
            reports.append((file_path, timestamp))
        else:
            reports.append((file_path, None))

    # Separate old and recent reports
    old_reports = []
    recent_reports = []

    for file_path, timestamp in reports:
        if timestamp and timestamp < cutoff_date:
            old_reports.append((file_path, timestamp))
        else:
            recent_reports.append((file_path, timestamp))

    # Delete old reports (or simulate in dry-run mode)
    deleted = []
    for file_path, timestamp in old_reports:
        if dry_run:
            print(f"[DRY RUN] Would delete: {file_path.name} (from {timestamp})")
            deleted.append(file_path)
        else:
            try:
                file_path.unlink()
                print(f"Deleted: {file_path.name} (from {timestamp})")
                deleted.append(file_path)
            except Exception as e:
                print(f"Error deleting {file_path.name}: {e}", file=sys.stderr)

    # Generate summary
    total_size = sum(fp.stat().st_size for fp, _ in reports if fp.exists())

    summary = {
        "total_reports": len(reports),
        "recent_reports": len(recent_reports),
        "old_reports": len(old_reports),
        "deleted_reports": len(deleted),
        "retained_reports": len(reports) - len(deleted),
        "retained_days": retain_days,
        "disk_freed_mb": round(sum(fp.stat().st_size for fp, _ in reports if fp in deleted) / (1024*1024), 2),
        "remaining_disk_mb": round(sum(fp.stat().st_size for fp, _ in reports if fp not in deleted) / (1024*1024), 2),
        "cutoff_date": cutoff_date.isoformat(),
        "dry_run": dry_run
    }

    return summary

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Clean up old container audit reports")
    parser.add_argument("--retain-days", type=int, default=30,
                       help="Number of days to retain reports (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Only print what would be deleted without actually deleting")
    parser.add_argument("--project-dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       help="Visual Audio project directory (default: auto-detected)")

    args = parser.parse_args()

    print(f"Container Audit Report Cleanup")
    print(f"Project directory: {args.project_dir}")
    print(f"Retention period: {args.retain_days} days")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'DELETE'}")
    print(f"{'='*60}")

    summary = cleanup_audit_reports(args.project_dir, args.retain_days, args.dry_run)

    if "error" in summary:
        print(f"Error: {summary['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print("Cleanup Summary:")
    print(f"{'='*60}")
    print(f"Total reports found:    {summary['total_reports']}")
    print(f"Recent reports (<{args.retain_days} days):   {summary['recent_reports']}")
    print(f"Old reports (>{args.retain_days} days):    {summary['old_reports']}")
    print(f"Reports deleted:        {summary['deleted_reports']}")
    print(f"Reports retained:       {summary['retained_reports']}")
    print(f"Disk freed:              {summary['disk_freed_mb']} MB")
    print(f"Remaining disk usage:    {summary['remaining_disk_mb']} MB")
    print(f"Cutoff date:            {summary['cutoff_date']}")

    if args.dry_run:
        print("\nDRY RUN MODE - No files were actually deleted")
        print("To delete files, run without --dry-run flag")

    sys.exit(0)

if __name__ == '__main__':
    main()
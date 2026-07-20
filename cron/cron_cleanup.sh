#!/bin/bash
# Cron wrapper script for audit report cleanup
# Install with: crontab -e
# Add: 0 3 * * * /home/jericho/projects/zion/projects/visual_audio/cron/cron_cleanup.sh >> /home/jericho/projects/zion/projects/visual_audio/audit.log 2>&1

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Log separator
echo "========================================"
echo "Audit Report Cleanup: $(date)"
echo "========================================"

# Run cleanup (retain reports for 30 days)
if python3 tools/cleanup_audit_reports.py --retain-days 30; then
    echo "Cleanup completed successfully"
else
    exit_code=$?
    echo "Cleanup completed with issues (exit code: $exit_code)"
    exit $exit_code
fi

echo "========================================"
echo "Cleanup run finished at $(date)"
echo "========================================"
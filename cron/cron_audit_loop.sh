#!/bin/bash
# Cron wrapper script for container audit loop
# Install with: crontab -e
# Add: 0 */2 * * * /home/jericho/projects/zion/projects/visual_audio/cron/cron_audit_loop.sh >> /home/jericho/projects/zion/projects/visual_audio/audit.log 2>&1

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Log separator
echo "========================================"
echo "Container Audit Loop: $(date)"
echo "========================================"

# Run audit
if python3 tools/container_audit.py; then
    echo "Audit completed successfully"
else
    exit_code=$?
    echo "Audit completed with issues (exit code: $exit_code)"
    # Continue to exit with the audit's exit code
    exit $exit_code
fi

echo "========================================"
echo "Audit run finished at $(date)"
echo "========================================"
#!/bin/bash
# Quick status check script for supervisor

echo "=== Alpine Boot Supervisor Status ==="
echo "Time: $(date)"
echo ""
echo "Supervisor log (last 10 lines):"
tail -10 /tmp/alpine_supervisor.log 2>/dev/null || echo "No supervisor log yet"
echo ""
echo "=== End ==="
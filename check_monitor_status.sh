#!/bin/bash
# Quick status check for Alpine boot monitor

echo "=== Alpine Boot Monitor Status ==="
echo ""
echo "Daemon process:"
ps aux | grep monitor_alpine_boot | grep -v grep
echo ""
echo "Recent log entries (tail 15):"
tail -15 /tmp/alpine_monitor.log
echo ""
echo "Current boot state:"
if [ -f alpine_boot_state.json ]; then
    echo "Iteration: $(jq -r '.state.iteration' alpine_boot_state.json)"
    echo "Best steps: $(jq -r '.state.last_working_step' alpine_boot_state.json)"
    echo "Applied fixes: $(jq -r '.state.applied_fixes | join(", ")' alpine_boot_state.json)"
else
    echo "No state file found"
fi
echo ""
echo "Monitor session data:"
if [ -f /tmp/alpine_monitor_session.jsonl ]; then
    echo "Last entry:"
    tail -1 /tmp/alpine_monitor_session.jsonl | jq '{steps, pc, halted, scause, tlb_hit_pct}'
else
    echo "No session data yet"
fi
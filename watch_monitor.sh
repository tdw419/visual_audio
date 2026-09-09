#!/bin/bash
# Continuous status monitoring for Alpine boot daemon

watch -n 30 '
echo "=== Alpine Boot Monitor Status ==="
echo "Time: $(date)"
echo ""
echo "Daemon process:"
ps aux | grep monitor_alpine_boot | grep -v grep || echo "Not running"
echo ""
echo "Recent log (last 10 lines):"
tail -10 /tmp/alpine_monitor.log 2>/dev/null || echo "No log yet"
echo ""
echo "Boot state:"
if [ -f alpine_boot_state.json ]; then
    echo "  Iteration: $(jq -r ".state.iteration" alpine_boot_state.json)"
    echo "  Best steps: $(jq -r ".state.last_working_step" alpine_boot_state.json)"
    echo "  Fixes: $(jq -r ".state.applied_fixes | join(\", \")" alpine_boot_state.json)"
fi
echo ""
echo "Monitor session:"
if [ -f /tmp/alpine_monitor_session.jsonl ]; then
    echo "  Last entry:"
    tail -1 /tmp/alpine_monitor_session.jsonl 2>/dev/null | jq "{steps, pc: (\"0x\" + (.pc | tostring)), scause, tlb_hit_pct}"
fi
echo ""
echo "=== Status End ==="
'
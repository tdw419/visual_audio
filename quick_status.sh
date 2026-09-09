#!/bin/bash
# Simple status checker - runs once and exits

echo "=== Alpine Boot Status ==="
echo "Time: $(date)"
echo ""

# Check daemon
DAEMON_PID=$(pgrep -f monitor_alpine_boot)
if [ -n "$DAEMON_PID" ]; then
    echo "✓ Monitor daemon running (PID: $DAEMON_PID)"
else
    echo "✗ Monitor daemon NOT running"
fi
echo ""

# Check current monitor session
MONITOR_PID=$(pgrep -f "monitor_rv64i.py.*alpine")
if [ -n "$MONITOR_PID" ]; then
    echo "✓ Monitor session running (PID: $MONITOR_PID)"
    # Get uptime
    UPTIME=$(ps -p $MONITOR_PID -o etime= | tr -d ' ')
    echo "  Uptime: $UPTIME"
else
    echo "✗ No monitor session running"
fi
echo ""

# Check boot state
if [ -f alpine_boot_state.json ]; then
    ITER=$(jq -r ".state.iteration" alpine_boot_state.json)
    BEST=$(jq -r ".state.last_working_step" alpine_boot_state.json)
    FIXES=$(jq -r ".state.applied_fixes | join(\", \")" alpine_boot_state.json)
    echo "Boot state from JSON:"
    echo "  Iteration: $ITER"
    echo "  Best progress: $(printf "%'d" $BEST) steps"
    echo "  Fixes applied: $FIXES"
else
    echo "No boot state file found"
fi
echo ""

# Check monitor session data
if [ -f /tmp/alpine_monitor_session.jsonl ]; then
    LINES=$(wc -l < /tmp/alpine_monitor_session.jsonl)
    echo "Monitor session data: $LINES entries"
    if [ $LINES -gt 0 ]; then
        echo "Latest metrics:"
        tail -1 /tmp/alpine_monitor_session.jsonl | jq "{steps, pc: (\"0x\" + (.pc | tostring)), halted, scause, tlb_hit_pct}"
    fi
else
    echo "No monitor session data yet"
fi
echo ""

# Check old monitor output
if [ -f /tmp/alpine_500m_state.jsonl ]; then
    OLD_LINES=$(wc -l < /tmp/alpine_500m_state.jsonl)
    echo "Legacy monitor data: $OLD_LINES entries"
    if [ $OLD_LINES -gt 0 ]; then
        echo "Latest legacy metrics:"
        tail -1 /tmp/alpine_500m_state.jsonl | jq "{steps, pc: (\"0x\" + (.pc | tostring)), scause, tlb_hit_pct}"
    fi
fi
echo ""
echo "=== End Status ==="
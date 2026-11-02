#!/bin/bash
# Overnight watchdog for boot_xv6_gpu.py: this sandbox has a known real GPU
# compute submission hang (not the emulated CPU stalling - the actual GPU
# dispatch freezing, seen 2026-08-25 mid-run). A plain long-timeout run just
# sits hung forever with no signal. This wrapper detects "no new Iter line
# in $STALL_SECS" and kills+restarts the boot process, appending to one
# cumulative log, until MAX_RUNTIME is reached or a real result appears
# (stall dump / shell prompt / crash).
set -u
cd "$(dirname "$0")"

LOG=/tmp/xv6_state_dump_overnight.log
STALL_SECS=180
MAX_RUNTIME=$((8*3600))
START=$(date +%s)
RESTART_COUNT=0

: > "$LOG"

is_done() {
    grep -q "Full CPU state dump\|Working-set stall detected\|CPU PC stall detected\|xv6 kernel is booting\|\\$ $" "$LOG" 2>/dev/null
}

while true; do
    NOW=$(date +%s)
    if [ $((NOW - START)) -ge $MAX_RUNTIME ]; then
        echo "[watchdog] MAX_RUNTIME reached, stopping." >> "$LOG"
        break
    fi

    echo "[watchdog] Launching boot_xv6_gpu.py (restart #$RESTART_COUNT)..." >> "$LOG"
    python3 boot_xv6_gpu.py /tmp/xv6-riscv/kernel/kernel --stall-threshold 200 >> "$LOG" 2>&1 &
    CHILD=$!

    LAST_LINES=0
    LAST_PROGRESS=$(date +%s)

    while kill -0 "$CHILD" 2>/dev/null; do
        sleep 15
        NOW=$(date +%s)
        if [ $((NOW - START)) -ge $MAX_RUNTIME ]; then
            kill -9 "$CHILD" 2>/dev/null
            echo "[watchdog] MAX_RUNTIME reached mid-run, stopping." >> "$LOG"
            exit 0
        fi
        if is_done; then
            echo "[watchdog] Conclusive result found, letting process finish/stopping." >> "$LOG"
            sleep 5
            kill "$CHILD" 2>/dev/null
            exit 0
        fi
        CUR_LINES=$(grep -c "^    Iter" "$LOG" 2>/dev/null || echo 0)
        if [ "$CUR_LINES" -gt "$LAST_LINES" ]; then
            LAST_LINES=$CUR_LINES
            LAST_PROGRESS=$NOW
        elif [ $((NOW - LAST_PROGRESS)) -ge $STALL_SECS ]; then
            echo "[watchdog] No progress in ${STALL_SECS}s (GPU dispatch hang) - killing and restarting." >> "$LOG"
            kill -9 "$CHILD" 2>/dev/null
            sleep 2
            break
        fi
    done

    if is_done; then
        break
    fi
    RESTART_COUNT=$((RESTART_COUNT + 1))
done

echo "[watchdog] Final state after $RESTART_COUNT restart(s):" >> "$LOG"
tail -5 "$LOG" >> "$LOG"

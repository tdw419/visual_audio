# NBD Boot Debugging Patterns

## Which Script Writes Which Log

When investigating NBD boot failures, verify you're looking at the right file:

| Script | Log File | Purpose |
|--------|----------|---------|
| `test_nbd_boot.sh` | `/tmp/qemu_serial_nbd.log` | NBD-backed boot evidence |
| Traditional boot | `/tmp/qemu_serial.log` | Direct virtio-blk boot (STALE reference) |

**CRITICAL**: Never verify NBD boot success by looking at `/tmp/qemu_serial.log`. That file is for traditional boot and will contain unrelated stale output from earlier sessions. Always use `/tmp/qemu_serial_nbd.log`.

## Stale-Log Race in test_nbd_boot.sh

### The Bug

The `grep -q "ubuntu login:" /tmp/qemu_serial_nbd.log` check could succeed against a stale log file from a previous run if:
1. The previous NBD boot succeeded and left `/tmp/qemu_serial_nbd.log` with `ubuntu login:` in it
2. A subsequent boot attempt crashes or stalls before overwriting the log
3. The grep finds the old `ubuntu login:` line and reports FALSE SUCCESS

### Fix Applied

Added an mtime guard that only accepts log files modified within the last 10 minutes:

```bash
# Run with timestamp guard
RUN_START=$(date +%s)
timeout 300 bash -c 'until grep -q "ubuntu login:" /tmp/qemu_serial_nbd.log 2>/dev/null; do sleep 2; echo -n "."; done' || true

# Verify log freshness before declaring success
LOG_AGE=$(( $(date +%s) - $(stat -c %Y /tmp/qemu_serial_nbd.log 2>/dev/null || echo 0) ))
if [ "$LOG_AGE" -gt 600 ]; then
    echo "FAILED: Log file is stale (${LOG_AGE}s old)"
    exit 1
fi
```

This prevents false-positive claims based on evidence from previous sessions.

## Evidence Verification Checklist

When claiming NBD boot success, verify:

- [ ] Log file is `/tmp/qemu_serial_nbd.log`, NOT `/tmp/qemu_serial.log`
- [ ] Log file mtime is AFTER the run start time (check with `stat -c %Y`)
- [ ] Log file contains `ubuntu login:` line
- [ ] No I/O errors in log (`grep -i "I/O error"` returns nothing)
- [ ] No sector errors in log (`grep "I/O error, dev" /path/to/log` returns nothing)
- [ ] Tile timestamps are BEFORE the boot attempt (tiles must exist before boot)
- [ ] NBD server was running during the boot (`ss -tulnp | grep 10809`)

## Current Status (2026-08-23)

### V4.1 Tiled NBD Boot

**Status**: ✅ WORKING — reaches login, 3 verified runs

**Evidence Paths**:
- Fresh logs: `/tmp/qemu_serial_nbd.log`, `/tmp/qemu_serial_nbd_2105_run.log`, `/tmp/qemu_serial_manual.log`
- Stale reference (NEVER use for NBD): `/tmp/qemu_serial.log` (16:06 timestamp, traditional boot)

**Tile Fix Timestamp**: 2026-08-23 20:31:03 (re-encoded 331 tiles)

**Verified Boot Timestamps**:
- `/tmp/qemu_serial_nbd.log`: 2026-08-23 21:25:10
- `/tmp/qemu_serial_nbd_2105_run.log`: 2026-08-23 21:13:xx
- `/tmp/qemu_serial_manual.log`: 2026-08-23 21:20:xx

**Result**: All three boots reached `ubuntu login:` with zero I/O errors. Partition detection completed normally. System fully functional.

## Known Issues to Fix

1. **NBD server connection resilience**: Drop dead connections so hung clients (stale parted/nbd-client) don't block guest I/O
2. **Initramfs cosmetic fix**: Remove "No block devices found" message by dropping `/dev/sd*` from ls glob (trivial)
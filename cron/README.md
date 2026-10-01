# Visual Audio Cron Jobs

This directory contains cron job scripts for automated Visual Audio operations.

## Installation

### Method 1: Direct Crontab Entry

Edit crontab:
```bash
crontab -e
```

Add entry for container audit loop (runs every 2 hours):
```cron
0 */2 * * * /home/jericho/projects/zion/projects/visual_audio/cron/cron_audit_loop.sh >> /home/jericho/projects/zion/projects/visual_audio/audit.log 2>&1
```

### Method 2: Using Cron.d (System-wide)

Create system cron entry:
```bash
sudo ln -s /home/jericho/projects/zion/projects/visual_audio/cron/cron_audit_loop.sh /etc/cron.d/visual-audio-audit
sudo chmod 644 /etc/cron.d/visual-audio-audit
```

## Available Cron Jobs

### cron_audit_loop.sh

**Purpose**: Runs container audit loop periodically

**Schedule**: Every 2 hours (configurable)

**Output**: Appends to `audit.log` in project root

**What it does**:
1. Runs `python3 tools/container_audit.py`
2. Logs timestamped execution
3. Captures both stdout and stderr
4. Propagates exit code (0 = clean, 1 = issues found)

## Customizing Schedule

Edit the crontab entry to change frequency:

```cron
# Every hour
0 * * * * ...

# Every 6 hours
0 */6 * * * ...

# Daily at midnight
0 0 * * * ...

# Weekdays at 9 AM
0 9 * * 1-5 ...
```

## Monitoring

View audit logs:
```bash
tail -f audit.log
```

View recent audit reports:
```bash
ls -lt audit_report_*.json | head -5
```

## Troubleshooting

### Cron Not Running

Check cron service:
```bash
sudo systemctl status cron
```

### Environment Variables

Cron jobs run with minimal environment. If scripts need specific environment:

```bash
# Add to crontab
PATH=/usr/local/bin:/usr/bin:/bin
PYTHONPATH=/home/jericho/projects/zion/projects/visual_audio
```

### Permission Denied

Ensure scripts are executable:
```bash
chmod +x cron/cron_audit_loop.sh
```

## Available Cron Jobs

### cron_audit_loop.sh

**Purpose**: Runs container audit loop periodically

**Schedule**: Every 2 hours (configurable)

**Output**: Appends to `audit.log` in project root

**What it does**:
1. Runs `python3 tools/container_audit.py`
2. Logs timestamped execution
3. Captures both stdout and stderr
4. Propagates exit code (0 = clean, 1 = issues found)

### cron_cleanup.sh

**Purpose**: Cleans up old audit reports to save disk space

**Schedule**: Daily at 3 AM (recommended)

**Output**: Appends to `audit.log` in project root

**What it does**:
1. Runs `python3 tools/cleanup_audit_reports.py`
2. Deletes reports older than 30 days (configurable)
3. Reports disk space freed

Add to crontab:
```cron
0 3 * * * /home/jericho/projects/zion/projects/visual_audio/cron/cron_cleanup.sh >> /home/jericho/projects/zion/projects/visual_audio/audit.log 2>&1
```

## References

- TASK_A003: Automated container audit loop
- docs/container_audit_loop.md
- AGENTS.md: Visual Audio Agent Constitution

---

**Last Updated**: 2026-07-20
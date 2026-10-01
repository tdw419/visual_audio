# Cron Infrastructure Operations Guide

**Generated:** 2026-07-19T17:37:56.382167
**Status:** Complete

## Overview
This guide provides operational procedures for the Hermes cron infrastructure,
including job management, monitoring, and troubleshooting.

## Architecture

### Job Classification
- **LLM-Heavy Jobs**: Jobs that spawn LLM agents (concurrency limited to 2)
- **Script-Only Jobs**: Pure shell/Python scripts marked with `no_agent=true`
- **Shell-Wrapped Jobs**: Complex command pipelines
- **Repeat-Limited Jobs**: Jobs with execution count limits

### Priority Tiers
- **P0**: Critical infrastructure (no concurrency limits)
- **P1**: High priority autonomous agents
- **P2**: Regular automated tasks
- **P3**: Background monitoring and reporting

### Concurrency Management
- Maximum 2 concurrent LLM jobs (GPU constraint: 24GB total, 8GB per qwen2.5-coder:14b)
- Script-only jobs have no concurrency limits
- Priority queue ensures P0 jobs always execute first

## Operations

### Job Management
```bash
# List all cron jobs
hermes cronjob action='list'

# Add a new job
hermes cronjob add <name> --schedule "*/5 * * * *" --command "python script.py"

# Remove a job
hermes cronjob remove <name>

# Mark job as script-only
hermes cronjob update <name> --no_agent=true
```

### Monitoring
```bash
# View cron health dashboard
firefox ~/.hermes/hermes-agent/cron_dashboard.svg

# Regenerate dashboard
python3 ~/.hermes/hermes-agent/cron_dashboard_generator.py

# View cron logs
hermes logs --level ERROR | grep cron
```

### Troubleshooting
- **High Error Rate**: Check schedule overlaps, verify concurrency limits
- **Resource Exhaustion**: Monitor GPU usage with `nvidia-smi`
- **Stuck Jobs**: Check for repeat limits, verify job dependencies

## Success Metrics
- Error Rate < 5%
- Max 2 concurrent LLM jobs
- 95% of jobs staggered
- All script-only jobs marked `no_agent=true`


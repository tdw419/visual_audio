#!/bin/bash
# pixel_linux_exit.sh — reverse of pixel_linux_enter.sh: kill v5_interactive
# and restore the normal Ubuntu desktop (gdm).
set -e

echo "Stopping v5_interactive..."
sudo pkill -TERM -x v5_interactive 2>/dev/null || echo "  (not running)"
sleep 1
sudo pkill -KILL -x v5_interactive 2>/dev/null || true

echo "Starting gdm..."
sudo systemctl start gdm

for i in $(seq 1 15); do
    if systemctl is-active --quiet gdm; then
        echo "gdm active."
        break
    fi
    sleep 1
done

systemctl status gdm --no-pager | head -5

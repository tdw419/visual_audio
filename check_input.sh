#!/bin/bash
set -e

# Check input devices in VM
sshpass -p "israel" ssh -p 2222 -o StrictHostKeyChecking=no root@localhost << 'EOF'
echo "=== /dev/input event devices ==="
ls -la /dev/input/event* 2>/dev/null || echo "No event devices found"

echo ""
echo "=== Device info ==="
for dev in /dev/input/event* 2>/dev/null; do
    echo "Device: $dev"
    udevadm info --attribute-walk --name=$dev 2>/dev/null | grep -E "ID_INPUT|ID_BUS|ID_VENDOR|ID_MODEL" | head -4
    echo "---"
done
EOF

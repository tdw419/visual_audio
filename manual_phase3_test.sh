#!/usr/bin/env bash
# Manual Phase 3 Testing Script
# Run this inside the Ubuntu VM with sudo privileges
#
# This script requires:
# 1. sudo access (enter password when prompted)
# 2. The v5_interactive binary built and deployed

set -euo pipefail

echo "=========================================="
echo "Phase 3: Interactive Input Manual Test"
echo "=========================================="
echo ""

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    echo "✓ Running as root"
else
    echo "⚠ Not running as root, will use sudo"
    SUDO="sudo"
fi

# Stop gdm to release DRM master
echo ""
echo "Step 1: Stopping GDM (releases DRM master)..."
echo "Sudo password required:"
$SUDO systemctl stop gdm
sleep 1
echo "✓ GDM stopped"

# Check for DRM device
echo ""
echo "Step 2: Checking DRM devices..."
DRI_DEVICES=(/dev/dri/card*)
if [ ${#DRI_DEVICES[@]} -eq 0 ]; then
    echo "❌ No DRM devices found"
    exit 1
fi
DRI_CARD=${DRI_DEVICES[0]}
echo "✓ Using DRM device: $DRI_CARD"

# Check for input devices
echo ""
echo "Step 3: Checking input devices..."
INPUT_DEVICES=(/dev/input/event*)
if [ ${#INPUT_DEVICES[@]} -eq 0 ]; then
    echo "❌ No input devices found"
    exit 1
fi

# Try to identify mouse device
for dev in "${INPUT_DEVICES[@]}"; do
    if sudo udevadm info --name="$dev" 2>/dev/null | grep -qi "mouse\|ps/2"; then
        INPUT_DEV=$dev
        break
    fi
done

if [ -z "${INPUT_DEV:-}" ]; then
    INPUT_DEV=${INPUT_DEVICES[0]}
    echo "⚠ Could not identify mouse, using: $INPUT_DEV"
else
    echo "✓ Using input device: $INPUT_DEV"
fi

# Check for v5_interactive binary
echo ""
echo "Step 4: Checking for v5_interactive binary..."
if [ -f "/opt/geos_pixel_v5/v5_interactive" ]; then
    BINARY="/opt/geos_pixel_v5/v5_interactive"
elif [ -f "/tmp/v5_interactive" ]; then
    BINARY="/tmp/v5_interactive"
else
    echo "❌ v5_interactive binary not found"
    echo "   Run deploy_interactive.sh first"
    exit 1
fi
echo "✓ Found binary: $BINARY"

# Run v5_interactive
echo ""
echo "Step 5: Starting v5_interactive..."
echo ""
echo "=========================================="
echo "  INTERACTIVE TESTING INSTRUCTIONS"
echo "=========================================="
echo ""
echo "The window system will display:"
echo "  - RED window at (50, 50)"
echo "  - GREEN window at (100, 100)"
echo "  - BLUE window at (20, 20)"
echo ""
echo "TEST 1: Click Test"
echo "  → Click on the RED window"
echo "  → Expected: RED window raises to top (z-order)"
echo ""
echo "TEST 2: Drag Test"
echo "  → Click and drag the GREEN window"
echo "  → Expected: GREEN window moves following mouse"
echo ""
echo "Press Ctrl+C to exit"
echo ""
echo "=========================================="
echo ""

V5_DRI_CARD="$DRI_CARD" \
V5_INPUT_DEVICE="$INPUT_DEV" \
$SUDO "$BINARY"

# Restart gdm on exit
echo ""
echo "Restarting GDM..."
$SUDO systemctl start gdm
echo "✓ GDM restarted"

echo ""
echo "=========================================="
echo "Test completed"
echo "=========================================="
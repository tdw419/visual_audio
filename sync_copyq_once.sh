#!/bin/bash
# One-time CopyQ sync: copy host data to guest
set -e

echo "=== One-time CopyQ Sync: Host to Guest ==="
echo ""

HOST_COPYQ_DATA="/host_zion/projects/visual_audio/.copyq_sync_from_host"
GUEST_COPYQ_DATA="$HOME/.config/copyq"

# Copy host data to guest
if [ -d "$HOST_COPYQ_DATA" ] && [ "$(ls -A "$HOST_COPYQ_DATA" 2>/dev/null)" ]; then
    echo "Copying host CopyQ data to guest..."
    mkdir -p "$GUEST_COPYQ_DATA"
    cp -r "$HOST_COPYQ_DATA"/* "$GUEST_COPYQ_DATA/" 2>/dev/null || true
    echo "✓ CopyQ data synced from host"
else
    echo "No host CopyQ data found at $HOST_COPYQ_DATA"
    echo "Starting with fresh CopyQ instance..."
fi

echo ""
echo "Sync complete. CopyQ is ready in the guest."
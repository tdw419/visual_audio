#!/bin/bash
# One-time CopyQ sync: copy host data to shared directory
set -e

echo "=== One-time CopyQ Sync: Host to Shared ==="
echo ""

PROJECT_ROOT="/home/jericho/zion/projects/visual_audio"
SHARED_DATA="$PROJECT_ROOT/.copyq_sync_from_host"

# Copy host CopyQ data to shared location
mkdir -p "$SHARED_DATA"
if [ -d "$HOME/.config/copyq" ] && [ "$(ls -A "$HOME/.config/copyq" 2>/dev/null)" ]; then
    echo "Copying host CopyQ data to shared directory..."
    cp -r "$HOME/.config/copyq"/* "$SHARED_DATA/" 2>/dev/null || true
    echo "✓ CopyQ data copied to $SHARED_DATA"
else
    echo "No existing CopyQ data found on host"
    echo "Creating empty sync directory..."
fi

echo ""
echo "Run this in the guest VM to complete the sync:"
echo "  /host_zion/projects/visual_audio/sync_copyq_once.sh"
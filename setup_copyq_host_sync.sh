#!/bin/bash
# Configure CopyQ host instance to sync with guest via shared data directory
set -e

echo "=== CopyQ Host-Guest Sync Setup ==="
echo ""

PROJECT_ROOT="/home/jericho/zion/projects/visual_audio"
SHARED_DATA="$PROJECT_ROOT/.copyq_shared"
SHARED_CONFIG="$PROJECT_ROOT/.copyq_config"

# Create shared directories
mkdir -p "$SHARED_DATA"
mkdir -p "$SHARED_CONFIG"

echo "✓ Created shared directories:"
echo "  Data:   $SHARED_DATA"
echo "  Config: $SHARED_CONFIG"
echo ""

# Stop CopyQ if running
if pgrep -x copyq > /dev/null; then
    echo "Stopping existing CopyQ instance..."
    pkill -x copyq
    sleep 2
fi

# Copy existing host config if available
if [ -d ~/.config/copyq ] && [ "$(ls -A ~/.config/copyq 2>/dev/null)" ]; then
    echo "Copying existing host configuration to shared location..."
    cp -r ~/.config/copyq/* "$SHARED_CONFIG/"
fi

echo "=== CopyQ Host Sync Configuration Complete ==="
echo ""
echo "IMPORTANT NOTES:"
echo "- Host and guest share the same CopyQ data directory"
echo "- DO NOT run CopyQ on both host and guest simultaneously"
echo "- Use this script to start CopyQ with shared data:"
echo "  $PROJECT_ROOT/start_copyq_host_sync.sh"
echo ""
echo "To start CopyQ manually:"
echo "  copyq -d $SHARED_DATA -c $SHARED_CONFIG &"
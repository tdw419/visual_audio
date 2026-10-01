#!/bin/bash
# Start CopyQ host instance with shared data directory for guest sync
set -e

PROJECT_ROOT="/home/jericho/zion/projects/visual_audio"
SHARED_DATA="$PROJECT_ROOT/.copyq_shared"
SHARED_CONFIG="$PROJECT_ROOT/.copyq_config"

# Check if shared directories exist
if [ ! -d "$SHARED_DATA" ] || [ ! -d "$SHARED_CONFIG" ]; then
    echo "Error: Shared directories not found. Run setup script first:"
    echo "  $PROJECT_ROOT/setup_copyq_host_sync.sh"
    exit 1
fi

# Stop existing CopyQ instances
if pgrep -x copyq > /dev/null; then
    echo "Stopping existing CopyQ instance..."
    pkill -x copyq
    sleep 2
fi

echo "=== Starting CopyQ with Guest Sync ==="
echo "Data:   $SHARED_DATA"
echo "Config: $SHARED_CONFIG"
echo ""

# Start CopyQ with shared configuration
copyq -d "$SHARED_DATA" -c "$SHARED_CONFIG" &

echo "✓ CopyQ started with guest sync enabled"
echo ""
echo "IMPORTANT: Do not start CopyQ on the guest while this is running!"
#!/bin/bash
# Configure CopyQ guest instance to sync with host via shared data directory
set -e

echo "=== CopyQ Guest-Host Sync Setup ==="
echo ""

SHARED_DATA="/host_zion/projects/visual_audio/.copyq_shared"
SHARED_CONFIG="/host_zion/projects/visual_audio/.copyq_config"

# Create shared directories on host side
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

# Remove existing CopyQ data and config directories
echo "Removing existing CopyQ directories..."
rm -rf ~/.local/share/copyq/copyq
rm -rf ~/.config/copyq

# Create symbolic links
echo "Creating symbolic links..."
ln -s "$SHARED_DATA" ~/.local/share/copyq/copyq
ln -s "$SHARED_CONFIG" ~/.config/copyq

echo "✓ Symbolic links created:"
echo "  ~/.local/share/copyq/copyq -> $SHARED_DATA"
echo "  ~/.config/copyq -> $SHARED_CONFIG"
echo ""

# Verify setup
echo "Verifying setup..."
ls -la ~/.local/share/copyq/
ls -la ~/.config/

echo ""
echo "=== CopyQ Sync Configuration Complete ==="
echo ""
echo "IMPORTANT NOTES:"
echo "- Guest changes to shared directories are immediately visible on host"
echo "- Avoid running CopyQ simultaneously on both guest and host (conflict risk)"
echo "- Guest CopyQ will store all data in: $SHARED_DATA"
echo "- Host can access the same data directory"
echo ""
echo "To start CopyQ in the guest:"
echo "  copyq &"
echo ""
echo "To sync from host, run CopyQ with the same data directory:"
echo "  copyq -d $SHARED_DATA -c $SHARED_CONFIG"
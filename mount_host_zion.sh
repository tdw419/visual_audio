#!/bin/bash
#
# mount_host_zion.sh - Mount /host_zion in the guest VM
#
# Usage:
#   ./mount_host_zion.sh [port]
#
# Default port: 2222
#

SSH_PORT="${1:-2222}"
SSH_USER="jericho"

echo "Mounting /host_zion in guest..."

ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "${SSH_USER}@localhost" << 'EOF'
  # Create mount point if needed
  sudo mkdir -p /host_zion
  
  # Mount the 9p filesystem
  if ! mount | grep -q host_zion; then
    sudo mount -t 9p -o trans=virtio,version=9p2000.L host_zion /host_zion
    
    if [ $? -eq 0 ]; then
      echo "✓ /host_zion mounted successfully"
      echo "Contents:"
      ls -la /host_zion | head -5
    else
      echo "✗ Mount failed"
      echo "Available 9p devices:"
      mount | grep 9p || echo "None found - reboot VM with a launcher that includes the virtfs option (e.g., interactive_ubuntu_pixel.sh)"
    fi
  else
    echo "✓ /host_zion already mounted"
    ls -la /host_zion | head -5
  fi
EOF
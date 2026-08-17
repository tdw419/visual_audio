#!/bin/bash
# Rebuild cognitive initramfs with PXC1 support

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INITRAMFS_DIR="$PROJECT_ROOT/initramfs-cognitive"

cd "$INITRAMFS_DIR"

echo "=== Updating initramfs with PXC1 support ==="

# Replace the extractor script
echo "[1] Updating extract_cognitive.py → extract_cognitive_pxc1.py..."
cp extract_cognitive_pxc1.py extract_cognitive.py

# Update init script to use PXC1
echo "[2] Updating init script..."
cat > init << 'EOF'
#!/bin/sh
# PXC1 Cognitive Boot Init Script

mount -t proc none /proc
mount -t sysfs none /sys
mount -t devtmpfs none /dev

echo "=== Geometry OS PXC1 Cognitive Boot ==="

# Load VirtIO block module
echo "Loading VirtIO block module..."
insmod /lib/modules/virtio_blk.ko || echo "Warning: virtio_blk.ko load failed"

# Wait for block device
echo "Waiting for /dev/vda..."
while [ ! -b /dev/vda ]; do
    sleep 0.5
done

echo "✓ Block device found: /dev/vda"

# Create /tmp/cognitive
mkdir -p /tmp/cognitive

# Run PXC1 extractor
echo "Running PXC1 cognitive extractor..."
export PYTHONPATH=/usr/lib/python3.12/site-packages:/usr/lib/python3.12:/usr/local/lib
python3 /bin/extract_cognitive.py

# If we get here, extraction failed
echo "❌ Cognitive extraction failed!"
poweroff -f
EOF

# Rebuild initramfs
echo "[3] Rebuilding initramfs..."
./build.sh

if [ $? -eq 0 ]; then
    echo ""
    echo "=== Initramfs Updated Successfully ==="
    echo "New initramfs: $INITRAMFS_DIR/output/initramfs-cognitive.gz"
    echo ""
    echo "Next: Re-encode PXC1 container with updated initramfs"
    echo "  ./encode_ubuntu_pxc1.sh"
else
    echo ""
    echo "=== Initramfs Build Failed ==="
    exit 1
fi
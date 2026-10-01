#!/bin/bash
set -e

WORK_DIR="/home/jericho/projects/zion/projects/visual_audio/minimal_image_build"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== Building Minimal Bootable Image (Debian) ==="

DISK="minimal_boot.img"
SIZE="2G"
ROOTDIR="rootfs"

if [ ! -f "$DISK" ]; then
    echo "Creating $SIZE disk image..."
    qemu-img create -f qcow2 "$DISK" "$SIZE"

    echo "Creating minimal filesystem..."
    mkdir -p "$ROOTDIR"
    debootstrap --arch=amd64 stable "$ROOTDIR" http://deb.debian.org/debian/

    echo "Setting up basic configuration..."
    # Set hostname
    echo "minimal" > "$ROOTDIR/etc/hostname"

    # Configure fstab
    cat > "$ROOTDIR/etc/fstab" << 'EOF'
/dev/vda1 / ext4 errors=remount-ro 0 1
/dev/vda2 none swap sw 0 0
EOF

    # Configure serial console
    cat > "$ROOTDIR/etc/inittab" << 'EOF'
T0:23:respawn:/sbin/getty -L ttyS0 115200 vt100
EOF

    # Create minimal user
    chroot "$ROOTDIR" useradd -m -s /bin/bash user

    # Clean up
    umount "$ROOTDIR/dev/pts" "$ROOTDIR/dev" "$ROOTDIR/proc" "$ROOTDIR/sys" 2>/dev/null || true

    # Copy to disk
    echo "Installing to disk image..."
    qemu-nbd -c /dev/nbd0 "$DISK"
    sleep 1

    # Create partition table
    (
        echo o # New MBR
        echo n # New partition
        echo p # Primary
        echo 1 # Partition 1
        echo   # First sector default
        echo   # Last sector default
        echo a # Bootable
        echo w # Write
    ) | fdisk /dev/nbd0 >/dev/null 2>&1
    sleep 1

    # Format and copy
    mkfs.ext4 -F /dev/nbd0p1
    mkdir -p disk_mount
    mount /dev/nbd0p1 disk_mount
    cp -a "$ROOTDIR"/* disk_mount/
    umount disk_mount
    qemu-nbd -d /dev/nbd0

    echo "✓ Image created: $DISK"
else
    echo "Image exists: $DISK"
fi

echo ""
echo "Testing boot..."
cd /home/jericho/projects/zion/projects/visual_audio
timeout 30 qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -drive file="$WORK_DIR/$DISK",format=qcow2,if=virtio \
    -nographic -serial mon:stdio 2>&1 || echo "Boot test complete"
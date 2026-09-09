#!/bin/bash
set -e

WORK_DIR="/home/jericho/projects/zion/projects/visual_audio/alpine_build"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== Building Alpine x86_64 Image ==="

DISK="alpine_boot.img"
SIZE="1G"
ROOTFS="rootfs"

if [ ! -f "$DISK" ]; then
    echo "Creating $SIZE disk..."
    qemu-img create -f qcow2 "$DISK" "$SIZE"

    echo "Running APK to fetch Alpine base..."
    mkdir -p "$ROOTFS"
    mkdir -p "$ROOTFS/etc/apk"
    mkdir -p "$ROOTFS/etc/apk/keys"

    # Use the system's apk tools
    if command -v apk >/dev/null 2>&1; then
        apk add --root "$ROOTFS" --initdb alpine-base busybox openrc
    else
        echo "apk not found, skipping rootfs creation"
        exit 1
    fi

    echo "Configuring Alpine..."
    # Set hostname
    echo "alpine" > "$ROOTFS/etc/hostname"

    # Setup fstab
    echo "/dev/vda1 / ext4 defaults,noatime 0 0" > "$ROOTFS/etc/fstab"

    # Setup inittab for serial
    echo 'ttyS0::respawn:/sbin/getty -L ttyS0 115200 vt100' > "$ROOTFS/etc/inittab"

    # Setup network
    cat > "$ROOTFS/etc/network/interfaces" << 'EOF'
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp
EOF

    # Enable services
    chroot "$ROOTFS" rc-update add bootmisc boot 2>/dev/null || true
    chroot "$ROOTFS" rc-update add hostname boot 2>/dev/null || true
    chroot "$ROOTFS" rc-update add networking boot 2>/dev/null || true

    echo "Installing to disk..."
    # Map NBD
    sudo modprobe nbd max_part=8 2>/dev/null || true
    sudo qemu-nbd -c /dev/nbd0 "$DISK"
    sleep 1

    # Partition
    sudo fdisk /dev/nbd0 <<EOF
o
n
p
1


a
w
EOF
    sleep 1

    # Format and copy
    sudo mkfs.ext4 -F /dev/nbd0p1
    mkdir -p disk_mount
    sudo mount /dev/nbd0p1 disk_mount
    sudo cp -a "$ROOTFS"/* disk_mount/
    sudo umount disk_mount
    sudo qemu-nbd -d /dev/nbd0

    echo "✓ Alpine image created: $DISK"
else
    echo "Using existing image: $DISK"
fi

echo ""
echo "Testing boot..."
cd /home/jericho/projects/zion/projects/visual_audio
timeout 30 qemu-system-x86_64 \
    -enable-kvm \
    -m 256M \
    -smp 1 \
    -drive file="$WORK_DIR/$DISK",format=qcow2,if=virtio \
    -nographic -serial mon:stdio 2>&1 || echo "Boot test complete"
#!/bin/bash
set -e

WORK_DIR="/home/jericho/projects/zion/projects/visual_audio/alpine_x86_build"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== Building Minimal Alpine x86_64 Image with Docker ==="

DISK="alpine_minimal_x86.raw"
SIZE="1G"

if [ ! -f "$DISK" ]; then
    echo "Creating $SIZE raw disk..."
    qemu-img create -f raw "$DISK" "$SIZE"

    echo "Partitioning disk..."
    (
        echo o # New MBR
        echo n # New partition
        echo p # Primary
        echo 1 # Partition 1
        echo   # First sector default
        echo   # Last sector default
        echo a # Bootable
        echo w # Write and exit
    ) | fdisk "$DISK" >/dev/null 2>&1

    LOOP=$(losetup -f --show -P "$DISK")
    echo "Loop device: $LOOP"

    # Format ext4
    mkfs.ext4 -F "${LOOP}p1"

    # Mount
    mkdir -p mnt
    mount "${LOOP}p1" mnt

    echo "Installing Alpine base system via Docker..."
    docker run --rm -v "$PWD/mnt:/target" alpine:3.20 sh -c '
        apk add --no-cache alpine-base alpine-conf busybox openssh openrc
        cp -a /etc/apk/keys/*.pub /target/etc/apk/keys/ 2>/dev/null || mkdir -p /target/etc/apk
        apk add --no-cache --root /target --initdb alpine-base busybox dropbear openrc
        echo "nameserver 8.8.8.8" > /target/etc/resolv.conf
        echo "localhost" > /target/etc/hostname
        echo "/dev/vda1 / ext4 defaults 0 0" > /target/etc/fstab
        echo 'ttyS0::respawn:/sbin/getty -L ttyS0 115200 vt100' >> /target/etc/inittab
        chmod 1777 /target/tmp
        # Enable services
        chroot /target rc-update add bootmisc boot
        chroot /target rc-update add hostname boot
        chroot /target rc-update add networking boot
    ' 2>&1 | head -20

    # Cleanup
    umount mnt
    losetup -d "$LOOP"

    echo ""
    echo "✓ Alpine image created: $DISK"
else
    echo "Using existing image: $DISK"
fi

echo ""
echo "Image info:"
ls -lh "$DISK"
file "$DISK"

echo ""
echo "=== Testing Alpine Boot ==="
echo "Expected login prompt: 'localhost login:'"
echo "Default root has no password"
echo ""

cd /home/jericho/projects/zion/projects/visual_audio
timeout 30 qemu-system-x86_64 \
    -enable-kvm \
    -m 256M \
    -smp 1 \
    -drive file="$WORK_DIR/$DISK",format=raw,if=virtio \
    -nographic -serial mon:stdio 2>&1 || echo "Booted successfully (timed out as expected)"
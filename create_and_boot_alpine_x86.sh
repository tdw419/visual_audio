#!/bin/bash
set -e

WORK_DIR="/home/jericho/projects/zion/projects/visual_audio/alpine_x86_install"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== Creating Minimal Alpine x86_64 Image ==="

# Create disk
DISK="alpine_minimal_x86.img"
if [ ! -f "$DISK" ]; then
    echo "Creating 2G raw disk..."
    qemu-img create -f raw "$DISK" 2G

    # Partition and format
    echo "Partitioning disk..."
    (
        echo o # Create new MBR
        echo n # New partition
        echo p # Primary
        echo 1 # Partition 1
        echo   # First sector (default)
        echo   # Last sector (default)
        echo a # Make bootable
        echo w # Write
    ) | fdisk "$DISK" 2>/dev/null || true

    # Setup loop device
    LOOP=$(losetup -f --show -P "$DISK")
    echo "Loop device: $LOOP"

    # Format as ext4
    mkfs.ext4 -F "${LOOP}p1"

    # Mount and install Alpine base
    mkdir -p mnt
    mount "${LOOP}p1" mnt

    echo "Installing Alpine base system..."
    # Use apk from the ISO
    mkdir -p mnt/boot
    mkdir -p mnt/dev
    mkdir -p mnt/proc
    mkdir -p mnt/sys

    # Copy APK keys
    mkdir -p mnt/etc/apk
    cp /etc/apk/keys/*.pub mnt/etc/apk/keys/ 2>/dev/null || true

    # Install base
    apk add --root mnt --initdb --arch x86_64 alpine-base alpine-conf openrc

    # Setup basic config
    echo "Setting up basic config..."
    chroot mnt /bin/sh -c "rc-update add bootmisc boot"
    chroot mnt /bin/sh -c "rc-update add networking boot"
    chroot mnt /bin/sh -c "rc-update add sshd default"

    # Create fstab
    echo "/dev/vda1 / ext4 defaults 0 0" > mnt/etc/fstab

    # Enable serial console
    echo "ttyS0::respawn:/sbin/getty -L ttyS0 115200 vt100" >> mnt/etc/inittab

    # Cleanup
    umount mnt
    losetup -d "$LOOP"
    echo ""
    echo "✓ Alpine minimal image created: $DISK"
else
    echo "Image already exists: $DISK"
fi

echo ""
echo "Image info:"
ls -lh "$DISK"
file "$DISK"

echo ""
echo "=== Booting Alpine x86_64 ==="
echo "Press Ctrl-A X to exit from QEMU monitor"

cd /home/jericho/projects/zion/projects/visual_audio
qemu-system-x86_64 \
    -enable-kvm \
    -m 512M \
    -smp 1 \
    -drive file="$WORK_DIR/$DISK",format=raw,if=virtio \
    -nographic -serial mon:stdio \
    -no-reboot
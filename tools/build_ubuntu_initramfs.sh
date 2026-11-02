#!/bin/bash
set -e

# Create a minimal initramfs for booting Ubuntu rootfs
WORKDIR="/tmp/initramfs_ubuntu"
OUTPUT="/home/jericho/projects/zion/projects/visual_audio/boot_images/tiny_x86_ubuntu_initramfs.gz"

echo "Building minimal Ubuntu-booting initramfs..."
# Clean and create work directory
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"

cd "$WORKDIR"

# Create directory structure
mkdir -p bin etc proc sys sbin usr/bin usr/sbin dev

# Find and copy busybox
BUSYBOX=$(which busybox)
if [ -z "$BUSYBOX" ]; then
    echo "ERROR: busybox not found"
    exit 1
fi

echo "Using busybox: $BUSYBOX"
cp "$BUSYBOX" bin/busybox
chmod +x bin/busybox

# Create init script
cat > init << 'INIT_EOF'
#!/bin/sh
# Init script to boot Ubuntu rootfs from /dev/vdb
echo "=== V4 Bootloader Initramfs ==="
echo "Scanning for block devices..."

# Install busybox applets
/bin/busybox --install -s /bin

# Mount essential filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev

# Wait for devices to settle
sleep 2

echo "Available block devices:"
ls -la /dev/vd* 2>/dev/null || echo "No /dev/vd* devices found"

# Find the Ubuntu rootfs partition
# Try common partition names for the second virtio disk
ROOT_DEV=""
for dev in /dev/vda1 /dev/vda2 /dev/vda3 /dev/vda4 /dev/vdb /dev/vdb1 /dev/vdb2 /dev/vdb3 /dev/vdb4 /dev/vdc /dev/vdc1 /dev/vdc2 /dev/vdc3 /dev/vdc4 /dev/vdd /dev/vdd1; do
    if [ -e "$dev" ]; then
        echo "Checking $dev..."
        
        # Try to detect filesystem type
        fstype=$(blkid -o value -s TYPE "$dev" 2>/dev/null)
        
        if [ "$fstype" = "ext4" ]; then
            echo "Found ext4 filesystem on $dev"
            ROOT_DEV="$dev"
            break
        fi
        
        # Also try mounting it to see if it works
        mkdir -p /test_mount
        if mount -t ext4 -o ro "$dev" /test_mount 2>/dev/null; then
            echo "Successfully mounted $dev as ext4"
            ROOT_DEV="$dev"
            umount /test_mount
            break
        fi
    fi
done

if [ -z "$ROOT_DEV" ]; then
    echo "ERROR: Could not find Ubuntu rootfs partition!"
    echo "Falling back to emergency shell"
    exec /bin/sh
fi

echo "Using root device: $ROOT_DEV"

# Create mountpoint
mkdir -p /newroot

# Mount the root filesystem
echo "Mounting $ROOT_DEV to /newroot..."
mount -t ext4 -o ro "$ROOT_DEV" /newroot

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to mount root filesystem!"
    exec /bin/sh
fi

# Verify that systemd/init exists
if [ ! -x /newroot/sbin/init ] && [ ! -x /newroot/lib/systemd/systemd ]; then
    echo "ERROR: No init found in /newroot!"
    echo "Contents of /newroot:"
    ls -la /newroot | head -20
    exec /bin/sh
fi

echo "Rootfs mounted successfully. Switching to real root..."

# Switch to the new root
exec switch_root /newroot /sbin/init

# If we get here, something went wrong
echo "ERROR: switch_root failed!"
exec /bin/sh
INIT_EOF

chmod +x init

# Build the initramfs
echo "Creating initramfs..."
find . | cpio -o -H newc | gzip > "$OUTPUT"

echo "✓ Initramfs created: $OUTPUT"
ls -lh "$OUTPUT"
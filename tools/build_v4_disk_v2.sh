#!/bin/bash
set -ex

PROJECT_ROOT="/home/jericho/projects/zion/projects/visual_audio"
DISK_IMG="/tmp/ubuntu_v4_efi_v2.img"
RAW_DATA="/tmp/ubuntu_v4_minimal_payload.img"
BOOTLOADER_EFI="$PROJECT_ROOT/systems/target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi"
MOUNT_POINT="/tmp/v4_esp_mount_v2"

# Clean up previous mounts
[ -d "$MOUNT_POINT" ] && sudo umount "$MOUNT_POINT" 2>/dev/null || true
rm -rf "$MOUNT_POINT"

# Detach any loop devices
for dev in $(losetup -j "$DISK_IMG" 2>/dev/null | awk '{print $1}' | cut -d: -f1); do
    sudo losetup -d "$dev" 2>/dev/null || true
done

# Remove old disk image
rm -f "$DISK_IMG"

# Build V4 payload if it doesn't exist
if [ ! -f "$RAW_DATA" ]; then
    echo "Building V4 payload..."
    python3 "$PROJECT_ROOT/tools/build_minimal_v4.py"
fi

# Create new disk image (256MB total)
dd if=/dev/zero of="$DISK_IMG" bs=1M count=256 2>/dev/null

# Partition the disk
echo "Creating GPT partitions..."
sgdisk -Z "$DISK_IMG"
sgdisk -o "$DISK_IMG"

ESP_START_SECTOR=2048
ESP_SIZE_MB=64
ESP_SECTORS=$((ESP_SIZE_MB * 1024 * 1024 / 512))
DATA_START_SECTOR=$((ESP_START_SECTOR + ESP_SECTORS))

# Create partitions
sgdisk -n 1:$ESP_START_SECTOR:+$((ESP_SECTORS - 1)) "$DISK_IMG"
sgdisk -n 2:$DATA_START_SECTOR:0 "$DISK_IMG"

# Set partition types
ESP_GUID="C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
DATA_GUID="0FC63DAF-8483-4772-8E79-3D69D8477DE4"
sgdisk -t 1:$ESP_GUID "$DISK_IMG"
sgdisk -t 2:$DATA_GUID "$DISK_IMG"

# Set bootable flag on ESP
sgdisk -A 1:set:2 "$DISK_IMG"

echo "Partitions created:"
sgdisk -p "$DISK_IMG"

# Setup ESP
ESP_OFFSET=$((ESP_START_SECTOR * 512))
ESP_SIZE_BYTES=$((ESP_SECTORS * 512))

echo "Setting up ESP at offset $ESP_OFFSET..."
LOOP_DEV=$(sudo losetup -f --show -o $ESP_OFFSET --sizelimit $ESP_SIZE_BYTES "$DISK_IMG")
sudo mkfs.vfat -F 32 "$LOOP_DEV"

# Mount and copy bootloader
sudo mkdir -p "$MOUNT_POINT"
sudo mount "$LOOP_DEV" "$MOUNT_POINT"
sudo mkdir -p "$MOUNT_POINT/EFI/BOOT"
sudo cp "$BOOTLOADER_EFI" "$MOUNT_POINT/EFI/BOOT/BOOTX64.EFI"
sync
sudo umount "$MOUNT_POINT"
sudo losetup -d "$LOOP_DEV"

# Setup data partition with V4 payload
DATA_OFFSET=$((DATA_START_SECTOR * 512))
echo "Writing V4 payload to partition 2 at offset $DATA_OFFSET..."

# Write payload directly to the partition offset
dd if="$RAW_DATA" of="$DISK_IMG" bs=1 seek=$DATA_OFFSET conv=notrunc

echo "=== V4 disk created successfully ==="
echo "Disk image: $DISK_IMG"
echo ""
echo "Verifying V4BOOT00 magic:"
dd if="$DISK_IMG" bs=1 skip=$DATA_OFFSET count=8 2>/dev/null | od -A x -t x1z
echo ""
echo "To boot:"
echo "  bash test_v4_ubuntu_rootfs.sh"
echo "(update test_v4_ubuntu_rootfs.sh to use $DISK_IMG)"
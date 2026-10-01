#!/bin/bash
set -ex

# Paths
PROJECT_ROOT="/home/jericho/projects/zion/projects/visual_audio"
DISK_IMG="/tmp/ubuntu_v4_efi_new.img"
RAW_DATA="/tmp/ubuntu_v4_raw_data_new.img"
BOOTLOADER_EFI="$PROJECT_ROOT/systems/target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi"
MOUNT_POINT="/tmp/v4_esp_mount_new"

# Check bootloader exists
if [ ! -f "$BOOTLOADER_EFI" ]; then
    echo "ERROR: Bootloader not found at $BOOTLOADER_EFI"
    echo "Please build it first: cd systems/v4_bootloader_x86 && cargo build --target x86_64-unknown-uefi --release"
    exit 1
fi

# Remove old files
rm -f "$DISK_IMG" "$RAW_DATA"
rm -rf "$MOUNT_POINT"

# Create raw data image (64MB for kernel+initramfs PDB data)
# This is the data that will go into partition 2
dd if=/dev/zero of="$RAW_DATA" bs=1M count=64 2>/dev/null

# Create new disk image (256MB total)
dd if=/dev/zero of="$DISK_IMG" bs=1M count=256 2>/dev/null

# Partition the disk
sgdisk -Z "$DISK_IMG"  # Zap old partition table
sgdisk -o "$DISK_IMG"  # Create new GPT

ESP_START_SECTOR=2048
ESP_SIZE_MB=64
ESP_SECTORS=$((ESP_SIZE_MB * 1024 * 1024 / 512))
DATA_START_SECTOR=$((ESP_START_SECTOR + ESP_SECTORS))

# Create partitions
sgdisk -n 1:$ESP_START_SECTOR:+$((ESP_SECTORS - 1)) "$DISK_IMG"  # EFI System Partition
sgdisk -n 2:$DATA_START_SECTOR:0 "$DISK_IMG"                    # Data partition

# Set partition types
ESP_GUID="C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
DATA_GUID="0FC63DAF-8483-4772-8E79-3D69D8477DE4"
sgdisk -t 1:$ESP_GUID "$DISK_IMG"
sgdisk -t 2:$DATA_GUID "$DISK_IMG"

# Set bootable flag on ESP
sgdisk -A 1:set:2 "$DISK_IMG"

# Setup ESP (EFI System Partition)
ESP_OFFSET=$((ESP_START_SECTOR * 512))
ESP_SIZE_BYTES=$((ESP_SECTORS * 512))

# Create loop device for ESP
LOOP_DEV=$(losetup -f --show -o $ESP_OFFSET --sizelimit $ESP_SIZE_BYTES "$DISK_IMG")
mkfs.vfat -F 32 "$LOOP_DEV"
mkdir -p "$MOUNT_POINT"
mount "$LOOP_DEV" "$MOUNT_POINT"
mkdir -p "$MOUNT_POINT/EFI/BOOT"
cp "$BOOTLOADER_EFI" "$MOUNT_POINT/EFI/BOOT/BOOTX64.EFI"
umount "$MOUNT_POINT"
losetup -d "$LOOP_DEV"

# Setup data partition (V4BOOT00 format)
DATA_OFFSET=$((DATA_START_SECTOR * 512))
DATA_SIZE=$((64 * 1024 * 1024))  # 64MB

# Create loop device for data partition
LOOP_DEV=$(losetup -f --show -o $DATA_OFFSET --sizelimit $DATA_SIZE "$DISK_IMG")

# Copy raw data to partition
dd if="$RAW_DATA" of="$LOOP_DEV" bs=1M 2>/dev/null
losetup -d "$LOOP_DEV"

echo "=== V4 disk created successfully ==="
echo "Disk image: $DISK_IMG"
echo "Now you need to:"
echo "1. Build the V4BOOT00 payload (kernel+initramfs PDBs)"
echo "2. Write it to the data partition at offset $DATA_OFFSET"
echo ""
echo "To inspect:"
echo "  sgdisk -p $DISK_IMG"
echo "  dd if=$DISK_IMG bs=1 skip=$DATA_OFFSET count=8 2>/dev/null | od -A x -t x1z"
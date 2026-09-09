#!/bin/bash
set -e
RAW_DATA="/tmp/ubuntu_v4_x86.img"
DISK_IMG="/tmp/ubuntu_v4_efi.img"
BOOTLOADER_EFI="/home/jericho/projects/zion/projects/visual_audio/systems/target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi"
MOUNT_POINT="/tmp/v4_esp_mount"

rm -f "$DISK_IMG"
rm -rf "$MOUNT_POINT"

# Align to 1MB
RAW_SIZE=$(stat -c%s "$RAW_DATA")
TOTAL_SIZE=$(( (RAW_SIZE + 1048575) / 1048576 * 1048576 + 128 * 1024 * 1024 ))
truncate -s $TOTAL_SIZE "$DISK_IMG"

parted -s "$DISK_IMG" mklabel gpt
parted -s "$DISK_IMG" mkpart primary fat32 1MiB 65MiB
parted -s "$DISK_IMG" set 1 esp on
parted -s "$DISK_IMG" mkpart primary ext4 65MiB 100%

LOOP_DEV=$(losetup -f)
losetup -P "$LOOP_DEV" "$DISK_IMG"

mkfs.vfat -F 32 "${LOOP_DEV}p1"
mkdir -p "$MOUNT_POINT"
mount "${LOOP_DEV}p1" "$MOUNT_POINT"
mkdir -p "$MOUNT_POINT/EFI/BOOT"
cp "$BOOTLOADER_EFI" "$MOUNT_POINT/EFI/BOOT/BOOTX64.EFI"
umount "$MOUNT_POINT"

dd if="$RAW_DATA" of="${LOOP_DEV}p2" bs=1M 2>/dev/null

losetup -d "$LOOP_DEV"

chmod 666 "$DISK_IMG"
echo "=== COMPLETE ==="

#!/bin/bash
set -e
RAW_DATA="/tmp/ubuntu_v4_raw_data.img"
if [ -f "/tmp/ubuntu_v4_efi.img" ]; then
    mv "/tmp/ubuntu_v4_efi.img" "$RAW_DATA"
fi

DISK_IMG="/tmp/ubuntu_v4_efi.img"
BOOTLOADER_EFI="/home/jericho/projects/zion/projects/visual_audio/systems/target/x86_64-unknown-uefi/release/bootloader_uefi_v4.efi"
MOUNT_POINT="/tmp/v4_esp_mount"

rm -f "$DISK_IMG"
rm -rf "$MOUNT_POINT"

dd if=/dev/zero of="$DISK_IMG" bs=1M count=256 2>/dev/null
sgdisk -Z "$DISK_IMG"
sgdisk -o "$DISK_IMG"

ESP_START_SECTOR=2048
ESP_SIZE_MB=64
ESP_SECTORS=$((ESP_SIZE_MB * 1024 * 1024 / 512))
DATA_START_SECTOR=$((ESP_START_SECTOR + ESP_SECTORS))

sgdisk -n 1:$ESP_START_SECTOR:+$((ESP_SECTORS - 1)) "$DISK_IMG"
sgdisk -n 2:$DATA_START_SECTOR:0 "$DISK_IMG"

ESP_GUID="C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
DATA_GUID="0FC63DAF-8483-4772-8E79-3D69D8477DE4"

sgdisk -t 1:$ESP_GUID "$DISK_IMG"
sgdisk -t 2:$DATA_GUID "$DISK_IMG"
sgdisk -A 1:set:2 "$DISK_IMG"

ESP_OFFSET=$((ESP_START_SECTOR * 512))
ESP_SIZE_BYTES=$((ESP_SECTORS * 512))
LOOP_DEV=$(losetup -f)
losetup -o $ESP_OFFSET --sizelimit $ESP_SIZE_BYTES "$LOOP_DEV" "$DISK_IMG"
mkfs.vfat -F 32 "$LOOP_DEV"
mkdir -p "$MOUNT_POINT"
mount "$LOOP_DEV" "$MOUNT_POINT"
mkdir -p "$MOUNT_POINT/EFI/BOOT"
cp "$BOOTLOADER_EFI" "$MOUNT_POINT/EFI/BOOT/BOOTX64.EFI"
umount "$MOUNT_POINT"
losetup -d "$LOOP_DEV"

DATA_OFFSET=$((DATA_START_SECTOR * 512))
LOOP_DEV=$(losetup -f)
losetup -o $DATA_OFFSET "$LOOP_DEV" "$DISK_IMG"
dd if="$RAW_DATA" of="$LOOP_DEV" bs=1M 2>/dev/null
losetup -d "$LOOP_DEV"

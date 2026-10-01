#!/bin/bash
set -e

ISO_URL="https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso"
ISO_FILE="boot_images/ubuntu-24.04-desktop-amd64.iso"
DISK_FILE="boot_images/ubuntu_desktop.qcow2"
DISK_SIZE="25G"

echo "=== Ubuntu Desktop QEMU Installer ==="

# 1. Download ISO if not present
if [ ! -f "$ISO_FILE" ]; then
    echo "[*] Downloading Ubuntu 24.04 Desktop ISO (6.2GB)... This will take a while."
    wget -O "$ISO_FILE" "$ISO_URL"
else
    echo "[*] ISO already downloaded."
fi

# 2. Create the persistent qcow2 disk if it doesn't exist
if [ ! -f "$DISK_FILE" ]; then
    echo "[*] Creating ${DISK_SIZE} persistent qcow2 disk at ${DISK_FILE}..."
    qemu-img create -f qcow2 "$DISK_FILE" "$DISK_SIZE"
else
    echo "[*] Persistent disk ${DISK_FILE} already exists. Continuing to boot..."
fi

echo ""
echo "[*] Launching QEMU..."
echo "[*] Connect to the graphical installer using a VNC viewer at: 127.0.0.1:5901"
echo ""

# 3. Boot QEMU with the CDROM and the new persistent disk attached
# Note: We use -enable-kvm for native performance, which requires Linux host
qemu-system-x86_64 \
    -M pc -m 4096M -enable-kvm -smp 4 \
    -drive file="$DISK_FILE",format=qcow2,if=virtio \
    -cdrom "$ISO_FILE" \
    -boot d \
    -vnc :1

echo ""
echo "[*] QEMU terminated."
echo "[*] Once you finish the installation and shut down the VM,"
echo "[*] you can boot the installed system natively through the Visual Audio pipeline using:"
echo ""
echo '    {'
echo '      "type": "boot_manifest",'
echo '      "arch": "x86_64",'
echo '      "image": "ubuntu_desktop.qcow2",'
echo '      "gui": true,'
echo '      "mem": "4096M"'
echo '    }'

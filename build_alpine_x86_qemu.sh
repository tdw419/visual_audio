#!/bin/bash
set -e

WORK_DIR="/home/jericho/projects/zion/projects/visual_audio/alpine_x86_build"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== Building Alpine x86_64 VM ==="

# Download Alpine x86_64 ISO
ISO="alpine-virt-3.20.3-x86_64.iso"
if [ ! -f "$ISO" ]; then
    echo "Downloading Alpine x86_64 virt ISO..."
    wget -q "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/$ISO" -O "$ISO"
fi

# Create empty disk for installation
DISK="alpine_x86.qcow2"
echo "Creating 10G disk for Alpine..."
qemu-img create -f qcow2 "$DISK" 10G

# Boot ISO to install (automated with preseed)
echo "Creating autoinstall config..."
cat > setup-alpine.conf << 'EOF'
KEYMAP=us
HOSTNAME=alpine
INTERFACES=auto
TIMEZONE=UTC
PROXY=none
APKREPOS=1
USER=jericho
SSHKEYS=none
DISK=vda
USE_MIRROR=1
INSTALL_ISO=1
EOF

echo "=== To complete Alpine installation manually ==="
echo "Run this command:"
echo ""
echo "qemu-system-x86_64 \\"
echo "    -enable-kvm -m 2G -smp 2 \\"
echo "    -drive file=$DISK,format=qcow2,if=virtio \\"
echo "    -drive file=$ISO,media=cdrom,if=ide \\"
echo "    -nographic -serial mon:stdio"
echo ""
echo "Then run 'setup-alpine' inside the VM"
echo ""
echo "For now, let's try a direct boot from the ISO..."

# Try booting directly from ISO (Alpine can run live)
echo "=== Testing Alpine live boot from ISO ==="
echo "Press Ctrl-A X to quit"
sleep 2

qemu-system-x86_64 \
    -enable-kvm \
    -m 1G -smp 1 \
    -drive file="$ISO",media=cdrom,if=ide \
    -nographic -serial mon:stdio
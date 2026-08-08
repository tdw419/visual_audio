#!/bin/bash
set -e

WORK_DIR="/home/jericho/projects/zion/projects/visual_audio/ubuntu_build"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "Downloading Ubuntu Noble (24.04) x86_64 cloud image..."
if [ ! -f ubuntu.img ]; then
    wget -q https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img -O ubuntu.img
fi

echo "Creating resized qcow2 (15G)..."
rm -f ubuntu.qcow2
cp ubuntu.img ubuntu.qcow2
qemu-img resize ubuntu.qcow2 15G

echo "Creating cloud-init config..."
cat > user-data << 'EOF'
#cloud-config
password: ubuntu
chpasswd: { expire: False }
ssh_pwauth: True
runcmd:
  - apt-get update
  - DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-desktop
  - systemctl set-default graphical.target
  - poweroff
EOF

cat > meta-data << 'EOF'
instance-id: ubuntu-spatial
local-hostname: ubuntu
EOF

genisoimage -output cidata.iso -volid cidata -joliet -rock user-data meta-data

echo "Booting VM to install ubuntu-desktop (this will take a while)..."
# Using KVM to speed it up significantly
qemu-system-x86_64 \
    -enable-kvm \
    -m 4G -smp 4 \
    -nographic \
    -drive file=ubuntu.qcow2,format=qcow2,if=virtio \
    -drive file=cidata.iso,format=raw,if=virtio \
    -serial mon:stdio > qemu_install.log 2>&1

echo "Installation complete. VM powered off."

echo "Converting to spatial MKV..."
cd ..
python3 convert_alpine_qcow2_to_mkv.py "$WORK_DIR/ubuntu.qcow2" ubuntu_desktop_x86.mkv

echo "Build complete! MKV is at ubuntu_desktop_x86.mkv"

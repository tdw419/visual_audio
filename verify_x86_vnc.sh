#!/bin/bash
# Verify x86_64 spatial boot with working VNC

set -e

PROJECT_ROOT="/home/jericho/projects/zion/projects/visual_audio"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
MKV_PATH="$PROJECT_ROOT/test_data/spatial_boot/test_row_major.mkv"
SOCK_PATH="/tmp/virtio_x86_vnc.sock"

echo "=== x86_64 Spatial Boot with VNC ==="
echo ""

if [ ! -f /tmp/vmlinuz-lts ]; then
    wget -q https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/x86_64/vmlinuz-lts -O /tmp/vmlinuz-lts
fi
if [ ! -f /tmp/initramfs-lts ]; then
    wget -q https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/x86_64/initramfs-lts -O /tmp/initramfs-lts
fi

cd "$PROJECT_ROOT/systems/virtio_pixel_rs"
cargo build --release 2>&1 | grep -E "(Finished|Compiling)" || true

pkill -f virtio_pixel_backend 2>/dev/null || true
pkill -f qemu-system-x86_64 2>/dev/null || true
rm -f $SOCK_PATH
sleep 1

"$BACKEND" "$MKV_PATH" $SOCK_PATH > /tmp/virtio_x86_backend.log 2>&1 &
BACKEND_PID=$!

for i in {1..30}; do
    if [ -S $SOCK_PATH ]; then break; fi
    sleep 0.2
done

if [ ! -S $SOCK_PATH ]; then
    echo "ERROR: Socket never appeared"
    cat /tmp/virtio_x86_backend.log
    exit 1
fi

echo "Booting QEMU x86_64 with VNC and virtio-gpu-pci..."

qemu-system-x86_64 \
    -object memory-backend-file,share=on,size=1G,mem-path=/dev/shm,id=ram \
    -machine q35,memory-backend=ram \
    -display vnc=:1 \
    -device virtio-gpu-pci \
    -kernel /tmp/vmlinuz-lts \
    -initrd /tmp/initramfs-lts \
    -append "console=ttyS0 earlyprintk=serial root=/dev/vda debug ignore_loglevel" \
    -chardev socket,id=blk0,path=$SOCK_PATH \
    -device vhost-user-blk-pci,chardev=blk0 \
    -m 1G \
    -no-reboot > /tmp/virtio_x86_qemu.log 2>&1 &
    
QEMU_PID=$!

echo "QEMU PID: $QEMU_PID"
sleep 5

if ps -p $QEMU_PID > /dev/null; then
    echo "SUCCESS: QEMU x86_64 is running with VNC."
    echo "VNC should be available on :1"
else
    echo "FAILURE: QEMU exited."
    cat /tmp/virtio_x86_qemu.log
    exit 1
fi

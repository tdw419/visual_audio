#!/bin/bash
set -e

PROJECT_ROOT="/home/jericho/projects/zion/projects/visual_audio"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
MKV_PATH="$PROJECT_ROOT/ubuntu_desktop_x86.mkv"
SOCK_PATH="/tmp/virtio_x86_desktop_vnc.sock"

echo "=== x86_64 Ubuntu Desktop Spatial Boot with VNC ==="
echo ""

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
    -object memory-backend-file,share=on,size=4G,mem-path=/dev/shm,id=ram \
    -machine q35,memory-backend=ram \
    -enable-kvm \
    -display vnc=:1 \
    -device virtio-gpu-pci \
    -chardev socket,id=blk0,path=$SOCK_PATH \
    -device vhost-user-blk-pci,chardev=blk0,bootindex=0,num-queues=1 \
    -m 4G -smp 1 \
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

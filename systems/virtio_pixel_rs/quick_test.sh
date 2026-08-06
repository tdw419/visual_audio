#!/bin/bash
cd /home/jericho/projects/zion/projects/visual_audio/systems/virtio_pixel_rs
pkill -f virtio_pixel_backend 2>/dev/null || true
pkill -f qemu-system-x86_64 2>/dev/null || true
rm -f /tmp/virtio-pixel-spatial.sock
sleep 1

./target/release/virtio_pixel_backend \
    /home/jericho/projects/zion/projects/visual_audio/alpine_rootfs_ext4_rw3.mkv \
    /tmp/virtio-pixel-spatial.sock > /tmp/backend_full.log 2>&1 &
BACKEND_PID=$!

for i in {1..30}; do
    if [ -S /tmp/virtio-pixel-spatial.sock ]; then
        break
    fi
    sleep 0.2
done

qemu-system-x86_64 \
    -chardev socket,id=blk0,path=/tmp/virtio-pixel-spatial.sock \
    -device vhost-user-blk-pci,chardev=blk0,bootindex=0 \
    -m 2G -nographic -no-reboot 2>&1 | head -30

sleep 5
kill $BACKEND_PID 2>/dev/null || true

echo ""
echo "=== VhostUser messages ==="
grep "VhostUser message" /tmp/backend_full.log
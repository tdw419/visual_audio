#!/bin/bash
# Boot VM and break to initramfs shell for fsck

PROJECT_ROOT="/home/jericho/projects/zion/projects/visual_audio"
CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1"
BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
SOCKET="/tmp/virtio-pixel-interactive.sock"
LOG_DIR="$PROJECT_ROOT/logs"
NATIVE_BOOT_DIR="/home/jericho/scratch/ubuntu_boot_native"
KERNEL="$NATIVE_BOOT_DIR/vmlinuz-6.8.0-136-generic"
INITRD="$NATIVE_BOOT_DIR/initrd.img-6.8.0-136-generic"

echo "=== Initramfs Shell Boot ==="

# Check kernel/initrd exist
if [ ! -f "$KERNEL" ] || [ ! -f "$INITRD" ]; then
    echo "[!] Kernel/initrd not found at $NATIVE_BOOT_DIR"
    echo "    Looking for alternatives..."
    NATIVE_BOOT_DIR="/home/jericho/projects/zion/projects/visual_audio/ubuntu_desktop_pxc1_v1"
    KERNEL="$NATIVE_BOOT_DIR/vmlinuz"
    INITRD="$NATIVE_BOOT_DIR/initrd.img"
    if [ ! -f "$KERNEL" ] || [ ! -f "$INITRD" ]; then
        echo "[!] No kernel/initrd found"
        exit 1
    fi
    echo "[+] Using kernel from PXC1 container"
fi

# Cleanup
pkill -9 virtio_pixel_backend 2>/dev/null || true
rm -f "$SOCKET"
rm -rf /home/jericho/scratch/qemu_shm
mkdir -p /home/jericho/scratch/qemu_shm

# Start backend
chmod +x "$BACKEND"
$BACKEND "$CONTAINER_DIR" "$SOCKET" > "$LOG_DIR/virtio_initramfs.log" 2>&1 &
BACKEND_PID=$!

# Wait for socket
for i in {1..60}; do
    if [ -S "$SOCKET" ]; then break; fi
    sleep 1
done

if [ ! -S "$SOCKET" ]; then
    echo "[!] Backend failed"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

echo "[+] Booting with break=premount, debug, fsck.mode=skip..."

qemu-system-x86_64 \
    -machine q35,memory-backend=ram \
    -object memory-backend-file,share=on,size=4G,mem-path=/home/jericho/scratch/qemu_shm,id=ram \
    -m 4G \
    -smp 4 \
    -cpu host \
    -enable-kvm \
    -vga std \
    -usb -device usb-tablet \
    -display gtk \
    -netdev user,id=net0,hostfwd=tcp::2222-:22 \
    -device virtio-net-pci,netdev=net0 \
    -chardev socket,id=blk0,path="$SOCKET" \
    -device vhost-user-blk-pci,chardev=blk0,num-queues=1,bootindex=1 \
    -fsdev local,id=zionshare,path=/home/jericho/zion,security_model=mapped-xattr \
    -device virtio-9p-pci,fsdev=zionshare,mount_tag=host_zion \
    -serial stdio \
    -kernel "$KERNEL" \
    -initrd "$INITRD" \
    -append "root=UUID=db3ea6be-e601-49ba-a56b-7fb2b2bd2812 ro break=premount debug fsck.mode=skip console=tty1 console=ttyS0"

echo "[*] VM exited"
kill $BACKEND_PID 2>/dev/null
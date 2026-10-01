#!/bin/bash
set -ex
qemu-system-x86_64 -m 1G -enable-kvm -cpu host -display none \
    -d int,cpu_reset -D /tmp/qemu_int.log \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/my_vars.fd \
    -drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none \
    -device ide-hd,drive=bootdisk,bootindex=1 \
    -drive id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none \
    -device virtio-blk-pci,drive=rootdisk,bootindex=2 \
    -serial file:/tmp/qemu_serial.log &
QEMU_PID=$!

for i in {1..120}; do
    if grep -q "ubuntu login:" /tmp/qemu_serial.log 2>/dev/null; then
        echo "Login prompt found!"
        sleep 2
        break
    fi
    sleep 3
done

kill -9 $QEMU_PID || true
tail -n 20 /tmp/qemu_serial.log

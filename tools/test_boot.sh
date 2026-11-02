#!/bin/bash
# Quick test script for MKV boot

echo "Starting NBD server..."
python3 tools/mkv_nbd_server.py > /tmp/nbd.log 2>&1 &
NBD_PID=$!
echo "NBD PID: $NBD_PID"

sleep 2

echo "Starting QEMU (15 seconds)..."
timeout 15 ./qemu_bootstrap \
  -machine virt \
  -cpu rv64 \
  -m 2048 \
  -smp 2 \
  -bios default \
  -device virtio-gpu-device \
  -device virtio-net-device,netdev=net0 \
  -netdev user,id=net0,hostfwd=tcp::2222-:22 \
  -drive file=nbd:127.0.0.1:10809,format=qcow2,if=virtio \
  -nographic \
  -serial mon:stdio

echo "---"
echo "NBD log:"
head -30 /tmp/nbd.log

kill $NBD_PID 2>/dev/null
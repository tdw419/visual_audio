#!/usr/bin/env bash
# boot helper: rebuild stage1 consts from given payload, encode rung-5 medium, boot.
# usage: boot_probe.sh <payload.bin> <serial.log>
set -eu
cd /home/jericho/projects/zion/projects/visual_audio/tools/bare_metal_poc/rung5
PAYLOAD=$1
LOG=$2
python3 rung4_consts.py "$PAYLOAD" >/dev/null
nasm -f bin stage1.asm -o stage1.bin
python3 rung5_codec.py encode stage1.bin "$PAYLOAD" img2.bin \
    rung5_pb.png rung5_pb.raw rung5_pb_meta.json >/dev/null
timeout 25 qemu-system-x86_64 -drive file=rung5_pb.raw,format=raw,if=ide \
    -display none -no-reboot -serial file:"$LOG" 2>/dev/null || true
xxd "$LOG"

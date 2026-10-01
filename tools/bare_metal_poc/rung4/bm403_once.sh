#!/bin/bash
set -e
cd /home/jericho/projects/zion/projects/visual_audio/tools/bare_metal_poc/rung4
SCALE=$1
TAG=$2
nasm -f bin stage2.asm -DRUNG4_SCALE=$SCALE -o stage2_code.bin
python3 rung4_pad.py $SCALE stage2_code.bin stage2.bin >/dev/null
python3 rung4_consts.py >/dev/null
nasm -f bin stage1.asm -o stage1.bin
python3 rung4_codec.py encode stage1.bin stage2.bin rung4_medium.png rung4_medium.raw rung4_meta.json >/dev/null
rm -f serial_t_$TAG.log
timeout 120 qemu-system-x86_64 -drive file=rung4_medium.raw,format=raw,if=ide -display none -no-reboot -serial file:serial_t_$TAG.log &
QPID=$!
START=$(date +%s.%N)
while true; do
  if grep -q "GATE4=" serial_t_$TAG.log 2>/dev/null; then
    END=$(date +%s.%N)
    echo "receipt after: $(echo "$END - $START" | bc) s"
    break
  fi
  NOW=$(date +%s.%N)
  EL=$(echo "$NOW - $START" | bc)
  GT=$(echo "$EL > 110" | bc)
  if [ "$GT" = "1" ]; then echo "TIMEOUT no receipt"; break; fi
  sleep 0.05
done
kill $QPID 2>/dev/null
wait $QPID 2>/dev/null
tr -d '\r' < serial_t_$TAG.log | grep GATE4 || true

#!/usr/bin/env bash
# Compare: (a) iso direct serial, (b) iso direct serial + console=ttyS0 via
# extracted-kernel boot (-kernel/-initrd/-append) as diagnosis of whether
# isolinux vs kernel is the serial bottleneck.
set -u
cd "$(dirname "$0")"
MODE=${1:-kernel}

if [ "$MODE" = "kernel" ]; then
  python3 extract_boot_files.py
  timeout 60 qemu-system-x86_64 -M pc -m 512 \
    -kernel vmlinuz64 -initrd core.gz \
    -append "loglevel=3 console=ttyS0" \
    -display none -no-reboot -serial file:serial_kernel.log
  echo "kernel-direct rc=$?"
  wc -c serial_kernel.log
  tail -6 serial_kernel.log | tr -d '\r'
fi

#!/usr/bin/env bash
# Build the RV64 cpio-parser probe (bare-metal, links at 0x80000000).
set -euo pipefail
cd "$(dirname "$0")"

CC=riscv64-linux-gnu-gcc
CFLAGS="-march=rv64imac_zicsr -mabi=lp64 -nostdlib -static -O2 -g -fno-builtin -I. -I./linux"

"$CC" $CFLAGS -Wl,-T,probe.ld \
    -o probe_cpio.elf \
    probe_cpio.c probe_start.S probe_data.S inflate.c inffast.c inftrees.c

echo "built: $(pwd)/probe_cpio.elf"
riscv64-linux-gnu-objdump -f probe_cpio.elf | head -3
ls -la probe_cpio.elf

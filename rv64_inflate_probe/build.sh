#!/usr/bin/env bash
# Build the RV64 inflate probe (bare-metal, links at 0x80000000).
set -euo pipefail
cd "$(dirname "$0")"

CC=riscv64-linux-gnu-gcc
CFLAGS="-march=rv64imac_zicsr -mabi=lp64 -nostdlib -static -O2 -g -I. -I./linux"

"$CC" $CFLAGS -Wl,-T,probe.ld \
    -o probe.elf \
    probe_main.c probe_start.S probe_data.S inflate.c inffast.c inftrees.c

echo "built: $(pwd)/probe.elf"
riscv64-linux-gnu-objdump -f probe.elf | head -5
ls -la probe.elf

#!/usr/bin/env bash
# Build the tlb_membench variants for the RV64I GPU emulator.
# Usage: ./build.sh [W]
set -euo pipefail
cd "$(dirname "$0")"

W="${1:-128}"
CC=riscv64-linux-gnu-gcc
CFLAGS="-march=rv64imac_zicsr -mabi=lp64 -nostdlib -static -O2 -g -DR=${R:-1000000}"

for acc in ALU LOAD STORE; do
    out="tlb_bench_$(echo "$acc" | tr 'A-Z' 'a-z')_w${W}.elf"
    echo "building $out (ACCESS=$acc W=$W)"
    "$CC" $CFLAGS -DACCESS_$acc -DW=$W -Ttext=0x80000000 \
        -o "$out" tlb_membench.c
done
ls -la tlb_bench_*.elf

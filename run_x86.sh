#!/bin/bash
qemu-system-x86_64 -m 512 \
    -machine q35 \
    -bios /usr/share/ovmf/OVMF.fd \
    -drive format=raw,file=fat:rw:systems/target/fat/ \
    -drive format=raw,file=boot_images/hello_x86.rts.png \
    -nographic \
    -serial mon:stdio

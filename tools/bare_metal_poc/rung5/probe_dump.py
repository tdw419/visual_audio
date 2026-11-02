#!/usr/bin/env python3
"""Probe: make the guest print WHAT it decoded. Builds a stage2 whose only
job is to dump the first 64 bytes at its base as hex, using rung-4 stage1
unchanged. The dump lets us compare guest RAM vs the medium directly.
"""
import subprocess
import sys

DUMP = r"""
BITS 16
ORG 0
COM1 equ 0x3F8
start:
    cld
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti
    mov dx, COM1+1
    xor al, al
    out dx, al
    mov dx, COM1+3
    mov al, 0x80
    out dx, al
    mov dx, COM1
    mov al, 0x01
    out dx, al
    mov dx, COM1+1
    xor al, al
    out dx, al
    mov dx, COM1+3
    mov al, 0x03
    out dx, al

    mov ax, cs
    mov ds, ax
    xor si, si
    mov cx, 64
.dump:
    lodsb
    push cx
    mov ah, al
    shr al, 1
    shr al, 1
    shr al, 1
    shr al, 1
    call nib
    mov al, ah
    and al, 0x0F
    call nib
    mov al, ' '
    call putc
    pop cx
    loop .dump
    mov si, msg_done
    jmp puts_msg
.halt:
    hlt
    jmp .halt
puts_msg:
    lodsb
    test al, al
    jz .halt2
    mov ah, al
    mov dx, COM1+5
.in0:
    in al, dx
    test al, 0x20
    jz .in0
    mov al, ah
    mov dx, COM1
    out dx, al
    jmp puts_msg
.halt2:
    hlt
    jmp .halt2
nib:
    cmp al, 10
    jb .d
    add al, 'A'-10-'0'
.d:
    add al, '0'
putc:
    push ax
    push dx
    mov ah, al
.wait:
    mov dx, COM1+5
    in al, dx
    test al, 0x20
    jz .wait
    mov al, ah
    mov dx, COM1
    out dx, al
    pop dx
    pop ax
    ret
msg_done db 13, 10, 'DUMP-DONE', 13, 10, 0
"""

open("probe_dump.asm", "w").write(DUMP)
subprocess.run(["nasm", "-f", "bin", "probe_dump.asm", "-o", "probe_dump_code.bin"],
               check=True)
code = open("probe_dump_code.bin", "rb").read()
# pad to 64 KB with the rung-4 pattern (host authority)
PATTERN = bytes([0xA5, 0x5A, 0xC3, 0x3C, 0x0F, 0xF0, 0x33, 0xCC,
                 0x81, 0x7E, 0x18, 0xE7, 0x42, 0xBD, 0x69, 0x96])
pad = 65536 - len(code)
out = code + PATTERN * (pad // 16) + PATTERN[: pad % 16]
open("probe_dump.bin", "wb").write(out)
print(f"probe_dump.bin: {len(out)} bytes (code {len(code)} + filler {pad})")

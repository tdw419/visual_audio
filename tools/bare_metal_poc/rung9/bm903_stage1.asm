; BM903 step 1 stage1: MBR that lands stage2 at linear 0x8000 and jumps there.
; Copied-by-shape from rung5/stage1.asm (COM1 init, int 13h AH=42h DAP read,
; RDFAIL refusal, 512-byte tail); the pixel de-interleave and CRC legs are
; step-2 work, so this file carries only the conventional-load path the brief
; allows for step 1.
BITS 16
ORG 0x7C00

COM1 equ 0x3F8
DST_SEG equ 0x0000            ; stage2 home = linear 0x8000 == ORG 0x8000
DST_OFF equ 0x8000

%include "bm903_layout.inc"

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

    mov si, msg_hello
    call puts

    ; ---- read STAGE2_SECTORS sectors from LBA 1 into 0x0000:0x8000 ----
    mov ax, STAGE2_SECTORS
    mov [dap_count], ax
    mov word [dap_lba], 1
    mov word [dap_lba+2], 0
    mov si, dap
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    jc rdfail

    mov si, msg_load2
    call puts
    push word 0x0000
    push word DST_OFF
    retf

rdfail:
    mov si, msg_readfail
    call puts
.hang:
    cli
    hlt
    jmp .hang

; ---- real-mode serial helpers (shape copied from rung5/stage1.asm) ----
puts:
    pusha
.lod:
    lodsb
    test al, al
    jz .done
    call putc
    jmp .lod
.done:
    popa
    ret

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

msg_hello    db 'BM903-S1', 13, 10, 0
msg_load2    db 'BM903-S1 JUMP STAGE2', 13, 10, 0
msg_readfail db 'BM903-S1 RDFAIL', 13, 10, 0

dap:
    db 0x10, 0
dap_count:
    dw 16
    dw DST_OFF
    dw DST_SEG
dap_lba:
    dq 1

    times 510-($-$$) db 0
    dw 0xAA55

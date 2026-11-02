; stage1_dbg_src.asm -- DEBUG VARIANT of stage1 for the 64 KB GREEN FAIL:
; identical streaming scatter, then prints per-4KB sum16 of the decoded
; region (16 lines) BEFORE the CRC gate, so the host can localize where
; guest memory diverges from the host image. Not part of the gate.
BITS 16
ORG 0x7C00

COM1        equ 0x3F8
SRC_SEG     equ 0x2000
DST_SEG     equ 0x1000
CHUNK_BYTES equ CHUNK_SECTORS*512

%include "stage1_const.inc"

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

    ; ================= streaming read + de-interleave (as stage1) =====
    mov word [lba], 1
    mov ax, DST_SEG
    mov es, ax
    mov bp, 0
r4_plane:
    mov ax, PLANE_LEN/512
    mul bp
    inc ax
    mov [lba], ax
    mov di, bp
    mov cx, CHUNKS_PER_PLANE
r4_chunk:
    push cx
    mov ax, [lba]
    mov [dap_lba], ax
    mov si, dap
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    jnc r4_read_ok
    mov si, msg_readfail
    call puts
    jmp halt
r4_read_ok:
    push ds
    mov ax, SRC_SEG
    mov ds, ax
    xor si, si
    mov cx, CHUNK_BYTES
%macro SCATTER_D 0
%%byte:
    lodsb
    stosb
    add di, 3
    loop %%byte
%endmacro
    SCATTER_D
    pop ds
    pop cx
    mov ax, CHUNK_SECTORS
    add [lba], ax
    loop r4_chunk
    inc bp
    cmp bp, 4
    jb r4_plane

    ; ================= DEBUG: 16 per-4KB sum16 lines ==================
    mov bp, 0                  ; bank index 0..15 (4 KB each)
dbg_bank:
    ; DS = ES = DST_SEG + bp*0x100 paragraphs (0x100 para = 4096 bytes).
    ; byte offset = bp*4096; paragraph offset = bp*0x100 = (bp*4)<<6.
    mov ax, DST_SEG
    mov dx, bp                 ; save bank in dx
    mov bl, dl
    mov bh, 0
    add bx, bx                 ; bp*2
    add bx, bx                 ; bp*4
    mov cl, 6
    shl bx, cl                 ; bp*4 << 6 = bp*0x100 paragraphs
    add ax, bx
    mov ds, ax
    mov es, ax
    xor si, si

    xor bx, bx                 ; sum accumulator
    xor si, si
    mov cx, 4096/2             ; words
.sumw:
    lodsw
    add bl, al
    adc bh, 0
    add bl, ah
    adc bh, 0
    loop .sumw
    mov si, msg_sum
    call puts
    mov ax, bp
    call putdec
    mov si, msg_sp
    call puts
    mov ax, bx
    call puthex4
    mov si, msg_crlf
    call puts
    inc bp
    cmp bp, 16
    jb dbg_bank

    ; ================= normal CRC gate ================================
    mov ax, DST_SEG
    mov es, ax
    xor si, si
    call crc32_calc
    mov [crcline], eax
    mov si, msg_crc
    call puts
    mov eax, [crcline]
    call puthex8
    mov si, msg_crlf
    call puts
    jmp halt
halt:
    hlt
    jmp halt

; ---- CRC32 identical to stage1's banked walk ----
crc32_calc:
    push es
    mov eax, 0xFFFFFFFF
    mov bp, PAYLOAD_LEN/65536
    xor si, si
.bank:
    xor cx, cx
.byte_loop:
    mov bl, [es:si]
    inc si
    xor al, bl
    mov edx, 8
.bit_loop:
    shr eax, 1
    jnc .no_xor
    xor eax, 0xEDB88320
.no_xor:
    dec dx
    jnz .bit_loop
    loop .byte_loop
    mov ax, es
    add ax, 0x1000
    mov es, ax
    dec bp
    jnz .bank
.done:
    xor eax, 0xFFFFFFFF
    pop es
    ret

puts:
    push ax
    push dx
.next:
    lodsb
    test al, al
    jz .done
    call putc
    jmp .next
.done:
    pop dx
    pop ax
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

puthex4:
    push ax
    push cx
    mov ch, 4
.rot:
    rol ax, 1
    rol ax, 1
    rol ax, 1
    rol ax, 1
    push ax
    and al, 0x0F
    cmp al, 10
    jb .dig
    add al, 'A'-10-'0'
.dig:
    add al, '0'
    call putc
    pop ax
    dec ch
    jnz .rot
    pop cx
    pop ax
    ret

puthex8:
    push eax
    push bx
    mov bx, ax
    shr eax, 16
    call puthex4
    mov ax, bx
    call puthex4
    pop bx
    pop eax
    ret

putdec:
    push ax
    push bx
    push cx
    push dx
    mov bx, 10
    xor cx, cx
.div:
    xor dx, dx
    div bx
    push dx
    inc cx
    test ax, ax
    jnz .div
.pr:
    pop ax
    add al, '0'
    call putc
    loop .pr
    pop dx
    pop cx
    pop bx
    pop ax
    ret

msg_hello    db 'PXC1-RUNG4-DBG', 13, 10, 0
msg_sum      db 'SUM4K[', 0
msg_sp       db ']=', 0
msg_crc      db 'CRC=', 0
msg_crlf     db 13, 10, 0
msg_readfail db 'READFAIL', 13, 10, 0

crcline: dd 0

align 2
lba:     dw 1

dap:
    db 0x10, 0
    dw CHUNK_SECTORS
    dw 0x0000
    dw SRC_SEG
dap_lba:
    dq 1

    times 510-($-$$) db 0
    dw 0xAA55

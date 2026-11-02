; stage1_dbg2.asm -- DEBUG VARIANT of the NEW bank-outer stage1 for the
; 256 KB GREEN FAIL: identical bank-outer scatter, then prints per-bank
; sum16 (one line per 64 KB bank) BEFORE the CRC gate, so the host can
; compare guest memory against host expectations (bank0=765C,
; banks1-3=8000 for the 256 KB patterned-filler payload).
BITS 16
ORG 0x7C00

COM1        equ 0x3F8
SRC_SEG     equ DST_SEG+PAYLOAD_BANKS*0x1000
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
    xor bx, bx
r4_bank:
    mov ax, DST_SEG
    mov dx, bx
    shl dx, 12
    add ax, dx
    mov es, ax
    mov bp, 0
r4_plane:
    mov ax, PLANE_LEN/512
    mul bp
    add ax, 1
    mov dx, bx
    shl dx, 5
    add ax, dx
    mov [lba], ax
    mov di, bp
    mov cx, CHUNKS_PER_BANK
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
    inc bx
    cmp bx, PAYLOAD_BANKS
    jb r4_bank

    ; ================= DEBUG: per-bank sum16 ==========================
    xor bx, bx
dbg_bank:
    mov ax, DST_SEG
    mov dx, bx
    shl dx, 12
    add ax, dx
    mov es, ax
    xor si, si
    xor cx, cx
    xor dx, dx                 ; dx = accumulator
.sum:
    mov al, [es:si]
    inc si
    xor ah, ah
    add dx, ax
    loop .sum
    mov si, msg_b
    call puts
    ; print bank number
    mov ax, bx                 ; bank index (BX clobbered? no, preserved
                               ; by .sum; but we reloaded bx for loop...)
    call putdec16
    mov si, msg_eq
    call puts
    mov ax, dx
    call puthex4
    mov si, msg_crlf
    call puts
    inc bx
    cmp bx, PAYLOAD_BANKS
    jb dbg_bank

    ; then run the CRC gate as stage1 does
    mov ax, DST_SEG
    mov es, ax
    xor si, si
    call crc32_calc
    mov [crcline], eax
    cmp eax, EXPECTED_CRC
    jne dbg_fail
    mov si, msg_dbgok
    call puts
.h:
    hlt
    jmp .h
dbg_fail:
    mov si, msg_fail
    call puts
    mov eax, [crcline]
    call puthex8
    mov si, msg_crlf
    call puts
.h2:
    hlt
    jmp .h2

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
    dec bp
    jz .done
    mov ax, es
    add ax, 0x1000
    mov es, ax
    jmp .bank
.done:
    xor eax, 0xFFFFFFFF
    pop es
    ret

puts:
    push ax
.next:
    lodsb
    test al, al
    jz .done
    call putc
    jmp .next
.done:
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

putdec16:
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

msg_hello db 'PXC1-RUNG4-DBG2', 13, 10, 0
msg_readfail db 'READFAIL', 13, 10, 0
msg_b     db 'BANK ', 0
msg_eq    db ' SUM=', 0
msg_dbgok db 'DBGCRC=PASS', 13, 10, 0
msg_fail  db 'DBGCRC=FAIL ', 0
msg_crlf  db 13, 10, 0

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

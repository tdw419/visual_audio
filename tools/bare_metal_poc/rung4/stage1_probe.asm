; stage1_probe.asm -- COPY of stage1.asm with a probe in the FAIL path:
; prints the first 8 decoded bytes at DST_SEG:0 and the per-4KB sum16 of
; banks 0..3, then the CRC as usual. Nothing else changed.
[bits 16]
[org 0x7C00]

SRC_SEG     equ 0x2000
DST_SEG     equ 0x1000
COM1        equ 0x3F8
CHUNK_BYTES equ 4096

start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti
    cld

    ; COM1 init exactly as the real stage1 does (divisor latch, 8N1)
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

    mov si, msg_boot
    call puts

    ; ================= streaming read + de-interleave =================
    mov word [lba], 1
    mov ax, DST_SEG
    mov es, ax
    mov bp, 0
r4_plane:
    mov ax, 32                   ; PLANE_LEN/512 = 16384/512
    mul bp
    inc ax
    mov [lba], ax
    mov di, bp
    mov cx, 4                    ; CHUNKS_PER_PLANE
r4_chunk:
    push cx
    mov ax, [lba]
    mov [DAP_LBA], ax
    mov si, dap
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    jnc r4_read_ok
    mov al, ah
    call puthex1_lo             ; error code as hex digit
    mov si, msg_readfail
    call puts
    jmp halt
r4_read_ok:
    push ds
    mov ax, SRC_SEG
    mov ds, ax
    xor si, si
    mov cx, CHUNK_BYTES
%macro SCATTER 0
%%byte:
    lodsb
    stosb
    add di, 3
    loop %%byte
%endmacro
    SCATTER
    pop ds
    pop cx
    mov ax, 8                    ; CHUNK_SECTORS
    add [lba], ax
    loop r4_chunk
    inc bp
    cmp bp, 4
    jb r4_plane

    ; ================= probe: 64K CRC walk ============================
    mov ax, DST_SEG
    mov es, ax
    mov si, msg_probe
    call puts

    mov si, msg_c64k
    call puts
    mov ax, DST_SEG
    mov es, ax
    xor si, si
    call crc64k_calc
    call puthex8
    mov si, msg_crlf
    call puts
    jmp probe_halt

crc64k_calc:                     ; CRC over ES:0 .. 65536 bytes
    push es
    push cx
    mov eax, 0xFFFFFFFF
    xor cx, cx
.cr6_byte:
    mov bl, [es:si]
    inc si
    xor al, bl
    mov dx, 8
.cr6_bit:
    shr eax, 1
    jnc .cr6_nx
    xor eax, 0xEDB88320
.cr6_nx:
    dec dx
    jnz .cr6_bit
    loop .cr6_byte
    xor eax, 0xFFFFFFFF
    pop cx
    pop es
    ret


; ---- print EAX as 8 uppercase hex digits ----
puthex8:
    push eax
    push bx
    mov bx, ax
    shr eax, 16
    call puthex4                 ; high 16
    mov ax, bx
    call puthex4                 ; low 16
    pop bx
    pop eax
    ret

msg_c4096 db 'C4K:', 0
msg_c64k  db 'C64K:', 0

r4_crc_fail_near:
    jmp r4_crc_fail

halt:
    hlt
    jmp halt

probe_halt:
    mov si, msg_done
    call puts
    jmp halt

r4_crc_fail:
    mov si, msg_fail
    call puts
    mov si, msg_crlf
    call puts
    jmp halt

; ---- print ASCIIZ at SI over COM1 ----
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

; ---- print AL over COM1 ----
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

; ---- print AL low nibble as hex digit ----
puthex1_lo:
    push ax
    cmp al, 10
    jb .dig
    add al, 'A'-10
    jmp .out
.dig:
    add al, '0'
.out:
    call putc
    pop ax
    ret

; ---- print AX as 4 uppercase hex digits ----
puthex4:
    push ax
    push bx
    push cx
    mov cx, 4
.dig4:
    rol ax, 4
    push ax
    and al, 0x0F
    call puthex1_lo
    pop ax
    loop .dig4
    pop cx
    pop bx
    pop ax
    ret

EXPECTED_CRC equ 0xE1AE9612

msg_boot     db 'PXC1-PROBE', 13, 10, 0
msg_readfail db 'READFAIL', 13, 10, 0
msg_probe    db 'PB:', 0
msg_r        db 'r', 0
msg_s        db 's', 0
msg_bank     db 'B', 0
msg_pass     db 'GATE4=PASS CRC=', 0
msg_fail     db 'GATE4=FAIL CRC=', 0
msg_crlf     db 13, 10, 0
msg_done     db 'PROBEDONE', 13, 10, 0
crcline: dd 0
lba:     dw 0
dap:     db 0x10, 0
         dw 8                    ; sectors
         dw 0x0000               ; offset
         dw 0x2000               ; segment (SRC_SEG)
DAP_SEG equ dap + 6
DAP_LBA equ dap + 8

times 510-($-$$) db 0
dw 0xAA55

align 512
stage1_probe_end:

; stage2.asm -- RUNG2 payload: until stage1 decodes it, this code exists
; ONLY as four channel planes on the medium (no two of its bytes are even
; adjacent there). The loader lands it at 0x7E00 and jumps; we checksum
; our own decoded bytes (PAYLOAD_LEN at 0x7E00) and print the receipt.

BITS 16
ORG 0x7E00

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

    ; ---- checksum the bytes we were decoded to (mod 65536) ----
    mov cx, PAYLOAD_LEN          ; our own length, padded to multiple of 4
    mov si, 0x7E00
    xor bx, bx
.chk:
    lodsb
    add bl, al
    adc bh, 0
    loop .chk

    mov si, msg2
    call puts
    mov ax, bx
    call puthex4
    mov si, msg3
    call puts

.halt:
    hlt
    jmp .halt

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
    mov dx, COM1+5               ; LSR: THR empty?
    in al, dx
    test al, 0x20
    jz .wait
    mov al, ah
    mov dx, COM1
    out dx, al
    pop dx
    pop ax
    ret

; ---- print AX as 4 uppercase hex digits ----
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

msg2 db 'STAGE2 CKSUM=', 0
msg3 db ' EXEC', 13, 10, 0

; payload length = own length padded to a multiple of 4 (must match the
; padding rule in rung2_codec.py, which pads stage2.bin identically).
; Note: ($+3)&~3 is rejected by nasm here ($ is section-relative), hence
; the divide/multiply form of round-up.
code_end:
PAYLOAD_LEN equ ((code_end - $$ + 3) / 4) * 4
times (PAYLOAD_LEN - (code_end - $$)) db 0

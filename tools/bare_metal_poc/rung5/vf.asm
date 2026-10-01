; stage2.asm -- RUNG4 payload: >=64 KB scale, ORG 0 (executes at
; DST_SEG:0000 = linear 0x10000, jumped via retf from stage1). Until
; stage1 decodes it, this code exists ONLY as four channel planes on the
; medium. We checksum the FULL decoded image (PAYLOAD_LEN bytes at our
; own base: this code + patterned filler to the rung-4 scale) and print
; a receipt naming the payload size, so GREEN proves scale, not just
; life. The filler is PATTERNED, not zero: a truncated/short decode
; cannot checksum correctly by skipping a zero tail.
;
; NOTE the receipt prints the CRC of the bytes at the destination, which
; the loader already gated; stage2's own sum16 is the in-executor witness
; that the image that EXECUTES matches what the loader verified.

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

    ; ---- checksum the full image at our own base: CS -> DS mapping.
    ; We are at DST_SEG:0; set DS=DST_SEG and walk PAYLOAD_LEN bytes.
    mov ax, cs
    mov ds, ax
    xor si, si
%if (RUNG4_SCALE/1024) == 64
    mov cx, PAYLOAD_LEN>>1       ; word-wise (65536B fits 16-bit count)
%else
    mov ecx, PAYLOAD_LEN>>1      ; scaled payloads need the 32-bit count
%endif
    xor bx, bx
.chk:
    lodsw
    add bl, al
    adc bh, 0
    add bl, ah
    adc bh, 0
    loop .chk

    mov si, msg_sz
    call puts
    mov ax, PAYLOAD_LEN / 1024   ; payload size in KB (decimal)
    call putdec
    mov si, msg_kbu
    call puts

    mov si, msg2
    call puts
    mov ax, bx
    call puthex4
    mov si, msg3
    call puts

    mov si, img2_dap
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    mov si, msg2
    call puts
halt:
    hlt
    jmp halt

align 2
img2_dap:
    db 0x10, 0
    dw 4
    dw 0x0000
    dw 0x5000
img2_dap_lba:
    dq 129
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

; ---- print AX as unsigned decimal ----
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

msg_sz  db 'STAGE2 SIZE=', 0
msg_kbu db ' KB', 13, 10, 0
msg2    db 'STAGE2 CKSUM=', 0
msg3    db ' EXEC', 13, 10, 0

; payload length IS the scale: stage2 checksums RUNG4_SCALE bytes at its
; base at runtime (memory holds code + filler decoded from the medium),
; and rung4_pad.py grows the HOST binary to RUNG4_SCALE with the same
; patterned filler (PATTERN there is the single point of definition).
; The gate asserts the padded binary is what got encoded.
PAYLOAD_LEN equ RUNG4_SCALE

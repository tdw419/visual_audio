; boot.asm -- 512-byte MBR that proves pixels became executing code.
;
; Loaded by BIOS at 0x7C00. Prints a receipt over COM1 (115200 8N1):
;   line 1: PXC1-BARE-METAL-RECEIPT
;   line 2: CKSUM=XXXX  (sum of the 512 bytes this code was loaded
;                        from, computed by the CPU executing them,
;                        mod 65536 -- host recomputes independently
;                        from the PNG-decoded bytes)
;           plus " EXEC" = execution proven, not just data integrity.
; Then halts.

BITS 16
ORG 0x7C00

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

    ; ---- COM1: 115200 baud, 8N1 ----
    mov dx, COM1+1              ; IER: disable serial interrupts
    xor al, al
    out dx, al
    mov dx, COM1+3              ; LCR: DLAB on
    mov al, 0x80
    out dx, al
    mov dx, COM1                ; DLL: divisor low = 1
    mov al, 0x01
    out dx, al
    mov dx, COM1+1              ; DLM: divisor high = 0
    xor al, al
    out dx, al
    mov dx, COM1+3              ; LCR: 8N1, DLAB off
    mov al, 0x03
    out dx, al

    mov si, msg1
    call puts

    ; ---- checksum of the 512 bytes we were loaded from ----
    ; BX = sum(byte[0x7C00 .. 0x7C1FF]) mod 65536
    xor bx, bx
    mov si, 0x7C00
    mov cx, 512
.chk:
    lodsb
    add bl, al
    adc bh, 0                   ; carry into BH; overflow out of BX = mod 2^16
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
    mov dx, COM1+5              ; LSR: THR empty?
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
    rol ax, 1                   ; rotate top nibble into AL[3:0]
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

msg1 db 'PXC1-BARE-METAL-RECEIPT', 13, 10, 0
msg2 db 'CKSUM=', 0
msg3 db ' EXEC', 13, 10, 0

    times 510-($-$$) db 0
    dw 0xAA55                   ; boot signature

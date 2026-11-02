; stage1.asm -- RUNG2 MBR: decodes stage2 out of PIXEL PLANES on the medium.
;
; Rung 1 proved pixels can boot a machine when a host-side decoder serves
; the bytes (NBD shim). Rung 2 removes the shim: this MBR reads the medium
; itself (BIOS int 13h), de-interleaves four channel planes into stage2,
; checksums the decoded bytes against a build-time gate constant, and only
; then transfers control. The payload byte stream does not exist
; contiguously on the medium (gate leg [5] proves no two consecutive
; payload bytes are ever adjacent), so execution here REQUIRES the
; pixel-domain decode. Corruption of one payload pixel is caught by the
; checksum and specified-fails as GATE=FAIL with no transfer of control.
;
; Medium layout (the raw RGBA pixel stream IS the IDE disk image):
;   bytes 0..511              stage1 (this code), consecutive packing
;                             (R=b0,G=b1,B=b2,A=b3) - BIOS loads it as-is.
;   bytes 512..512+4*PLANE-1  stage2 as FOUR CHANNEL PLANES:
;                             payload byte i -> plane p=i%4, slot j=i//4
;                             -> medium byte 512 + p*PLANE + j.
; Constants come from stage1_const.inc, generated from stage2.bin at
; build time (run_gate2.sh step [0]).

BITS 16
ORG 0x7C00

COM1     equ 0x3F8
SRC_SEG  equ 0x1000              ; raw payload pixels land here (int 13h)
DST_OFF  equ 0x7E00              ; decoded stage2 lands here; we jump to it

%include "stage1_const.inc"      ; PLANE_LEN PAYLOAD_LEN PAYLOAD_SECTORS EXPECTED_SUM

start:
    cld
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax                   ; ES=0: stosb writes decoded bytes at DST_OFF
    mov ss, ax
    mov sp, 0x7C00
    sti

    ; ---- COM1: 115200 baud, 8N1 ----
    mov dx, COM1+1               ; IER: disable serial interrupts
    xor al, al
    out dx, al
    mov dx, COM1+3               ; LCR: DLAB on
    mov al, 0x80
    out dx, al
    mov dx, COM1                 ; DLL: divisor low = 1
    mov al, 0x01
    out dx, al
    mov dx, COM1+1               ; DLM: divisor high = 0
    xor al, al
    out dx, al
    mov dx, COM1+3               ; LCR: 8N1, DLAB off
    mov al, 0x03
    out dx, al

    mov si, msg_hello
    call puts

    ; ---- read the payload pixels ourselves: LBA 1.. -> SRC_SEG:0000 ----
    mov si, dap
    mov dl, 0x80
    mov ah, 0x42                 ; extended read (LBA)
    int 0x13
    jnc .read_ok
    mov si, msg_readfail
    call puts
    jmp .halt
.read_ok:

    ; ---- de-interleave 4 channel planes -> DST_OFF (ES=0) ----
    ; plane p occupies SRC_SEG:[p*PLANE_LEN .. (p+1)*PLANE_LEN); si walks
    ; plane bases naturally as each pass consumes PLANE_LEN bytes.
    ; (nasm %% local labels are only legal inside %macro, not %rep, hence
    ; the macro + 4 explicit invocations.)
    mov ax, SRC_SEG
    mov ds, ax
    xor si, si
%macro DEPLANE 1
    mov di, DST_OFF+%1
    mov cx, PLANE_LEN
%%plane:
    lodsb                        ; al = ds:si, si++
    stosb                        ; es:di = al, di++
    add di, 3                    ; net di += 4: next slot of this channel
    loop %%plane
%endmacro
    DEPLANE 0
    DEPLANE 1
    DEPLANE 2
    DEPLANE 3

    ; ---- integrity gate: sum decoded payload mod 65536 vs EXPECTED_SUM ----
    xor ax, ax
    mov ds, ax
    mov si, DST_OFF
    mov cx, PAYLOAD_LEN
    xor bx, bx
.chk:
    lodsb
    add bl, al
    adc bh, 0                    ; carry into BH; overflow out of BX = mod 2^16
    loop .chk

    cmp bx, EXPECTED_SUM
    je .gate_pass
    mov si, msg_fail
    call puts
    mov ax, bx
    call puthex4
    mov si, msg_crlf
    call puts
    jmp .halt
.gate_pass:
    mov si, msg_pass
    call puts
    jmp 0x0000:DST_OFF           ; execute the decoded pixels

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
    rol ax, 1                    ; rotate top nibble into AL[3:0]
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

msg_hello    db 'PXC1-RUNG2', 13, 10, 0
msg_pass     db 'GATE=PASS', 13, 10, 0
msg_fail     db 'GATE=FAIL SUM=', 0
msg_crlf     db 13, 10, 0
msg_readfail db 'READFAIL', 13, 10, 0

dap:                         ; disk address packet for int 13h AH=42h
    db 0x10, 0
    dw PAYLOAD_SECTORS       ; sectors to read
    dw 0x0000                ; offset
    dw SRC_SEG               ; segment
    dq 1                     ; LBA 1 (first payload sector)

    times 510-($-$$) db 0
    dw 0xAA55                ; boot signature

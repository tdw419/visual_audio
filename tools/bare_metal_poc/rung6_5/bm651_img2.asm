; bm651_img2.asm -- the image that gets EXECUTED out of decoded pixels.
;
; Entered by rung6_5's stage2 at IMG2_SEG:0 with DS=ES=IMG2_SEG, SS:SP left at
; 0:7C00, IF=0 (the leg `cli`s before the jump: R-SCOPE-3), and ES:SI pointing
; at the 14-byte contract block. It owns every GPR except SS:SP, and returns
; with the far return address stage2 pushed. Nothing else is promised, and
; nothing else may be assumed: this file is DATA until the loader jumps into
; it, which is the whole claim under test.
;
; Four builds from one source, each a leg of the row:
;   (none)        green: banner, echo, mailbox, retf
;   -DNO_ECHO     prints the banner but does not record the NID in memory
;                 -> stage2's own check must refuse: EXEC=NO-BANNER
;   -DNO_MAILBOX  runs to the end of everything except its contract word
;                 -> EXEC=BAD-MAILBOX 0000
;   -DHALT        banners, echoes, then hangs: control never comes back
;                 -> the host must call it a timeout, from OUTSIDE, because no
;                 guest-side watchdog can exist here
; Every one of them pads to exactly 2048 bytes: rung5_consts asserts that
; length, so the variants cannot drift apart by size without the build saying
; so. Padded with 0x00, which the CRC covers like any other byte.

BITS 16
ORG 0

COM1 equ 0x3F8
MAILBOX equ 0x4B4F
ARG_NID   equ 8                    ; contract words, as stage2 lays them out
ARG_MBOX  equ 10
ARG_ECHO  equ 12

start:
    cld
    mov bx, si                     ; the arg block, in a register we own

    mov ax, [es:bx+ARG_NID]
    push ax
    mov si, msg_banner
    call puts
    pop ax
    call puthex4
    mov si, msg_crlf
    call puts

%ifndef NO_ECHO
    mov ax, [es:bx+ARG_NID]
    mov [es:bx+ARG_ECHO], ax       ; "I ran", in memory, for the loader to check
%endif

%ifdef HALT
    cli
.hang:
    hlt
    jmp .hang                      ; never returns: the host times this out
%endif

%ifndef NO_MAILBOX
    mov word [es:bx+ARG_MBOX], MAILBOX     ; "I finished", per the contract
%endif

    retf                           ; to the far address stage2 pushed

; ---- its own serial output: an independent image does not link against the
; ---- loader. Same 16550 discipline the loader measured, written fresh here.
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

msg_banner db 'IMG2EXEC BANNER NID=', 0
msg_crlf   db 13, 10, 0

; exactly 2048 bytes, whatever the variant: the assert is in the build, and
; rung5_consts.py asserts the length again from the other side.
times 2048 - ($ - $$) db 0x00

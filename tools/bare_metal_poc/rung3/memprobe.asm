; memprobe.asm -- RUNG3 anchor: what memory can a 512-byte stub address?
; A real payload (4096x4096 RGBA = 64 MB) cannot live in real mode's 1 MB.
; This probe boots a bare 512-byte sector and prints over COM1:
;   EXT88   int 15h AH=88h  extended KB   (legacy, caps at 0xFFFF)
;   E801A/B int 15h AX=E801 KB(1-16M) / 64KB-blocks(>16M)
;   E820    int 15h AX=E820 entry count (full map exists?)
; Result decides whether the rung3 loader needs a PMODE/unreal switch
; before it can plane-decode multi-MB payloads. See RECEIPT_RUNG2.md
; "Rung 3" discussion. No payload, no planes -- pure probe.

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

    ; ---- 88h: extended memory KB ----
    mov ah, 0x88
    int 0x15
    mov si, msg88
    call puts
    call puthex4
    mov si, msg_crlf
    call puts

    ; ---- E801: KB(1-16M) in AX, 64KB blocks(>16M) in BX ----
    mov ax, 0xE801
    int 0x15
    jnc .ok801
    xor ax, ax
    xor bx, bx
.ok801:
    mov si, msg801a
    call puts
    call puthex4
    mov si, msg801b
    call puts
    mov ax, bx
    call puthex4
    mov si, msg_crlf
    call puts

    ; ---- E820: count map entries (buffer at 0x7000, clear of BIOS data) ----
    xor bp, bp                    ; entry count
    xor ebx, ebx                  ; continuation value: first call = 0
.e820prep:
    mov di, 0x7000
    mov ecx, 24                   ; request 24-byte (ACPI) entries
    mov edx, 0x534D4150           ; 'SMAP' before every call (NOT 0x504D5341
                                  ;  -- that is byte-reversed 'ASMP' and
                                  ;  SeaBIOS correctly rejects it, CF set)
    mov eax, 0xE820
    int 0x15
    jc .e820done                  ; CF set: end of list (or unsupported)
    inc bp
    cmp bp, 32                    ; safety cap: SeaBIOS maps are small
    jae .e820done
    test ebx, ebx
    jz .e820done
    jmp .e820prep
.e820done:
    mov si, msg820
    call puts
    mov ax, bp
    call puthex4
    mov si, msg_crlf
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

msg_hello db 'MEMPROBE',13,10,0
msg88     db 'EXT88=',0
msg801a   db 'E801A=',0
msg801b   db ' E801B=',0
msg820    db 'E820=',0
msg_crlf  db 13,10,0

    times 510-($-$$) db 0
    dw 0xAA55

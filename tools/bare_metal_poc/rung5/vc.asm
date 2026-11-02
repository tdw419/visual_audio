; stage2.asm -- RUNG5 payload: BM-501 second-image read + BM-502 write leg.
;
; Entered at ORG 0 in DST_SEG (retf from stage1, rung-4 unchanged). The
; loader already CRC32-gated OUR image; this stage does three new things:
;
;   BM-501: read a SECOND pixel-encoded image from the same medium
;     (int 13h AH=42h, four channel planes at IMG2_BASE_LBA), compute
;     its CRC32 with the same reflected-0xEDB88320 routine, and print
;     IMG2 CRC=<computed>. REFUSAL on mismatch:
;     IMG2 FAIL CRC=<computed> EXP=<expected>  (computed first -- the
;     rung-4 DEFECT-R4PRINT lesson; refusal labels computed vs expected).
;   BM-502: write a 4-sector marker block via int 13h AH=43h (EDD write)
;     to WR_LBA -- a sector range asserted disjoint from stage1, the
;     stage2 planes, and the second image (disjointness is a BUILD-TIME
;     %error in this file, and a gate assertion over the layout consts).
;     The marker is the payload bytes [0,2048) of our own image -- the
;     guest writes what it decoded, not host-hand-fed bytes.
;   Then it prints the rung-4 style self receipt (SIZE/CKSUM/EXEC) and
;   halts. The GATE5= line bundles all three verdicts:
;     GATE5=IMG2CRC=<crc> WRITE=OK | IMG2CRCFAIL EXP=<expected>
;
; 16-bit discipline (rung-4 receipts): every 16-bit loop counter is
; banked to <=65536 iterations; segment-relative walks step ES/SI/DI
; per 64 KB bank; no 32-bit `loop` counts exist.
;
; Scale note: rung-5 gates run at RUNG4_SCALE=65536 (the rung's claimed
; scale for the new legs). The banked sums mirror rung 4 so larger
; scales remain correct by construction.

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

    ; ---- COM1: 115200 8N1 (stage1 already programmed it, but a bare
    ; stage2 run must stand alone; re-init is idempotent) ----
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
    jmp halt

    ; ================= BM-501: read + CRC the second image ================
    ; Read IMG2_SECTORS sectors at IMG2_BASE_LBA into IMG2_SEG:0000,
    ; then CRC32 them with the banked routine (IMG2_LEN = 2048 = 1 bank
    ; window; the walk stays inside one segment, cx = IMG2_LEN/2 words
    ; via the same sum-loop structure rung-4 stage2 used for 64 KB).
    mov si, img2_dap
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    jnc .img2_ok
    mov si, msg_img2readfail
    call puts
    jmp halt
.img2_ok:
    mov ax, IMG2_SEG
    mov ds, ax
    xor si, si
    mov cx, IMG2_LEN/2           ; 1024 word iterations
    xor bx, bx                   ; sum16 of img2 (witness line)
.img2_sum:
    lodsw
    add bl, al
    adc bh, 0
    add bl, ah
    adc bh, 0
    loop .img2_sum

    mov ax, IMG2_SEG
    mov es, ax
    xor si, si
    call crc32_calc              ; -> EAX = CRC32 over img2 window
    push eax                     ; DEFECT-R5CRCSEG: DS=IMG2_SEG here, so
                                 ; [img2crcline] would write INSIDE the
                                 ; img2 window, and the later reads (DS=0)
                                 ; would print garbage. Keep the CRC in
                                 ; a register across the DS restore.
    xor ax, ax
    mov ds, ax

    cmp eax, EXPECTED_IMG2_CRC
    jne .img2_fail
    pop eax                      ; the computed CRC
    mov [img2crcline], eax       ; DS=0 now: safe store
    mov si, msg_img2ok
    call puts
    mov eax, [img2crcline]
    call puthex8
    mov si, msg_crlf
    call puts
    jmp .img2_done
.img2_fail:
    pop eax
    mov [img2crcline], eax
    mov si, msg_img2fail
    call puts
    mov eax, [img2crcline]
    call puthex8
    mov si, msg_img2exp
    call puts
    mov ax, EXPECTED_IMG2_CRC >> 16
    call puthex4
    mov ax, EXPECTED_IMG2_CRC & 0xFFFF
    call puthex4
    mov si, msg_crlf
    call puts
    jmp halt                     ; REFUSAL: no write leg on a bad read
.img2_done:

    ; ================= BM-502: write the marker block =====================
    ; Marker = our own decoded payload bytes [0, 2048) at DST_SEG:0.
    ; Copy them into the IMG2_SEG scratch (above the write target, no
    ; overlap: IMG2_SEG is a read window AND this bounce buffer; the
    ; write target lives on the MEDIUM at WR_LBA, not in RAM), point the
    ; EDD write packet at it, and issue AH=43h with write-verify (AL=2).
    push word DST_SEG
    pop ds
    xor si, si                   ; DS:SI = our payload bytes [0,2048)
    mov ax, IMG2_SEG
    mov es, ax
    xor di, di
    mov cx, 1024
    rep movsw                    ; copy 2048 bytes payload -> bounce buffer
    push ax
    mov ax, IMG2_SEG
    mov ds, ax                   ; write packet buffer segment
    pop ax
    xor ax, ax
    mov ds, ax                   ; DAP lives in DS:SI at segment 0

    mov si, wr_dap
    mov dl, 0x80
    mov ah, 0x43
    mov al, 2                    ; write with verify
    int 0x13
    jnc .wr_ok
    mov si, msg_wrfail
    call puts
    jmp halt
.wr_ok:
    mov si, msg_wrok
    call puts
    mov si, msg_crlf
    call puts

    ; ================= self receipt (rung-4 style) ========================
    push word DST_SEG
    pop ds
    xor si, si
    mov cx, PAYLOAD_LEN>>1
    xor bx, bx
.self_sum:
    lodsw
    add bl, al
    adc bh, 0
    add bl, ah
    adc bh, 0
    loop .self_sum
    xor ax, ax
    mov ds, ax

    mov si, msg_sz
    call puts
    mov ax, PAYLOAD_LEN / 1024
    call putdec
    mov si, msg_kbu
    call puts
    mov si, msg2
    call puts
    mov ax, bx
    call puthex4
    mov si, msg3
    call puts
.halt:
    hlt
    jmp .halt

halt:
    hlt
    jmp halt

; ---- CRC32 (zlib: reflected poly 0xEDB88320, in/out 0xFFFFFFFF) ----
; identical algorithm to rung-4 stage1 crc32_calc; walks ES:SI over
; CX*2 bytes... here: IMG2_LEN bytes as CX=IMG2_LEN/2 word-loops would
; break the byte-CRC, so we keep rung-4's byte loop: CX = IMG2_LEN
; bytes (2048 fits 16 bits). Clobbers EAX EBX ECX EDX ESI BP.
crc32_calc:
    push es
    mov eax, 0xFFFFFFFF
    mov bp, IMG2_LEN/65536 + 1   ; 2048 bytes -> 1 bank walk, bp=1
    xor si, si
    mov cx, IMG2_LEN             ; byte count (<=65536: the whole image)
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
    push eax
    mov ax, es
    add ax, 0x1000
    mov es, ax
    pop eax
    jmp .byte_loop
.done:
    xor eax, 0xFFFFFFFF
    pop es
    ret

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

; ---- print EAX as 8 uppercase hex digits ----
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

msg_hello       db 'PXC1-RUNG5', 13, 10, 0
msg_img2ok      db 'IMG2 CRC=', 0
msg_img2fail    db 'IMG2 FAIL CRC=', 0
msg_img2exp     db ' EXP=', 0
msg_img2readfail db 'IMG2 RDFAIL', 13, 10, 0
msg_wrok        db 'WRITE=OK', 0
msg_wrfail      db 'WRITE=FAIL', 13, 10, 0
msg_sz          db 'STAGE2 SIZE=', 0
msg_kbu         db ' KB', 13, 10, 0
msg2            db 'STAGE2 CKSUM=', 0
msg3            db ' EXEC', 13, 10, 0
msg_crlf        db 13, 10, 0

img2crcline: dd 0

; ---- EDD packets (DS = 0) ----
align 2
img2_dap:
    db 0x10, 0
    dw IMG2_SECTORS      ; sectors to read
    dw 0x0000            ; offset
    dw IMG2_SEG          ; segment
img2_dap_lba:
    dq IMG2_BASE_LBA     ; fixed: no patching needed

align 2
wr_dap:
    db 0x10, 0
    dw WR_SECTORS        ; sectors to write
    dw 0x0000            ; offset
    dw IMG2_SEG          ; segment (bounce buffer = img2 window, RAM only)
wr_dap_lba:
    dq WR_LBA            ; fixed write target (gate-asserted disjoint)

; PAYLOAD_LEN arrives from stage1_const.inc (shared with stage1);
; the rung-5 layout consts arrive from rung5_consts.py -D flags.
PAYLOAD_LEN equ RUNG4_SCALE

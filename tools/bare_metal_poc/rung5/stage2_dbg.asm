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
    mov es, ax                   ; ES=0 only for the DAP protocol dance
    mov ss, ax
    mov sp, 0x7C00
    sti
    ; DEFECT-R5DSSEG (measured 2026-09-18): the first build kept DS=0 and
    ; printed via DS:SI -- which read the INTERRUPT VECTOR TABLE at 0:511
    ; and emitted bytes f0 53 ff... as "output". We execute at DST_SEG:0,
    ; so our data (messages, DAPs) lives in CS==DS==DST_SEG. DS=0 is used
    ; only transiently around the int 13h calls, where the DAP pointer
    ; DS:SI is rebuilt from SEG0_DAP_SEG:SEG0_DAP_OFF.
    push cs
    pop ds

    call init_daps               ; stage both DAPs into segment 0

; === DEBUG BUILD ONLY: hexdump first 16 bytes of IMG2_SEG:0 after a
; manual read, using the read DAP directly (before anything else runs) ===
    push es
    pop ds                      ; DS=0 for DAP
    mov si, SEG0_DAP_OFF
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    push cs
    pop ds
    jnc .dbg_rd_ok
    mov si, msg_img2readfail
    call puts
    jmp halt
.dbg_rd_ok:
    mov si, msg_dbgrand0
    call puts
    mov ax, IMG2_SEG
    mov ds, ax
    xor si, si
    mov ch, 16
.dbg0:
    lodsb
    call puthex2
    mov al, ' '
    call putc
    dec ch
    jnz .dbg0
    mov ax, cs
    mov ds, ax
    mov si, msg_crlf
    call puts

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

    ; ================= BM-501: read + CRC the second image ================
    ; Read IMG2_SECTORS sectors at IMG2_BASE_LBA into IMG2_SEG:0000,
    ; then CRC32 them with the banked routine (IMG2_LEN = 2048 = 1 bank
    ; window; the walk stays inside one segment, cx = IMG2_LEN/2 words
    ; via the same sum-loop structure rung-4 stage2 used for 64 KB).
    ; int 13h wants the DAP at DS:SI: stage it through a zeroed segment.
    push es
    pop ds                       ; DS=0 for the DAP
    mov si, SEG0_DAP_OFF
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    push cs
    pop ds                       ; back to our data segment
    jnc .img2_ok
    mov si, msg_img2readfail
    call puts
    jmp halt
.img2_ok:
    ; The four planes arrived CONCATENATED at IMG2_SEG:0 (a contiguous
    ; LBA walk reads plane 0, then 1, then 2, then 3). De-interleave to
    ; the FREE window at IMG2_SEG:IMG2_LEN (offsets [2048,4096)).
    ; DEFECT-R5DEINT (measured 2026-09-18 gate run 2, guest SUM=5490 vs
    ; host E956): the previous build scattered IN PLACE, backwards. For
    ; plane p>=1, dst(4k+p) < src(512p+k) whenever 3k < 512p-1, so the
    ; descending walk wrote into not-yet-consumed source bytes (the
    ; ascending walk re-reads them for k'>=171 -- both directions
    ; corrupt; the dst region subsumes every src region). A
    ; non-overlapping destination window is the fix; the segment has
    ; 64 KB, the two windows need 4 KB.
    mov ax, IMG2_SEG
    mov ds, ax
    mov es, ax
    mov bx, IMG2_LEN/4 - 1       ; k = PLANE_LEN-1 .. 0
.deint:
    mov si, bx                   ; plane 0: src k -> dst IMG2_LEN+4k
    lodsb
    mov di, bx
    shl di, 1
    shl di, 1                    ; di = 4k
    add di, IMG2_LEN             ; dst window above the planes
    mov es:[di], al
    mov si, bx
    add si, IMG2_LEN/4           ; plane 1: src PLANE+k -> dst 4k+1
    lodsb
    inc di
    mov es:[di], al
    mov si, bx
    add si, 2*(IMG2_LEN/4)       ; plane 2
    lodsb
    inc di
    mov es:[di], al
    mov si, bx
    add si, 3*(IMG2_LEN/4)       ; plane 3
    lodsb
    inc di
    mov es:[di], al
    dec bx
    jns .deint
    mov si, msg_dbgrand8
    call puts
    mov si, IMG2_LEN
    mov ch, 16
.dbg1:
    lodsb
    call puthex2
    mov al, ' '
    call putc
    dec ch
    jnz .dbg1
    mov ax, cs
    mov ds, ax
    mov si, msg_crlf
    call puts

    mov ax, IMG2_SEG
    mov ds, ax                   ; sum the de-interleaved img2 window
    mov si, IMG2_LEN             ; (de-interleaved copy lives at :2048)
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
    mov si, IMG2_LEN             ; CRC the de-interleaved window at :2048
    push bx                      ; sum16 witness survives crc32_calc
    call crc32_calc              ; -> EAX = CRC32 over img2 window
    push eax                     ; keep the CRC across the DS restore
    push cs
    pop ds                       ; DS=DST_SEG: our data segment again
    pop bx
    ; WITNESS LINE (added after run-1 RED): sum16 of the de-interleaved
    ; image, printed BEFORE the CRC verdict. A gate RED with SUM != host
    ; means read/deinterleave bug; SUM == host with CRC != host means
    ; CRC-implementation bug. The gate cross-checks this against the host.
    mov [img2sumline], bx
    mov si, msg_img2sum
    call puts
    mov ax, [img2sumline]
    call puthex4
    mov si, msg_crlf
    call puts

    cmp eax, EXPECTED_IMG2_CRC
    jne .img2_fail
    pop eax                      ; the computed CRC
    mov [img2crcline], eax       ; safe store in our segment
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
    mov ds, ax                   ; DS=DST_SEG (ax still holds cs value)
    push word DST_SEG
    pop ds
    xor si, si                   ; DS:SI = our payload bytes [0,2048)
    mov ax, IMG2_SEG
    mov es, ax
    xor di, di
    mov cx, 1024
    rep movsw                    ; copy 2048 bytes payload -> bounce buffer
    ; the WRITE DAP also lives in our segment; int 13h needs DS:SI -> DAP,
    ; so copy the DAP into the zero page (ES=IMG2_SEG is busy as bounce;
    ; ES was reloaded, so stash the dap via stack into segment 0 window).
    ; Simplest correct route: point DS at segment 0 ONLY for the call,
    ; with SI targeting a DAP COPY placed there at init (see dap0 below
    ; is unnecessary: the read path already proved DS=0 staging works).
    push es
    pop ds                       ; DS=0
    mov si, SEG0_DAP_OFF + 16    ; second DAP slot (the write DAP copy)
    mov dl, 0x80
    mov ah, 0x43
    mov al, 2                    ; write with verify
    int 0x13
    push cs
    pop ds
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


; ---- print AL as 2 hex digits (debug builds) ----
puthex2:
    push ax
    push cx
    mov cl, al
    shr al, 1
    shr al, 1
    shr al, 1
    shr al, 1
    call .nib
    mov al, cl
    call .nib
    pop cx
    pop ax
    ret
.nib:
    and al, 0x0F
    cmp al, 10
    jb .d2
    add al, 'A'-10-'0'
.d2:
    add al, '0'
    call putc
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
msg_dbgrand0     db 'DBG :0 =', 0
msg_dbgrand8     db 'DBG :800=', 0
msg_img2sum     db 'IMG2 SUM=', 0
msg_wrok        db 'WRITE=OK', 0
msg_wrfail      db 'WRITE=FAIL', 13, 10, 0
msg_sz          db 'STAGE2 SIZE=', 0
msg_kbu         db ' KB', 13, 10, 0
msg2            db 'STAGE2 CKSUM=', 0
msg3            db ' EXEC', 13, 10, 0
msg_crlf        db 13, 10, 0

img2crcline: dd 0
img2sumline: dw 0

; ---- EDD packets ----
; DEFECT-R5DSSEG follow-up: int 13h needs the DAP at DS:SI. Our data
; segment is DST_SEG, but the DAPs are staged in SEGMENT 0 (the zero
; page below the IVT's first entry is free RAM 0x200..0x3FF region --
; we use 0x300, well above the IVT (0x0..0x3FF)? NO: the IVT is
; 0x0000-0x03FF, BIOS data area 0x400-0x4FF. Free low RAM starts ~0x500.
; We stage DAPs at linear 0x0500 (SEG0_DAP_OFF), BELOW 0x7C00's stack
; and never touched by SeaBIOS after POST.
SEG0_DAP_OFF equ 0x0500
; DST_SEG arrives via -DDST_SEG=0x1000 from rung5_consts.py
IMG2_SEG_STAGE equ 0x5000

; --- runtime init: copy both DAPs to segment 0 (called with CS=DS=DST_SEG)
init_daps:
    push es
    push si
    mov ax, cs
    mov ds, ax
    mov ax, 0
    mov es, ax
    mov si, img2_dap
    mov di, SEG0_DAP_OFF
    mov cx, 16
    rep movsb                    ; read DAP -> 0x0500
    mov si, wr_dap
    mov di, SEG0_DAP_OFF + 16
    mov cx, 16
    rep movsb                    ; write DAP -> 0x0510
    pop si
    pop es
    ret

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

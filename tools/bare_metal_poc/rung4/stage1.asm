; stage1.asm -- RUNG4 MBR: decodes a >=64 KB stage2 out of PIXEL PLANES.
;
; Rung 2 proved loader-side decode at 144 B (single sector, one window).
; Rung 4 scales the SAME mechanism (Path A, pure real mode, per
; rung3/ANCHORS.md -- zero new primitives):
;
;   * The payload is read from the medium in CHUNKS through a fixed
;     segment window (EDD AH=42h loop, CHUNK_SECTORS per call).
;   * Each chunk de-interleaves streaming into the payload's final
;     home at DST_SEG:0000 (linear 0x10000). Because a plane's slice of
;     the medium is CONTIGUOUS, the per-plane chunk loop is: read chunk
;     at running LBA -> rep movsb CHUNK_BYTES straight to the running
;     destination offset (the plane scatter happens across the four
;     plane loops, exactly as in rung 2).
;   * CRC32 (reflected 0xEDB88320, init/final 0xFFFFFFFF -- the
;     zlib/PNG standard) is computed over the FULL decoded image
;     BEFORE any transfer of control; sum16 rides along as a cheap
;     pre-filter. Refusal prints computed AND expected CRC.
;
; Medium layout (raw RGBA pixel stream == the IDE disk image):
;   bytes 0..511              stage1 (this code), consecutive packing
;   bytes 512..512+4*PLANE-1  stage2 as FOUR CHANNEL PLANES:
;                             payload byte i -> plane p=i%4, slot j=i//4
;                             -> medium byte 512 + p*PLANE + j.
; Constants come from stage1_const.inc, generated from the padded
; stage2 at build time (run_gate4.sh step [0]).
;
; Constraints the gate asserts at build time:
;   PLANE_LEN % CHUNK_BYTES == 0        (exact chunking, no ragged tail)
;   PLANE_LEN <= 0xFFFF and p*PLANE_LEN fits 16 bits (it does: <= 3*64K/4)
;   DST_SEG:0000 + PAYLOAD_LEN stays inside the DST segment (64 KB)
;   CHUNK_BYTES <= window segment (64 KB)

BITS 16
ORG 0x7C00

COM1        equ 0x3F8
SRC_SEG     equ DST_SEG+PAYLOAD_BANKS*0x1000  ; window ABOVE dest banks
DST_SEG     equ 0x1000           ; decoded stage2 lands at DST_SEG:0000
CHUNK_BYTES equ CHUNK_SECTORS*512

%include "stage1_const.inc"      ; PLANE_LEN PAYLOAD_LEN PAYLOAD_SECTORS
                                 ; CHUNK_SECTORS CHUNKS_PER_PLANE
                                 ; EXPECTED_CRC EXPECTED_SUM

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

    ; ================= streaming read + de-interleave =================
    ; DEFECT-R4SCATTER (measured 2026-09-17): the original plane-outer
    ; loop pinned ES=DST_SEG and let 16-bit DI run p+4*j across the
    ; whole plane: at 256 KB DI wraps at 64 KB and banks 1..3 are never
    ; written (guest 54AA5EB5 vs host 758F5EC8). FIX: bank-outer loop,
    ; ES = DST_SEG + b*0x1000 per 64 KB destination bank; within a bank
    ; DI maxes at 65535, so the scatter can never leave the bank
    ; segment, at ANY scale the bank walk supports. Per (b,p,c) chunk:
    ; LBA = 1 + p*(PLANE/512) + 32*b + 8*c (j_global = 16384*b +
    ; 4096*c + k, medium = 512 + p*PLANE + j_global).
    xor bx, bx                   ; bx = bank index b (0..PAYLOAD_KB/64-1)
r4_bank:
    mov ax, DST_SEG
    mov dx, bx
    shl dx, 12                   ; 0x1000 paragraphs per 64 KB bank
    add ax, dx
    mov es, ax                   ; this bank's destination segment
    mov bp, 0                    ; bp = plane index p (0..3)
r4_plane:
    ; LBA = 1 + p*(PLANE_LEN/512) + 32*b + 8*c  (c patched per chunk)
    mov ax, PLANE_LEN/512
    mul bp                       ; ax = p*(PLANE_LEN/512) (fits 16 bits)
    add ax, 1                    ; + stage1's LBA 0
    mov dx, bx
    shl dx, 5                    ; 32 sectors per bank (16384 slots /512)
    add ax, dx
    mov [lba], ax
    mov di, bp                   ; DI = p + 4*j_local, starts at slot 0
    mov cx, CHUNKS_PER_BANK
r4_chunk:
    push cx
    ; --- read CHUNK_SECTORS at [lba] into SRC_SEG:0000 ---
    mov ax, [lba]
    mov [dap_lba], ax
    mov si, dap
    ; dap_lba high words were zeroed at init time by the `dq 1`; only the
    ; low word is patched per chunk, and per-chunk LBA always fits 16 bits
    ; (max medium payload = 4 planes * 256 slots... 601 sectors at 256 KB).
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    jnc r4_read_ok
    mov si, msg_readfail
    call puts
    jmp halt
r4_read_ok:
    ; --- scatter this chunk into the de-interleaved destination ---
    ; plane p's chunk bytes are payload indices p, p+4, p+8 ... for
    ; slots j_local = c*CHUNK_BYTES .. (c+1)*CHUNK_BYTES-1. DI runs
    ; p + 4*c*CHUNK_BYTES .. +4 per byte, maxing at 65535 within the
    ; bank segment (see DEFECT-R4SCATTER note above).
    push ds
    mov ax, SRC_SEG
    mov ds, ax
    xor si, si
    mov cx, CHUNK_BYTES
%macro SCATTER 0
%%byte:
    lodsb                        ; al = ds:si, si++
    stosb                        ; es:di = al, di++ (DF=0)
    add di, 3                    ; net di += 4: next slot of this channel
    loop %%byte
%endmacro
    SCATTER
    pop ds
    pop cx
    mov ax, CHUNK_SECTORS
    add [lba], ax
    ; NOTE: DI is NOT advanced here: the inner loop's stosb+add-di,3
    ; already steps DI by 4 per byte (4*CHUNK_BYTES per chunk), so the
    ; next chunk of this plane continues at the correct slot offset.
    loop r4_chunk
    inc bp
    cmp bp, 4
    jb r4_plane
    inc bx
    cmp bx, PAYLOAD_BANKS
    jb r4_bank
    ; BP is dead here (plane loop finished): crc32_calc reuses it as the
    ; bank counter without save/restore -- 2 bytes cheaper than push/pop.

    ; ================= CRC32 + sum16 gate (ES=DST_SEG) ================
    mov ax, DST_SEG
    mov es, ax
    xor si, si
    call crc32_calc              ; -> EAX = CRC32 over ES:0 .. PAYLOAD_LEN
    mov [crcline], eax
    cmp eax, EXPECTED_CRC
    jne r4_crc_fail_near
    ; cheap pre-filter: sum16 (banked like the CRC walk)
    xor bx, bx
    mov dx, PAYLOAD_LEN/65536    ; banks
r4_sum:
    xor cx, cx                   ; 65536 bytes this bank (cx=0 idiom)
.sum_loop:
    mov al, [es:si]
    inc si
    add bl, al
    adc bh, 0
    loop .sum_loop
    mov ax, es
    add ax, 0x1000               ; next 64K bank
    mov es, ax
    dec dx
    jnz r4_sum
    ; ---- gate PASS: print receipt, transfer control ----
    mov si, msg_pass
    call puts
    mov eax, [crcline]
    call puthex8
    mov si, msg_crlf
    call puts
    ; transfer control: jump far to DST_SEG:0000 via register-indirect
    push word DST_SEG
    push word 0x0000
    retf                         ; CS=DST_SEG, IP=0 -- stage2 ORG 0
r4_crc_fail_near:
    jmp r4_crc_fail

r4_crc_fail:
    ; Contract (run_gate4.sh leg RED-A): CRC=<computed> EXP=<expected>.
    ; DEFECT-R4PRINT (measured 2026-09-18): the halves were printed
    ; swapped (CRC=EXPECTED, EXP=computed), so the gate's greps for the
    ; computed and expected values both missed a CORRECT refusal.
    mov si, msg_fail
    call puts
    mov eax, [crcline]
    call puthex8
    mov si, msg_exp
    call puts
    mov ax, EXPECTED_CRC >> 16
    call puthex4
    mov ax, EXPECTED_CRC & 0xFFFF
    call puthex4
    mov si, msg_crlf
    ; fall through into halt (size: the jmp halt was dead weight and the
    ; 512-byte MBR budget went negative after DEFECT-R4SCATTER)
halt:
    hlt
    jmp halt

; ---- CRC32 (zlib: reflected poly 0xEDB88320, in/out 0xFFFFFFFF) ----
; input: ES = base segment; walks PAYLOAD_LEN bytes as PAYLOAD_LEN/65536
; banks of 64 KB (ES += 0x1000 per bank).
; BANKED WALK (DEFECT-R4CRC fix): a 16-bit `loop` cannot count past
; 65536, and the previous single-loop 32-bit count silently CRC'd only
; the first 4096 bytes at 256 KB (guest 334D1A75 = crc(folded[:4096]),
; measured 2026-09-17). The walk now iterates PAYLOAD_LEN/65536 banks
; of exactly 64 KB each, advancing ES by 0x1000 per bank -- the same
; proven structure as the sum16 pre-filter below.
; DEFECT-R4CRC2/R4CRC3 (measured 2026-09-17): the bank advance
; (`mov ax, es`) clobbers AX -- the accumulator's low 16 bits. E1AEDFFF
; vs host E1AE9612 was low16 = 0x2000^0xFFFF (last-bank clobber);
; intermediate advances broke 256 KB the same way. EAX is now
; push/pop'd around every advance, and the advance is skipped on the
; last bank entirely.
; clobbers: EAX, EBX, ECX, EDX, ESI, BP (BP is dead at the call site).
crc32_calc:
    push es
    mov eax, 0xFFFFFFFF
    mov bp, PAYLOAD_LEN/65536    ; banks (64 KB == 1, 256 KB == 4)
    xor si, si
.bank:
    xor cx, cx                   ; 65536 iterations (cx=0 idiom)
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
    dec dx                       ; EDX high word is never written: DX is the counter
    jnz .bit_loop
    loop .byte_loop
    dec bp
    jz .done
    push eax                     ; EAX=running CRC: save across ES advance
    mov ax, es
    add ax, 0x1000
    mov es, ax
    pop eax
    jmp .bank
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

; ---- print EAX as 8 uppercase hex digits ----
; (the puthex4 calls skip one bx save: BX reloaded between halves)
puthex8:
    push eax
    push bx
    mov bx, ax
    shr eax, 16
    call puthex4                 ; high 16
    mov ax, bx
    call puthex4                 ; low 16 (BX still holds the low half)
    pop bx
    pop eax
    ret

msg_hello    db 'PXC1-RUNG4', 13, 10, 0
msg_pass     db 'GATE4=PASS CRC=', 0
msg_fail     db 'GATE4=FAIL CRC=', 0
msg_exp      db ' EXP=', 0
msg_crlf     db 13, 10, 0
msg_readfail db 'RDFAIL', 0

crcline: dd 0

align 2
lba:     dw 1

dap:                     ; disk address packet for int 13h AH=42h
    db 0x10, 0
    dw CHUNK_SECTORS     ; sectors to read
    dw 0x0000            ; offset
    dw SRC_SEG           ; segment
dap_lba:
    dq 1                 ; LBA (patched per chunk)

    times 510-($-$$) db 0
    dw 0xAA55            ; boot signature
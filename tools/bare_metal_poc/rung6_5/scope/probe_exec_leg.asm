; probe_exec_leg.asm -- BM650 scoping probe: how many bytes does the
; exec-from-data leg of DESIGN_EXEC_FROM_DATA.md actually cost, when it is
; written the way rung5's landed code writes things?
;
; Standalone: the four rung5 helpers it calls (puts, putc, puthex4, puthex8)
; are declared at the bottom as 3-byte stubs so the block sizes are honest
; (call rel8 = 5 B near / 3 B short -- we use the same 3-byte `call near`
; form rung5 uses, and rung5's helpers are in the same segment). Only the
; NEW code is measured here; the strings are counted in bm650_scope.py.
;
; Every number this file produces is a size, not a behaviour: the leg runs
; nothing. See BM650_SCOPING.md.

BITS 16
ORG 0

; ---- constants as rung5 emits them (rung5_layout.inc + the exec additions)
IMG2_LEN        equ 2048
IMG2_SEG        equ 0x5000
EXEC_SEG        equ IMG2_SEG
EXEC_MAILBOX    equ IMG2_LEN              ; 2048: first byte above the image
EXEC_ARGS       equ EXEC_MAILBOX + 16     ; contract block, 6 words + pad
EXEC_NID_ECHO   equ EXEC_ARGS             ; slot img2 must copy back

; =====================================================================
; 1. contract block + NID hand-off. stage2 owns this memory; img2 reads
;    it through ES:SI. Word 0 is a version/length so a future img2 grows
;    the block instead of reordering it.
; =====================================================================
block_args:
    push ds
    mov ax, EXEC_SEG
    mov es, ax
    xor di, di
    mov di, EXEC_ARGS
    mov word [es:di], IMG2_LEN            ; 0: img2 length
    mov word [es:di+2], 129               ; 1: medium LBA of img2
    mov word [es:di+4], 0x3F8             ; 2: COM1
    mov word [es:di+6], EXEC_SEG          ; 3: trampoline CS
    mov word [es:di+8], EXPECTED_EXEC_NID ; 4: NID img2 must echo in its banner
    mov word [es:di+10], 0                ; 5: mailbox, cleared before the jump
    mov word [es:di+12], 0                ; 6: NID echo, cleared too
    pop ds
    ret

; =====================================================================
; 2. copy-down: IMG2_SEG:2048 -> IMG2_SEG:0, 1024 words, BACKWARD
;    (R-DESIGN-1: dst = src-2048 with full overlap; a forward rep movsw
;    reads bytes a lower destination already overwrote).
; =====================================================================
copy_down:
    push ds
    push es
    mov ax, EXEC_SEG
    mov ds, ax
    mov es, ax
    std                                 ; DF=1
    mov si, IMG2_LEN + IMG2_LEN - 2     ; src: last word of the window
    mov di, IMG2_LEN - 2                ; dst: last word of the image
    mov cx, IMG2_LEN / 2
    rep movsw
    cld
    pop es
    pop ds
    ret

; =====================================================================
; 3. the jump and the receipt. Entry state per the design's table:
;    CS:IP = EXEC_SEG:0, DS=ES=EXEC_SEG, SS:SP untouched (0:7C00), CLD,
;    IF=0, ES:SI -> the contract block.
; =====================================================================
exec_and_receipt:
    push es
    push ds
    mov ax, EXEC_SEG
    mov ds, ax
    mov es, ax
    mov si, EXEC_ARGS                   ; arg block pointer, per the contract
    push word EXEC_SEG                  ; far return: stage2's receipt label
    push word .back                     ; retf from img2 lands here
    jmp EXEC_SEG:0
.back:
    ; img2 returns with AX = the mailbox word (redundant echo of memory)
    cmp word [es:EXEC_ARGS+10], 0x4B4F
    jne .bad_mailbox
    mov ax, [es:EXEC_ARGS+12]           ; img2's echo
    cmp ax, [es:EXEC_ARGS+8]            ; vs the NID we handed it
    jne .no_banner
    mov si, msg_execok                  ; 'EXEC=OK'
    call puts
    jmp .done
.bad_mailbox:
    mov si, msg_badmbx
    call puts
    mov ax, [es:EXEC_ARGS+10]
    call puthex4                        ; the actual word, computed-first
    jmp .receipt_print
.no_banner:
    mov si, msg_nobanner
    call puts
    jmp .receipt_print
.done:
    pop ds
    pop es
    ret
.receipt_print:
    mov si, msg_crlf
    call puts
    pop ds
    pop es
    jmp halt_stub

; =====================================================================
; 4. the whole-string refusal form the design wants for the banner: print
;    the NID we expected against the echo we got. Measured separately
;    because it is the version that keeps DEFECT-R4PRINT's order (got
;    before expected).
; =====================================================================
banner_receipt_verbose:
    mov si, msg_bannertok
    call puts
    mov ax, [es:EXEC_ARGS+12]
    call puthex4
    mov si, msg_expsep
    call puts
    mov ax, [es:EXEC_ARGS+8]
    call puthex4
    mov si, msg_crlf
    call puts
    ret

; ---- stubs so the blocks above assemble as they will in stage2 ---------
puts:                                   ; 3-byte placeholders: rung5's real
    ret                                 ; puts/puthex4 are 24 B / 39 B and
puthex4:                                ; are NOT new cost here.
    ret
halt_stub:
    hlt
    jmp halt_stub

msg_execok      db 'EXEC=OK', 13, 10, 0
msg_badmbx      db 'EXEC=BAD-MAILBOX ', 0
msg_nobanner    db 'EXEC=NO-BANNER', 13, 10, 0
msg_bannertok   db 'IMG2EXEC BANNER NID=', 0
msg_expsep      db ' EXP=', 0
msg_crlf        db 13, 10, 0

EXPECTED_EXEC_NID equ 0x1234

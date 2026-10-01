import sys
src = open('stage2.asm').read()

# after "call init_daps", insert a raw hexdump of the read window and of
# the medium-equivalent bytes we EXPECT (no guest knowledge of medium —
# just dump; host compares)
hook = "    call init_daps               ; stage both DAPs into segment 0\n"
dbg = hook + """
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
"""
assert hook in src
src = src.replace(hook, dbg, 1)

# deint debug: dump 16 bytes at IMG2_SEG:0x800 right after the deint loop
old_tail = """    dec bx
    jns .deint
"""
new_tail = """    dec bx
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
"""
assert old_tail in src
src = src.replace(old_tail, new_tail, 1)

# messages + puthex2
src = src.replace(
    "msg_img2readfail db 'IMG2 RDFAIL', 13, 10, 0",
    "msg_img2readfail db 'IMG2 RDFAIL', 13, 10, 0\n"
    "msg_dbgrand0     db 'DBG :0 =', 0\n"
    "msg_dbgrand8     db 'DBG :800=', 0", 1)

puthex2 = """
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
"""
src = src.replace("; ---- print ASCIIZ at SI over COM1 ----", puthex2 + "\n; ---- print ASCIIZ at SI over COM1 ----", 1)

open('stage2_dbg.asm', 'w').write(src)
print("stage2_dbg.asm written")

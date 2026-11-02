; bm801_beacon.asm -- VGA text-mode receipt beacon, for TASK_BM801's fallback
; receipt channel ("VGA text beacon verified by XOR-diff glyph matching, not
; OCR", ROADMAP.md). Headless-bootable: everything the host learns about the
; guest comes from one screendump of the emulated VGA, so the same reader works
; on a box with no serial port.
;
; Screen layout -- the geometry the host reader assumes lives here:
;   rows 0..15, cols 0..15 : 16x16 code-page block. Cell (r,c) shows glyph
;                            code r*16+c, attribute ATTR_ATLAS.
;   row 20, col 0          : MSG, attribute ATTR_MSG
;   row 21, col 0          : MSG, attribute ATTR_MSG2
;   everywhere else        : fill code 0xB0, attribute ATTR_ATLAS
; The two message lines carry the same text in two colours that differ from
; each other and from the atlas block, so colour-blind matching is proved
; rather than assumed.
;
; Build: nasm -o bm801_beacon.bin bm801_beacon.asm   (512 bytes, no fat)

BITS 16
ORG 0x7C00

VIDSEG      equ 0xB800
COLS        equ 80
CELLS       equ 2000          ; 80 x 25
FILL_CODE   equ 0xB0          ; shaded block -- 0xDB measures BLANK in this font

ATTR_ATLAS  equ 0x07          ; black on light grey
ATTR_MSG    equ 0x1E          ; bright green on bright blue
ATTR_MSG2   equ 0x0F          ; bright white on black

ATLAS_SIDE  equ 16            ; 16x16 block == the full 256-code page
MSG_ROW     equ 20
MSG2_ROW    equ 21

start:
    cli
    xor  ax, ax
    mov  ds, ax
    mov  ax, 0x9000
    mov  ss, ax
    mov  sp, 0xFFFE
    sti

    mov  ax, VIDSEG
    mov  es, ax

    ; ---- fill every cell with FILL_CODE / ATTR_ATLAS
    xor  di, di
    mov  ax, FILL_CODE
    mov  ah, ATTR_ATLAS
    mov  cx, CELLS
fill:
    mov  [es:di], ax
    add  di, 2
    dec  cx
    jnz  fill

    ; ---- 16x16 code-page block: cell (r,c) <- glyph code r*16+c
    xor  bx, bx
atlas:
    mov  ax, bx
    shr  ax, 4                ; row
    mov  cl, COLS*2
    mul  cl                   ; AX = row byte offset into the frame
    mov  si, ax
    mov  al, bl
    and  al, 0x0F             ; column
    shl  al, 1
    xor  ah, ah
    add  si, ax
    mov  al, bl               ; the glyph code itself
    mov  ah, ATTR_ATLAS
    mov  [es:si], ax
    inc  bx
    cmp  bx, ATLAS_SIDE*ATLAS_SIDE
    jb   atlas

    ; ---- the same message twice, in two different colours
    mov  si, MSG_ROW*COLS*2
    mov  bx, msg
    mov  ah, ATTR_MSG
    call putline
    mov  si, MSG2_ROW*COLS*2
    mov  bx, msg
    mov  ah, ATTR_MSG2
    call putline

hang:
    hlt
    jmp  hang

; bx = NUL-terminated string, si = byte offset into es, ah = attribute
putline:
    mov  al, [bx]
    test al, al
    jz   .done
    mov  [es:si], ax
    add  si, 2
    inc  bx
    jmp  putline
.done:
    ret

msg: db 'BM801-RECEIPT-OK>0123456789ABCDEF', 0

times 510-($-$$) db 0
db 0x55, 0xAA

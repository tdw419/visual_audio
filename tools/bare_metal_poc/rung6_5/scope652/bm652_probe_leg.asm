; BM652 costing probe -- Rung 6.5 option C, section by section, in bytes.
;
; Nothing here boots. The file exists so that `bm652_scope.py` can read its
; sections out of nasm's own list file and the scoping note can cost the leg
; instead of estimating it -- the same method BM650 used for rung 6.5 option A
; (`scope/probe_exec_leg.asm`, which predicted 279 B against the 230 B the
; landed row measured).
;
; What option C has to pay for that option A did not: the PXC2-E walk runs in
; flat-32 (int 13h cannot reach past 1 MiB, and the payload is 13.6 MB), so by
; the time the image's bytes are in memory the loader is NOT in the mode the
; image expects. The leg therefore has three parts, and they are marked as
; three parts:
;
;   pmode_to_real   leave protected mode after the gate has passed
;   real_exec_leg   BM651's exec leg with the copy-down deleted: the walk
;                   already stored the decoded bytes AT their destination, so
;                   there is nothing to move and nothing to bounce over
;   back_to_pmode   return to 32-bit and pick the handoff up where it stopped
;
; The image is the SAME 2,048 bytes BM651 executes (`bm651_img2.asm`, green
; variant): entered at IMG2_SEG:0 with DS=ES=IMG2_SEG, SS:SP=0:7C00, IF=0,
; ES:SI at a 14-byte contract block, and it returns with `retf`. Keeping the
; image untouched is the point -- the claim is about where its bytes came from.

BITS 32
ORG 0

COM1        equ 0x3F8
IMG2_SEG    equ 0x5000             ; linear 0x50000: the image group's own dst
IMG2_LEN    equ 2048               ; unchanged from BM651
GROUP_BYTES equ 16384              ; one PXC2-E group == one sub-image slot
EXEC_ARGS   equ GROUP_BYTES - 16   ; the LAST 16 B of the group's window
STACK_TOP   equ 0x1f784
GDT_LIMIT   equ gdt_end - gdt - 1
GDT_ADDR    equ gdt
; stand-ins for what the consts emitter would hand the real build: a 16-bit
; fold of the image's own CRC32, and the medium LBA the image's first plane
; chunk came from (PX_BASE_LBA + group*PX_CHUNK_SECTORS).
EXPECTED_EXEC_NID equ 0xEE1B
IMG2_LBA_VALUE    equ 17 + 829 * 8

; the contract block, byte-for-byte BM651's layout (bm651_stage2.asm:45-52)
ARG_LEN  equ 0
ARG_LBA  equ 2
ARG_COM  equ 4
ARG_CS   equ 6
ARG_NID  equ 8
ARG_MBOX equ 10
ARG_ECHO equ 12
EXEC_MAILBOX equ 0x4B4F

; ---- where the 32-bit loader's own text leaves off: this probe starts after
; ---- `GATE2=PASS`, with ECX/EDI free and the gate's receipts already printed.
pmode_to_real:
    ; One 16-bit-offset far jump into selector 0x08, the 16-bit code descriptor
    ; rung9's GDT already carries and nothing in either loader has ever used:
    ; `dq 0x00009A000000FFFF`. Hand-encoded because nasm emits the offset field
    ; 32 bits wide for `jmp 0x08:label` under BITS 32, and a 66 prefix on top of
    ; that encoding would leave three bytes of the operand for the CPU to fall
    ; through -- so the operand size is fixed at the byte level, not the form.
    db 0x66, 0xEA
    dw .rm_entry
    dw 0x0008
.rm_entry:
    BITS 16
    mov eax, cr0                   ; 66 0F 20 C0: nasm prefixes it for the size
    and eax, 0xFFFFFFFE            ; clear PE. No paging was ever enabled, so
    mov cr0, eax                   ; there is nothing to tear down first.
    jmp 0x0000:.real               ; EA with 16-bit operands: base-0 CS
.real:
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax                     ; the 32-bit stack at 0x1f784 is above the
    mov sp, 0x7C00                 ; 64 KiB a 16-bit SS can address: re-aim it.
    cli                            ; R-SCOPE-3, and the image's own entry table
    xor ax, ax
    mov gs, ax                     ; the handoff never used GS; zero it so the
    mov fs, ax                     ; re-entry cannot inherit a stale selector
    mov word [ss_saved], sp

    ; ---- the leg proper ----------------------------------------------------
real_exec_leg:
    mov ax, IMG2_SEG
    mov ds, ax
    mov es, ax
    mov word [es:EXEC_ARGS + ARG_LEN], IMG2_LEN
    mov word [es:EXEC_ARGS + ARG_LBA], IMG2_LBA_VALUE
    mov word [es:EXEC_ARGS + ARG_COM], COM1
    mov word [es:EXEC_ARGS + ARG_CS], IMG2_SEG
    mov word [es:EXEC_ARGS + ARG_NID], EXPECTED_EXEC_NID
    mov word [es:EXEC_ARGS + ARG_MBOX], 0
    mov word [es:EXEC_ARGS + ARG_ECHO], 0
    mov si, EXEC_ARGS              ; the image finds its args in ES:SI
    call IMG2_SEG:0                ; 9A: pushes CS:IP, which is what its retf
.back:                             ; pops (R-SCOPE-6)
    mov ax, [es:EXEC_ARGS + ARG_MBOX]
    mov dx, [es:EXEC_ARGS + ARG_ECHO]
    mov [execcbline], ax
    mov [execnidline], dx
    cmp ax, EXEC_MAILBOX
    jne .badmbx
    cmp dx, EXPECTED_EXEC_NID
    jne .nobanner
    mov si, msg_execok
    call puts16
    jmp .done                      ; refusals are fall-through neighbours
.badmbx:
    mov si, msg_badmbx
    call puts16
    mov ax, [execcbline]
    call puthex4_16
    mov si, msg_exp
    call puts16
    mov ax, EXEC_MAILBOX
    call puthex4_16
    jmp .done
.nobanner:
    mov si, msg_nobanner
    call puts16
    mov ax, [execnidline]
    call puthex4_16
    mov si, msg_exp
    call puts16
    mov ax, EXPECTED_EXEC_NID
    call puthex4_16
.done:
    mov si, msg_crlf
    call puts16

    ; ---- and back. The image has owned the machine for the length of the
    ; ---- leg: it may have moved DS/ES/SS, cleared A20, or reloaded the GDT
    ; ---- register, so the re-entry re-establishes all four rather than
    ; ---- assuming it left them alone. That is the new risk option C takes on,
    ; ---- and the byte cost below is the honest price of it.
back_to_pmode:
    cli
    lgdt [gdt_ptr]
    in al, 0x92
    or al, 2
    out 0x92, al                   ; A20 again: the walk wrote above 1 MiB and
                                   ; the handoff will too
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    jmp dword 0x10:.pm
.pm:
    BITS 32
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov esp, STACK_TOP
    push dword 0x46
    popfd                          ; back to the handoff's frozen eflags
    jmp handoff_continues          ; the cmdline / zero-page build, unchanged

    BITS 16
; ---- the two helpers this base does not already have in 16-bit form: rung6's
; ---- stage2 keeps puts16/putc16 for the ENTER line and puthex8_32 for the
; ---- gate line. A receipt that names a 16-bit NID in real mode needs its own.
helpers16:
puts16:
    lodsb
    test al, al
    jz .pdone
    call putc16
    jmp puts16
.pdone:
    ret

putc16:
    push ax
    push dx
    mov ah, al
.pw:
    mov dx, COM1 + 5
    in al, dx
    test al, 0x20
    jz .pw
    mov al, ah
    mov dx, COM1
    out dx, al
    pop dx
    pop ax
    ret

puthex4_16:
    push ax
    push cx
    mov ch, 4
.rot:
    rol ax, 4
    push ax
    and al, 0x0F
    cmp al, 10
    jb .dig
    add al, 'A' - 10 - '0'
.dig:
    add al, '0'
    call putc16
    pop ax
    dec ch
    jnz .rot
    pop cx
    pop ax
    ret

strings_here:
msg_execok   db 'BM652-S2 EXEC=OK', 13, 10, 0
msg_badmbx   db 'BM652-S2 EXEC=BAD-MAILBOX ', 0
msg_nobanner db 'BM652-S2 EXEC=NO-BANNER ', 0
msg_exp      db ' EXP=', 0
msg_crlf     db 13, 10, 0

    align 4
data_here:
gdt_ptr:
    dw GDT_LIMIT
    dd GDT_ADDR
gdt:
    dq 0x0000000000000000
    dq 0x00009A000000FFFF
    dq 0x00CF9A000000FFFF
    dq 0x00CF92000000FFFF
gdt_end:
execcbline:  dw 0
execnidline: dw 0
ss_saved:    dw 0

; the handoff text this leg hands back to. Not costed here -- it is rung6's
; landed code, byte-identical to what BM602 gated; the label exists so the
; probe's own control flow closes and nasm has nothing to warn about.
handoff_continues:
    ret

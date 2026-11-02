; BM903 step 2 stage2: the SAME handoff constructor, fed by the PXC1 pixel
; medium. This file is a byte-copy of bm903_stage2.asm (step 1, committed and
; never edited in place) with exactly four deltas, all of them about where the
; payload bytes come from:
;
;   1. the real-mode int 13h header read is gone -- the header band now
;      arrives as sub-image 0 of the pixel walk, so HDR_SCRATCH is filled by
;      the same code path that fills the kernel and the initrd;
;   2. the two contiguous load_region calls are replaced by px_walk: per
;      16 KiB group it issues four 8-sector ATA reads (one per plane),
;      de-interleaves them into the destination sub-image, and accumulates a
;      table CRC32 over the DECODED bytes in decoded order;
;   3. a CRC32 gate v2 sits between the walk and the handoff (rung-4
;      discipline verbatim: compute first, then print, and refuse with
;      `CRC=<computed> EXP=<expected>`);
;   4. nothing else moved -- the zero page, the cmdline, the register state
;      and the jump are the step-1 text, so the differ's L1/L2/L3 legs mean
;      "the pixel medium carried the payload", not "a different loader was
;      written".
;
; Step 1's design notes still hold and are repeated only where relevant:
;   * ATA PIO instead of int 13h above 1 MiB (the DAP segment field is 16
;     bits); in flat mode the drive is read directly, per-sector DRQ.
;   * GDT = protocol selector layout (cs 0x10, ds/es/ss 0x18).
;   * cr0=0x11, eflags=0x46, rsp=0x1f784 landed explicitly.
BITS 16
ORG 0x8000                       ; linear == offset (loaded at 0x0800:0), and
                                 ; stays inside the 16-bit offset range so the
                                 ; same labels work in real and flat-32 mode.

COM1 equ 0x3F8
%include "bm903_layout.inc"
%include "bm903_px_layout.inc"

STACK_TOP equ 0x1f784
HEAP_END  equ 0xefff
TYPE_LOADER equ 0xff
KERNEL_ENTRY equ 0x100000

; CRC8: one byte into the running reflected CRC32 (poly 0xEDB88320, the SAME
; table the host codec uses, so "gate agrees" is one implementation not two).
; Byte in AL, accumulator in ESI; EAX/EDX are scratch.
%macro CRC8 0
    movzx edx, al
    xor edx, esi
    and edx, 0xFF
    shr esi, 8
    mov eax, [crc32_tab + edx*4]
    xor esi, eax
%endmacro

start16:
    cli
    xor ax, ax
    mov ds, ax                   ; cs=ds=es=0 with ORG 0x8000: real-mode linear
    mov es, ax                   ; == flat-32 linear, so one label serves both
    mov ss, ax
    mov sp, 0x7C00               ; the MBR's own bytes are dead by now
    cld

    mov si, msg_enter
    call puts16

    ; ---- no int 13h here: on the pixel medium every payload byte, including
    ; ---- the kernel header band, arrives through the flat-mode px_walk. ----
    lgdt [gdt_ptr]
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    jmp 0x10:pmode

rdfail16:
    mov si, msg_rdfail
    call puts16
.hang16:
    cli
    hlt
    jmp .hang16

; ---- 16-bit helpers live in their own BITS island: under
; ---- BITS 32 nasm encodes lodsb against ESI, not SI.
puts16:
    lodsb
    test al, al
    jz .p16done
    call putc16
    jmp puts16
.p16done:
    ret

putc16:
    push ax
    push dx
    mov ah, al
.p16w:
    mov dx, COM1+5
    in al, dx
    test al, 0x20
    jz .p16w
    mov al, ah
    mov dx, COM1
    out dx, al
    pop dx
    pop ax
    ret

BITS 32
pmode:
    mov ax, 0x18
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov esp, STACK_TOP

    mov edi, msg_pmode
    call puts32

    ; ---- A20: prove line 20 is live before writing anything above 1 MiB ----
    mov dword [0x100000], 0x11111111
    mov dword [0x200000], 0x22222222
    mov eax, [0x100000]
    cmp eax, 0x11111111
    je a20_ok
    in al, 0x92
    or al, 2
    out 0x92, al                 ; fast A20 via port 0x92
    mov dword [0x100000], 0x11111111
    mov dword [0x200000], 0x22222222
    mov eax, [0x100000]
    cmp eax, 0x11111111
    jne fail_a20
a20_ok:
    mov edi, msg_a20
    call puts32

    ; ---- PXC1 walk: PX_GROUPS groups of (4 plane reads -> de-interleave ->
    ; ---- CRC32 over the decoded bytes). Destinations come from the sub-image
    ; ---- table, so the kernel lands at 0x100000 and the initrd at
    ; ---- INITRD_ADDR exactly as in step 1. ----
    call px_walk
    mov edi, msg_kload             ; the walk completed; now the gate decides
    call puts32

    ; ---- CRC32 gate v2, rung-4 discipline verbatim: the walk above has ALREADY
    ; ---- computed the whole value, so nothing is printed until every decoded
    ; ---- byte is accounted for (rung-4's DEFECT-R4PRINT: never print a
    ; ---- computed-then-changed number). Then printed computed-then-expected,
    ; ---- and only then decided. This is the ONLY path to the handoff: a
    ; ---- mismatch refuses and hangs, so the kernel is never entered with a
    ; ---- corrupted payload. ----
    mov edi, msg_crc
    call puts32
    mov eax, [px_crc]
    call puthex8_32
    mov edi, msg_exp
    call puts32
    mov eax, EXPECTED_CRC
    call puthex8_32
    mov edi, msg_crlf
    call puts32
    mov edi, [px_crc]
    cmp edi, EXPECTED_CRC
    jne px_refuse
    mov edi, msg_crcpass
    call puts32

    ; ---- cmdline buffer: zero the whole 512 B, then the pinned bytes ----
    mov edi, CMDLINE_ADDR
    xor eax, eax
    mov ecx, CMDLINE_BYTES
    rep stosb
    mov esi, cmdline_img
    mov edi, CMDLINE_ADDR
    mov ecx, CMDLINE_BYTES
    rep movsb

    ; ---- zero page at ZP_ADDR (rsi for the kernel) ----
    mov edi, ZP_ADDR
    xor eax, eax
    mov ecx, 4096
    rep stosb
    ; kernel-baked band comes from the LOADED image, not from a host copy
    mov esi, HDR_SCRATCH + 0x1f1
    mov edi, ZP_ADDR + 0x1f1
    mov ecx, 0x268 - 0x1f1
    rep movsb
    mov eax, [ZP_ADDR + 0x202]
    cmp eax, 0x53726448          ; 'HdrS'
    jne fail_hdrs
    ; loader-set fields (BM902 contract; initrd pair is the step-1 addendum)
    mov word [ZP_ADDR + 0x1f2], 0            ; root_flags
    mov dword [ZP_ADDR + 0x1f8], 0           ; ram_size
    mov word [ZP_ADDR + 0x1fa], 0xffff       ; vid_mode
    mov word [ZP_ADDR + 0x1fc], 0            ; root_dev
    mov word [ZP_ADDR + 0x1fe], 0xaa55       ; boot_flag (frozen)
    mov byte [ZP_ADDR + 0x210], TYPE_LOADER  ; type_of_loader (0x33 is ours-not)
    mov byte [ZP_ADDR + 0x211], 0x81         ; loadflags LOADED_HIGH|CAN_USE_HEAP
    mov word [ZP_ADDR + 0x212], 0            ; setup_move_size
    mov dword [ZP_ADDR + 0x214], KERNEL_ENTRY ; code32_start (frozen)
    mov dword [ZP_ADDR + 0x218], INITRD_ADDR ; ramdisk_image   <-- constructed
    mov dword [ZP_ADDR + 0x21c], INITRD_BYTES; ramdisk_size    <-- constructed
    mov word [ZP_ADDR + 0x224], HEAP_END     ; heap_end_ptr
    mov dword [ZP_ADDR + 0x228], CMDLINE_ADDR; cmd_line_ptr
    mov byte [ZP_ADDR + 0x1e8], 7            ; e820_entries (frozen MUST-MATCH)
    mov esi, e820_img
    mov edi, ZP_ADDR + 0x2d0
    mov ecx, 140
    rep movsb
    mov edi, msg_handoff
    call puts32

    ; ---- pinned register state, then the jump ----
    xor ebx, ebx
    xor ecx, ecx
    xor edx, edx
    xor edi, edi
    xor ebp, ebp
    mov eax, KERNEL_ENTRY
    ; rax=0x100000, rbx..rbp, rdi = 0, rsi = zero page
    mov ecx, 0                   ; rcx again (last clobber wins)
    mov edx, 0
    mov esi, ZP_ADDR
    mov edi, 0
    mov ebp, 0
    mov ebx, 0
    push 0x46
    popfd                        ; IF clear, bits 1|2|6 -> reads back 0x46
    ; retf pops both dwords, so rsp at the handoff IS this value: the last
    ; stack mutation before the jump lands it on the oracle's 0x1f784 exactly.
    mov esp, STACK_TOP
    push dword 0x10
    push dword KERNEL_ENTRY
    retf

; ================= helpers =================
; px_walk: the PXC1 medium reader. For each of PX_GROUPS 16 KiB groups it
;   1. issues one 8-sector ATA read per plane into PB0..PB3 (plane p of group g
;      starts at LBA PX_BASE_LBA + g*PX_CHUNK_SECTORS + p*PX_PLANE_SECTORS --
;      rung-4's four-consecutive-planes layout, same arithmetic, 13x longer);
;   2. de-interleaves 4096 quads: decoded byte 4j+p = PBp[j];
;   3. CRC32s each decoded byte in decoded order as it is stored.
; The destination is per-group (px_dst), so sub-images land at their real load
; addresses and no bank ever has to fit under 1 MiB. Leaves the finished CRC in
; [px_crc].
px_walk:
    push ebx
    push esi
    push edi
    push ebp
    mov dword [px_crc], 0xFFFFFFFF
    mov dword [px_group], 0
.pw_group:
    mov eax, [px_group]
    cmp eax, PX_GROUPS
    jae .pw_done
    mov dword [px_plane], 0
.pw_plane:
    ; esi = this plane-chunk's start LBA: BASE + group*CHUNK + plane*PLANE
    mov ebx, [px_plane]
    mov eax, ebx
    imul eax, eax, PX_PLANE_SECTORS
    mov ecx, [px_group]
    imul ecx, ecx, PX_CHUNK_SECTORS
    add eax, ecx
    add eax, PX_BASE_LBA
    mov esi, eax
    ; edi = PBp
    mov edi, PB0
    mov eax, ebx
    shl eax, 12
    add edi, eax
    mov ebx, PX_CHUNK_SECTORS       ; ata_read keeps esi/edi/ebx, eats the rest
    call ata_read
    mov eax, [px_plane]
    inc eax
    mov dword [px_plane], eax
    cmp eax, 4
    jb .pw_plane

    ; ---- decode this group: EAX=dst, ESI = CRC, EBP = dst, ECX = j ----
    call px_dst                     ; reads [px_group]; clobbers ecx,edx only
    mov ebp, eax
    mov esi, [px_crc]
    xor ecx, ecx
.pw_byte:
    mov al, [PB0 + ecx]
    mov [ebp + ecx*4 + 0], al
    CRC8
    mov al, [PB1 + ecx]
    mov [ebp + ecx*4 + 1], al
    CRC8
    mov al, [PB2 + ecx]
    mov [ebp + ecx*4 + 2], al
    CRC8
    mov al, [PB3 + ecx]
    mov [ebp + ecx*4 + 3], al
    CRC8
    inc ecx
    cmp ecx, PX_GROUP_BYTES/4
    jb .pw_byte
    mov [px_crc], esi
    inc dword [px_group]
    jmp .pw_group
.pw_done:
    mov eax, [px_crc]
    not eax
    mov dword [px_crc], eax
    pop ebp
    pop esi
    pop edi
    pop ebx
    ret

; px_dst: EAX-free entry; reads [px_group], returns the linear destination for
; that group in EAX (PX_SINK for the bank-padding groups, whose bytes still
; count toward the CRC -- the gate covers the whole payload, not just what we
; keep).
px_dst:
    mov eax, [px_group]
    mov ecx, px_sub_table
    mov edx, PX_SUBIMAGE_COUNT
.pd_loop:
    cmp eax, [ecx]
    jb .pd_sink
    cmp eax, [ecx + 4]
    jb .pd_hit
    add ecx, 12
    dec edx
    jnz .pd_loop
.pd_sink:
    mov eax, PX_SINK
    ret
.pd_hit:
    sub eax, [ecx]
    imul eax, eax, PX_GROUP_BYTES
    add eax, [ecx + 8]
    ret

; ata_read: esi = LBA, ebx = sector count (<=128), edi = dst; clobbers eax,cx,dx,ebp
ata_read:
    push edx
    push edi                     ; rep insw advances DI: the caller's pointer
    call ata_wait_ready          ; stays valid only if we restore it here
    mov dx, 0x1F1
    xor al, al
    out dx, al
    mov dx, 0x1F2
    mov al, bl
    out dx, al
    mov dx, 0x1F3
    mov eax, esi
    out dx, al
    mov dx, 0x1F4
    mov eax, esi
    shr eax, 8
    out dx, al
    mov dx, 0x1F5
    mov eax, esi
    shr eax, 16
    out dx, al
    mov dx, 0x1F6
    mov eax, esi
    shr eax, 24                  ; esi must survive: load_region advances by it
    and eax, 0x0F
    or eax, 0xE0                 ; LBA-bit mode, drive 0
    out dx, al
    call ata_delay
    mov dx, 0x1F7
    mov al, 0x20                 ; READ SECTORS (LBA28)
    out dx, al
    call ata_wait_drq
    ; One `rep insw` across a whole multi-sector command reads garbage: an ATA
    ; device deasserts DRQ after each 512-byte sector and must be waited for
    ; again (MEASURED here — the first sector of every chunk survived, the rest
    ; of the payload read back as zero). So: handshake, 256 words, repeat.
    mov ebp, ebx                 ; ebp = sectors left in this command
.sector:
    mov dx, 0x1F0
    mov ecx, 256
    rep insw
    dec ebp
    jz .transferred
    call ata_wait_drq
    jmp .sector
.transferred:
    pop edi
    pop edx
    ret

ata_wait_ready:
    mov edx, 0x1F7               ; DX-form: 0x1F7 overflows an 8-bit port imm
    mov ecx, 0x00400000
.wr:
    in al, dx
    test al, 0x80
    jz .rdy
    loop .wr
    jmp fail_ata_to
.rdy:
    ret

ata_wait_drq:
    mov edx, 0x1F7
    mov ecx, 0x02000000
.wd:
    in al, dx
    test al, 0x01
    jnz fail_ata_err
    test al, 0x80
    jnz .wd2
    test al, 0x08
    jz fail_ata_err
    ret
.wd2:
    loop .wd
    jmp fail_ata_to

ata_delay:
    push eax
    push edx
    mov edx, 0x3F6               ; alternate status: 4 reads == ~1 us settle
    in al, dx
    in al, dx
    in al, dx
    in al, dx
    pop edx
    pop eax
    ret

fail_ata_err:
    mov edi, msg_ataerr
    call puts32
    movzx eax, al                ; the failing status byte, widened for the print
    call puthex8_32
    jmp hang32
fail_ata_to:
    mov edi, msg_atatimeout
    call puts32
    jmp hang32
fail_a20:
    mov edi, msg_a20fail
    call puts32
    jmp hang32
fail_hdrs:
    mov edi, msg_hdrfail
    call puts32
    jmp hang32

; px_refuse: the gate's only alternative exit. The computed and expected CRCs
; are already on the serial line above, so this adds the verdict and stops --
; deliberately NOT jumping to the kernel.
px_refuse:
    mov edi, msg_crcfail
    call puts32
    jmp hang32
hang32:
    cli
    hlt
    jmp hang32

; puts32: EDI = NUL-terminated string
puts32:
    push eax
    push esi
    mov esi, edi
.ps:
    lodsb
    test al, al
    jz .pd
    call putc32
    jmp .ps
.pd:
    pop esi
    pop eax
    ret

putc32:
    push eax
    push edx
    mov ah, al
.pcw:
    mov dx, COM1+5
    in al, dx
    test al, 0x20
    jz .pcw
    mov al, ah
    mov dx, COM1
    out dx, al
    pop edx
    pop eax
    ret

puthex8_32:
    ; EAX = value, printed as 8 hex digits MSB-first. The step-1 original
    ; rotated AL, which could only ever show one byte -- gate v2 prints a
    ; 32-bit CRC, so the shift is 64-bit-clean 32-bit arithmetic here.
    push eax
    push ebx
    push ecx
    push edx
    mov ebx, eax
    mov ecx, 28
.pr:
    mov edx, ebx
    shr edx, cl
    and dl, 0x0F
    cmp dl, 10
    jb .dig
    add dl, 'A' - 10 - '0'
.dig:
    add dl, '0'
    mov al, dl
    call putc32                  ; putc32 preserves eax/ebx/ecx
    sub ecx, 4
    jns .pr
    pop edx
    pop ecx
    pop ebx
    pop eax
    ret

; ================= data =================
msg_enter    db 'BM903-S2 ENTER', 13, 10, 0
msg_rdfail   db 'BM903-S2 RDFAIL', 13, 10, 0
msg_pmode    db 'BM903-S2 PMODE', 13, 10, 0
msg_a20      db 'BM903-S2 A20 OK', 13, 10, 0
msg_a20fail  db 'BM903-S2 A20 FAIL', 13, 10, 0
msg_kload    db 'BM903-S2 PIXEL WALK DONE', 13, 10, 0
msg_handoff  db 'BM903-S2 HANDOFF BUILT', 13, 10, 0
msg_hdrfail  db 'BM903-S2 HDRS CHECK FAIL', 13, 10, 0
msg_ataerr   db 'BM903-S2 ATA ERR status=', 0
msg_atatimeout db 'BM903-S2 ATA TIMEOUT', 13, 10, 0
; gate v2 lines: `GATE2 CRC=<computed> EXP=<expected>` is printed BEFORE the
; comparison verdict, so the numbers on the wire cannot be a post-hoc echo of
; the constant baked into the image.
msg_crc      db 'BM903-S2 GATE2 CRC=', 0
msg_exp      db ' EXP=', 0
msg_crlf     db 13, 10, 0
msg_crcpass  db 'BM903-S2 GATE2=PASS', 13, 10, 0
msg_crcfail  db 'BM903-S2 GATE2=FAIL -- NO HANDOFF JUMP', 13, 10, 0

align 4
px_group:   dd 0
px_plane:   dd 0
px_crc:     dd 0

; (start group, end group, destination) for each payload sub-image, ascending.
align 4
px_sub_table:
    dd SUB0_GROUP, SUB0_GROUP + SUB0_NGROUPS, SUB0_DEST
    dd SUB1_GROUP, SUB1_GROUP + SUB1_NGROUPS, SUB1_DEST
    dd SUB2_GROUP, SUB2_GROUP + SUB2_NGROUPS, SUB2_DEST

align 8
gdt_ptr:
    dw gdt_end - gdt - 1
    dd gdt
align 8
gdt:
    dq 0x0000000000000000        ; 0x00 null
    dq 0x00009A000000FFFF        ; 0x08 unused 16-bit code
    dq 0x00CF9A000000FFFF        ; 0x10 code32  <- kernel cs
    dq 0x00CF92000000FFFF        ; 0x18 data32  <- kernel ds/es/ss
gdt_end:

cmdline_img:
%include "bm903_cmdline.inc"
e820_img:
%include "bm903_e820.inc"
align 16
crc32_tab:
%include "bm903_crc32tab.inc"

    times 512*STAGE2_SECTORS-($-$$) db 0

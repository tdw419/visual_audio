; BM903 step 1 stage2: EXECUTED construction of the BM902 protected-mode
; handoff. Where bm902_stage2_construct.py built the zero page + cmdline as
; host-side bytes, this file builds the identical artifact from inside the
; guest, in real code: load the kernel header band, switch to 32-bit flat
; mode, pull kernel + initrd off the raw IDE medium with ATA PIO, compose the
; zero page and cmdline, then jump to 0x100000 with the pinned register state.
;
; Design notes (measured, not assumed):
;   * ATA PIO instead of int 13h above 1 MiB: the DAP segment field is 16
;     bits, so BIOS disk reads cannot land at 0x100000+ / 0x10000000 without a
;     bounce buffer; in flat mode the drive can be read directly.
;   * The GDT uses the protocol's own selector layout (index 2 = code32 ->
;     0x10, index 3 = data32 -> 0x18) so the cs/ss the kernel sees match the
;     frozen oracle selectors without a fake transition.
;   * cr0 = 0x11 (PE|ET, PG clear) and eflags = 0x46 are landed explicitly,
;     and rsp = 0x1f784 is set by the last mov before the far return, so the
;     pushes themselves cannot move the value the kernel observes.
;   * The cmdline is the oracle string byte-exact (BM902's RECORDED CHOICE),
;     carried as a pinned 512-byte blob and copied at run time.
BITS 16
ORG 0x8000                       ; linear == offset (loaded at 0x0800:0), and
                                 ; stays inside the 16-bit offset range so the
                                 ; same labels work in real and flat-32 mode.

COM1 equ 0x3F8
%include "bm903_layout.inc"

STACK_TOP equ 0x1f784
HEAP_END  equ 0xefff
TYPE_LOADER equ 0xff
KERNEL_ENTRY equ 0x100000

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

    ; ---- kernel header band: 2 sectors at KERNEL_LBA -> 0x20000 (linear) ----
    mov word [dap_count], 2
    mov dword [dap_lba], KERNEL_LBA
    mov dword [dap_lba+4], 0
    mov si, dap
    mov dl, 0x80
    mov ah, 0x42
    int 0x13
    jc rdfail16
    mov si, msg_hdr
    call puts16

    ; ---- GDT + PE ----
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

    ; ---- kernel payload: PAYLOAD_SECTORS from PAYLOAD_LBA -> 0x100000 ----
    mov esi, PAYLOAD_LBA
    mov edx, PAYLOAD_SECTORS
    mov edi, KERNEL_ENTRY
    call load_region
    mov edi, msg_kload
    call puts32

    ; ---- initrd: INITRD_SECTORS from INITRD_LBA -> INITRD_ADDR ----
    mov esi, INITRD_LBA
    mov edx, INITRD_SECTORS
    mov edi, INITRD_ADDR
    call load_region
    mov edi, msg_iload
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
; load_region: esi = start LBA, edx = sector count, edi = dst linear
load_region:
    push ebx
    push esi
    push edi
.lr_loop:
    test edx, edx
    jz .lr_done
    mov ebx, 128
    cmp edx, ebx
    jae .lr_go
    mov ebx, edx
.lr_go:
    call ata_read
    add esi, ebx
    imul eax, ebx, 512
    add edi, eax
    sub edx, ebx
    jmp .lr_loop
.lr_done:
    pop edi
    pop esi
    pop ebx
    ret

; ata_read: esi = LBA, ebx = sector count (<=128), edi = dst; clobbers eax,cx,dx
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
    call puthex8_32              ; prints AL as the failing status
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
    push eax
    push ecx
    push edx
    mov ecx, 8
.pr:
    rol al, 4
    mov edx, eax
    and dl, 0x0F
    cmp dl, 10
    jb .dig
    add dl, 'A' - 10 - '0'
.dig:
    add dl, '0'
    push eax
    mov al, dl
    call putc32
    pop eax
    dec ecx
    jnz .pr
    pop edx
    pop ecx
    pop eax
    ret

; ================= data =================
msg_enter    db 'BM903-S2 ENTER', 13, 10, 0
msg_hdr      db 'BM903-S2 HDR BAND READ', 13, 10, 0
msg_rdfail   db 'BM903-S2 RDFAIL', 13, 10, 0
msg_pmode    db 'BM903-S2 PMODE', 13, 10, 0
msg_a20      db 'BM903-S2 A20 OK', 13, 10, 0
msg_a20fail  db 'BM903-S2 A20 FAIL', 13, 10, 0
msg_kload    db 'BM903-S2 KERNEL LOADED', 13, 10, 0
msg_iload    db 'BM903-S2 INITRD LOADED', 13, 10, 0
msg_handoff  db 'BM903-S2 HANDOFF BUILT', 13, 10, 0
msg_hdrfail  db 'BM903-S2 HDRS CHECK FAIL', 13, 10, 0
msg_ataerr   db 'BM903-S2 ATA ERR status=', 0
msg_atatimeout db 'BM903-S2 ATA TIMEOUT', 13, 10, 0

align 4
dap:
    db 0x10, 0
dap_count:
    dw 2
    dw 0x0000
    dw HDR_SCRATCH/16
dap_lba:
    dq 0

align 4
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

    times 512*STAGE2_SECTORS-($-$$) db 0

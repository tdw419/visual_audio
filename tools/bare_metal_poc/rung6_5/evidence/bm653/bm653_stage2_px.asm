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
%include "bm653_px_layout.inc"

STACK_TOP equ 0x1f784
; ---- BM602 additions. Everything outside a block named in
; bm602_construct.py's delta list is byte-identical to
; rung9/bm903_stage2_px.asm, which is what the L1/L4 identity legs read.
MBR_ADDR equ 0x7C00                  ; the BIOS copy of stage1 is still there
BEE_WORDS equ PX_GROUP_BYTES/4       ; codewords per group == in-plane offsets
; ---- BM653 (option C). Everything outside a block named in
; bm653_construct.py's delta list is byte-identical to
; rung6/bm602_stage2_px.asm, the text BM602 gated 15/0 x2.
IMG2_SEG   equ IMG2_DST/16           ; the image group lands where the
                                     ; sub-image table says; this is the
                                     ; same linear address as a paragraph
EXEC_MAILBOX equ 0x4B4F              ; "I finished", in the image's words
ARG_LEN  equ 0                       ; the 14-byte block, byte-for-byte
ARG_LBA  equ 2                       ; BM651's contract: bm651_img2.asm
ARG_COM  equ 4                       ; parses the SAME offsets out of its
ARG_CS   equ 6                       ; own text and refuses the build if
ARG_NID  equ 8                       ; the two disagree (bm653_img2.py).
ARG_MBOX equ 10
ARG_ECHO equ 12
EXEC_ARGS equ PX_GROUP_BYTES - 16    ; R-SCOPE-7: the TOP of the group
                                     ; window, above any image the group
                                     ; can hold -- and written after the
                                     ; walk finished summing the CRC, so
                                     ; it cannot move a gate value.
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

; puthex4_16 -- AX as four hex digits, MSB first. The 32-bit twin
; puthex8_32 cannot be reused: it is BITS 32 arithmetic, and the EXEC
; verdicts are printed in real mode, where the image's NID is a 16-bit
; word. Same digit table logic, 16-bit operands.
puthex4_16:
    push ax
    push cx
    mov ch, 4
.ph4:
    rol ax, 4
    push ax
    and al, 0x0F
    cmp al, 10
    jb .hdig
    add al, 'A' - 10 - '0'
.hdig:
    add al, '0'
    call putc16
    pop ax
    dec ch
    jnz .ph4
    pop cx
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
    ; ---- BM602: this loader reads a PXC2-E medium (PX_PLANES planes). The
    ; ---- tag is read out of the stage1 bytes the BIOS left at 0x7C00, i.e.
    ; ---- out of the MEDIUM, so reusing an old 4-plane medium is refused by
    ; ---- name here rather than as an unexplained CRC mismatch one walk later.
    mov eax, [MBR_ADDR + PX_TAG_OFF]
    cmp eax, PX_CONTAINER
    jne fail_container
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
    ; ---- BM602 non-vacuity anchor. Printed after the whole walk (nothing
    ; here can still change: DEFECT-R4PRINT) and BEFORE the CRC verdict, so a
    ; run that "passed" by correcting nothing cannot be read as a recovery.
    ; ECC=0 PAR=0 on a KNOWN-CORRUPT medium is a FAIL leg. ----
    mov edi, msg_ecc
    call puts32
    mov eax, [bee_fixed]
    call puthex8_32
    mov edi, msg_par
    call puts32
    mov eax, [bee_parity_faults]
    call puthex8_32
    mov edi, msg_crlf
    call puts32
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

    ; =============== BM-653: exec-from-repaired-pixels (option C) ==========
    ; The gate above has PASSed, so every decoded byte of the group this
    ; medium was built from is the payload the host replay predicted --
    ; including the ones pass 1 had to fix. BM602 stopped there and built a
    ; handoff. The claim one rung further: the bytes the loader REPAIRED are
    ; now the bytes that RUN.
    ;
    ; Ordering, and it is load-bearing three times over:
    ;   * strictly after `GATE2=PASS`. A refused medium never reaches the
    ;     instruction pointer -- and the two-symbol and blind-spot fixtures
    ;     PROVE that by printing no EXEC= line, rather than trusting this
    ;     comment to say the order was kept.
    ;   * strictly before the zero-page build, so the handoff this row
    ;     captures is built AFTER the image has had its chance at the machine.
    ;     The scribbler leg depends on that order and on nothing else: an
    ;     image that keeps its side of the contract can still poison the
    ;     kernel's hardware, and the dumps say so.
    ;   * and there is NO copy-down. rung 5's leg bounced its bytes from a
    ;     second window to the first because the loader had put them there;
    ;     here px_walk already stored the decoded group AT its destination, so
    ;     the move is deleted rather than shrunk (BM652 §6 costed the leg on
    ;     exactly that deletion).
    ;
    ; What option A never had to pay for: the walk runs flat-32, because int
    ; 13h cannot reach past 1 MiB and the payload is 13.6 MB. So by the time
    ; the image's bytes are in memory, the loader is NOT in the mode they were
    ; written for. Three parts, and the third is the one that matters:
    ;   1. leave protected mode through the 16-bit code descriptor rung9's GDT
    ;      has carried, unused, since BM903;
    ;   2. hand over exactly as BM651 does -- args in ES:SI, far CALL so the
    ;      image's retf has somewhere to come back to (R-SCOPE-6);
    ;   3. re-enter defensively: the image owned the machine in between and
    ;      may have reloaded the GDT register, cleared A20, moved the segments
    ;      or left flags behind. R-SCOPE-8: that is the byte cost of this
    ;      option, and it is not negotiable -- the alternative is a kernel
    ;      entered with the image's leftovers.
    ;
    ; One 16-bit-offset far jump into selector 0x08 (`dq 0x00009A000000FFFF`,
    ; limit 0xFFFF -- which is also why the landing label must stay below
    ; 0x10000; BM652 §5 measured 24,576 B of headroom). Hand-encoded because
    ; nasm emits the operand of `jmp 0x08:label` 32 bits wide under BITS 32,
    ; and a 66 prefix on top of THAT leaves three bytes of operand for the CPU
    ; to fall through: the operand size is fixed at the byte level.
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
    cli                            ; R-SCOPE-3: the image owns no IDT
    mov gs, ax                     ; discipline, and a timer tick landing
    mov fs, ax                     ; inside it would be blamed on the claim
                                   ; under test. Zero both so the re-entry
                                   ; cannot inherit a stale selector.
    mov ax, IMG2_SEG
    mov ds, ax
    mov es, ax
    mov word [es:EXEC_ARGS + ARG_LEN], IMG2_LEN
    mov word [es:EXEC_ARGS + ARG_LBA], IMG2_LBA
    mov word [es:EXEC_ARGS + ARG_COM], COM1
    mov word [es:EXEC_ARGS + ARG_CS], IMG2_SEG
    mov word [es:EXEC_ARGS + ARG_NID], EXPECTED_EXEC_NID
    mov word [es:EXEC_ARGS + ARG_MBOX], 0
    mov word [es:EXEC_ARGS + ARG_ECHO], 0
    mov si, EXEC_ARGS              ; the image finds its args in ES:SI
    call IMG2_SEG:0                ; 9A: pushes 0:.back, which is what the
                                   ; image's retf pops
.back:
    ; ONE store per witness, both paths read it back (DEFECT-R5WITNESS). The
    ; args are read through ES while it still names the image's paragraph; DS
    ; goes back to the loader's real-mode base BEFORE the stores, because the
    ; witness words are loader data and ORG 0x8000 makes their address equal
    ; their linear address only while DS is 0.
    mov ax, [es:EXEC_ARGS + ARG_MBOX]
    mov dx, [es:EXEC_ARGS + ARG_ECHO]
    mov bx, 0
    mov ds, bx
    mov [execcbline], ax
    mov [execnidline], dx
    cmp ax, EXEC_MAILBOX
    jne .exec_badmbx               ; did it finish, per the contract?
    cmp dx, EXPECTED_EXEC_NID
    jne .exec_nobanner             ; did it run, and run as THIS image?
    mov si, msg_execok
    call puts16
    jmp .exec_done                 ; the refusals below are fall-through
                                   ; neighbours, so green needs its own exit
.exec_badmbx:
    mov si, msg_badmbx             ; computed first, then expected:
    call puts16                    ; rung-4 DEFECT-R4PRINT
    mov ax, [execcbline]
    call puthex4_16
    mov si, msg_exp
    call puts16
    mov ax, EXEC_MAILBOX
    call puthex4_16
    jmp .exec_done
.exec_nobanner:
    mov si, msg_nobanner
    call puts16
    mov ax, [execnidline]
    call puthex4_16
    mov si, msg_exp
    call puts16
    mov ax, EXPECTED_EXEC_NID
    call puthex4_16
.exec_done:
    mov si, msg_crlf
    call puts16

    cli
    lgdt [gdt_ptr]                 ; all four, not the one the image happened
    in al, 0x92                    ; to leave alone: the walk wrote above
    or al, 2                       ; 1 MiB and the handoff will too, so A20
    out 0x92, al                   ; is re-asserted rather than assumed
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
    ; edi = this plane's buffer. NOT PB0 + p*0x1000 past p=3: 0x34000 is
    ; PX_SINK, so the parity planes live above it, at PP1/PP2/PP4, and the
    ; mapping is a table the host proof reads too rather than arithmetic the
    ; reader has to re-derive.
    mov edi, [px_pb + ebx*4]
    mov ebx, PX_CHUNK_SECTORS       ; ata_read keeps esi/edi/ebx, eats the rest
    call ata_read
    mov eax, [px_plane]
    inc eax
    mov dword [px_plane], eax
    cmp eax, PX_PLANES
    jb .pw_plane

    ; ---- BM602 PASS 1: repair the plane chunks in place. The decode and
    ; CRC loop below is then untouched, so the gate checksums corrected bytes
    ; in decoded order exactly as BM903 does. ----
    call bee_correct
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

; bee_correct -- BM602 pass 1 over one group's seven 4096-byte plane
; buffers. Hamming(7,4) over BYTE symbols, so the codeword is (PB0[x],PB1[x],
; PB2[x],PB3[x]) with parity planes p1=d0^d1^d3, p2=d0^d2^d3, p4=d1^d2^d3, and
; the three syndromes are bytes. Linear over GF(2): no multiply, no table, no
; solver. The nonzero pattern names the symbol and the syndrome VALUE is the
; fault, so fixing is one XOR. Clobbers eax,ebx,ecx,edx only (the walk holds
; the group counter in memory and re-derives everything else).
;
; There is deliberately no "uncorrectable" branch: with a 3-bit pattern over a
; byte symbol, two faults still name some symbol and get confidently mis-fixed.
; That is BM601 scoping leg G, and the CRC32 gate downstream is what catches
; it. The corrector never sits in front of the gate.
bee_correct:
    xor  ecx, ecx
.bee_loop:
    mov  al, [PP1 + ecx]
    xor  al, [PB0 + ecx]
    xor  al, [PB1 + ecx]
    xor  al, [PB3 + ecx]             ; al = s1
    mov  ah, [PP2 + ecx]
    xor  ah, [PB0 + ecx]
    xor  ah, [PB2 + ecx]
    xor  ah, [PB3 + ecx]             ; ah = s2
    mov  bl, [PP4 + ecx]
    xor  bl, [PB1 + ecx]
    xor  bl, [PB2 + ecx]
    xor  bl, [PB3 + ecx]             ; bl = s4
    mov  bh, ah
    or   bh, bl
    cmp  al, 0
    jne  .bee_synd
    test bh, bh
    jne  .bee_synd
.bee_next:
    inc  ecx
    cmp  ecx, BEE_WORDS
    jb   .bee_loop
    ret

.bee_synd:
    ; pattern (s1,s2,s4) -> symbol: 011 d0, 101 d1, 110 d2, 111 d3 (data, fix
    ; with the covering syndrome); 001/010/100 are a parity plane (the payload
    ; is untouched, counted separately); anything else is two faults and is
    ; mis-fixed by design.
    cmp  al, 0
    je   .bee_s1zero
    cmp  ah, 0
    jne  .bee_s12
    cmp  bl, 0
    je   .bee_parity                 ; s1 alone
    jmp  .bee_d1                     ; s1, s4
.bee_s12:
    cmp  bl, 0
    je   .bee_d0                     ; s1, s2
    jmp  .bee_d3                     ; s1, s2, s4
.bee_s1zero:
    cmp  ah, 0
    je   .bee_parity                 ; s4 alone (or nothing)
    cmp  bl, 0
    jne  .bee_d2                     ; s2, s4 -> fix with s2
.bee_parity:                         ; s2 alone
    inc  dword [bee_parity_faults]
    jmp  .bee_next
.bee_d0:
    mov  dl, [PB0 + ecx]
    xor  dl, al
    mov  [PB0 + ecx], dl
    inc  dword [bee_fixed]
    jmp  .bee_next
.bee_d1:
    mov  dl, [PB1 + ecx]
    xor  dl, al
    mov  [PB1 + ecx], dl
    inc  dword [bee_fixed]
    jmp  .bee_next
.bee_d2:
    mov  dl, [PB2 + ecx]
    xor  dl, ah
    mov  [PB2 + ecx], dl
    inc  dword [bee_fixed]
    jmp  .bee_next
.bee_d3:
    mov  dl, [PB3 + ecx]
    xor  dl, al
    mov  [PB3 + ecx], dl
    inc  dword [bee_fixed]
    jmp  .bee_next

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
fail_container:
    ; computed-then-compared, same discipline as the CRC line: name what the
    ; medium says before the verdict, so a refusal can be read off serial.
    mov edi, msg_contain
    call puts32
    mov eax, [MBR_ADDR + PX_TAG_OFF]
    call puthex8_32
    mov edi, msg_exp
    call puts32
    mov eax, PX_CONTAINER
    call puthex8_32
    mov edi, msg_crlf
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
; BM602 lines. The ENTER/verdict strings keep the BM903-S2 prefix on purpose:
; a leg that differs from the proven loader only in these lines still shares
; every stage of BM903's stage ladder, which is what the classifier reads.
msg_ecc      db 'BM903-S2 ECC=', 0
msg_par      db ' PAR=', 0
msg_contain  db 'BM903-S2 CONTAINER=', 0
; BM653 lines. Same prefix rule BM602 stated: the only thing that
; differs from the gated loader is the text AFTER 'BM903-S2 ', so a
; leg still reads as the same stage ladder.
msg_execok   db 'BM903-S2 EXEC=OK', 13, 10, 0
msg_badmbx   db 'BM903-S2 EXEC=BAD-MAILBOX ', 0
msg_nobanner db 'BM903-S2 EXEC=NO-BANNER ', 0

align 4
px_group:   dd 0
px_plane:   dd 0
px_crc:     dd 0
; plane p of the group in flight lands where this table says. The host proof
; (bm602_mkimg.py) reads THESE SEVEN DEFINES out of this file, so a buffer
; that moved here and not there is caught before anything boots.
px_pb:      dd PB0, PB1, PB2, PB3, PP1, PP2, PP4
bee_fixed:           dd 0     ; data symbols repaired this boot
bee_parity_faults:   dd 0     ; parity-plane-only faults: inert for the payload
execcbline:          dw 0     ; BM653: mailbox word the image left
execnidline:         dw 0     ; BM653: NID word the image echoed

; (start group, end group, destination) for each payload sub-image, ascending.
align 4
px_sub_table:
    dd SUB0_GROUP, SUB0_GROUP + SUB0_NGROUPS, SUB0_DEST
    dd SUB1_GROUP, SUB1_GROUP + SUB1_NGROUPS, SUB1_DEST
    dd SUB2_GROUP, SUB2_GROUP + SUB2_NGROUPS, SUB2_DEST
    dd SUB3_GROUP, SUB3_GROUP + SUB3_NGROUPS, SUB3_DEST

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

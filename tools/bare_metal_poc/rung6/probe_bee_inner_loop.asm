; BM601 scoping probe -- CODE-SIZE ONLY.
;
; One question, answered by assembling real code rather than guessing: how many
; bytes of 16-bit loader does a corruption-tolerant corrector cost, against the
; measured stage2 budget? See BM601_ECC_SCOPING.md for the numbers this feeds.
;
; It is NOT wired into anything: no loader %includes this file, no medium is
; built from it, and it has never executed. Its algebra is validated
; independently (and exhaustively) by probe_bee_scheme.py on the real BM903
; payload; this file exists so the scoping note can say "N bytes" instead of
; "probably a few hundred". Equivalence between the two files is by
; construction -- same syndrome formulas, same four fix cases -- and the
; executed-code proof belongs to the implementation row, not to this one.
;
; Structure follows rung9/bm903_stage2_px.asm's px_walk. The corrector runs as
; a PASS 1 over the already-read plane chunks, patching bytes in place, and the
; existing de-interleave+CRC loop (.pw_byte) is then left byte-for-byte alone.
; That ordering is the design's load-bearing property: BM903's L1/L4 identity
; legs keep meaning "the same loader text, a different medium", and the CRC32
; gate still runs over decoded, corrected, decoded-order bytes -- so a
; mis-correction (2+ faults in one codeword) is still caught by the gate that
; is already proven to refuse.
;
; Geometry, measured from rung9/bm903_pxcodec.py: payload byte i lives at
; medium byte BASE_LBA*512 + (i%4)*PLANE_BYTES + i//4. So the four data symbols
; of one codeword are exactly the four PXC1 planes at the SAME in-plane offset
; -- the existing interleave already spreads every codeword across four
; independent read streams, and a one-plane media fault (a bad sector, a bad
; chunk) therefore lands at most ONE symbol per codeword. Hamming(7,4) over
; byte symbols corrects exactly that.
;
; Hamming(7,4), data at symbol positions 3/5/6/7, parity at 1/2/4:
;   p1 = d0 ^ d1 ^ d3      p2 = d0 ^ d2 ^ d3      p4 = d1 ^ d2 ^ d3
;   s1 = p1 ^ (d0^d1^d3), s2 = p2 ^ (d0^d2^d3), s4 = p4 ^ (d1^d2^d3)
;   (s1,s2,s4) nonzero pattern -> faulty symbol; the fix value is any nonzero
;   syndrome that covers it (s1 for d0/d1/d3, s2 for d2).
; Linear over GF(2): no GF(256) multiply, no log/antilog table, no syndrome
; solver. The only table-free correction code that fits here.

BITS 16
ORG 0x8000                       ; same bias as bm903_stage2_px.asm

PB0    equ 0x30000               ; the four plane chunks (bm903_px_layout.inc)
PB1    equ 0x31000
PB2    equ 0x32000
PB3    equ 0x33000
PP1    equ 0x38000               ; parity chunks: above the sink
PP2    equ 0x39000               ; (PX_SINK 0x34000 + one 16 KiB group
PP4    equ 0x3A000               ;  = 0x38000) -- free in the BM903 map
WORDS  equ 4096                  ; PX_GROUP_BYTES/4

bee_start:
; ---------------------------------------------------------------------------
; bee_correct -- patch one 4096-word chunk (4 data planes + 3 parity planes)
; in place. Clobbers eax, ebx, ecx, edx; updates the two report counters.
; ---------------------------------------------------------------------------
bee_correct:
    xor  ecx, ecx
.bee_loop:
    ; ---- syndromes: al = s1, ah = s2, bl = s4
    mov  al, [PP1 + ecx]
    xor  al, [PB0 + ecx]
    xor  al, [PB1 + ecx]
    xor  al, [PB3 + ecx]
    mov  ah, [PP2 + ecx]
    xor  ah, [PB0 + ecx]
    xor  ah, [PB2 + ecx]
    xor  ah, [PB3 + ecx]
    mov  bl, [PP4 + ecx]
    xor  bl, [PB1 + ecx]
    xor  bl, [PB2 + ecx]
    xor  bl, [PB3 + ecx]

    ; ---- fast path: clean codeword. Two-byte OR keeps ah's zero-ness out of
    ; the flags we are about to read, so s1 is tested by its own cmp.
    mov  bh, ah
    or   bh, bl
    cmp  al, 0
    jne  .bee_synd
    test bh, bh
    jne  .bee_synd
.bee_next:
    inc  ecx
    cmp  ecx, WORDS
    jb   .bee_loop
    ret

.bee_synd:
    ; ---- dispatch on the nonzero/zero pattern of (s1, s2, s4). Two nonzero
    ; syndromes => a data symbol; exactly one => a parity chunk (inert for the
    ; payload, counted); three => d3.
    cmp  al, 0
    je   .bee_s1zero
    cmp  ah, 0
    jne  .bee_s12
    cmp  bl, 0
    je   .bee_parity                 ; s1 only  -> parity chunk 1
    jmp  .bee_d1                     ; s1, s4   -> d1 ^= s1
.bee_s12:
    cmp  bl, 0
    je   .bee_d0                     ; s1, s2   -> d0 ^= s1
    jmp  .bee_d3                     ; s1, s2, s4 -> d3 ^= s1
.bee_s1zero:
    cmp  ah, 0
    je   .bee_parity                 ; s4 alone (or nothing) -> parity chunk 4
    cmp  bl, 0
    jne  .bee_d2                     ; s2, s4   -> d2 ^= s2
.bee_parity:                         ; s2 alone -> parity chunk 2
    inc  dword [bee_parity_faults]
    jmp  .bee_next

    ; ---- four data-symbol fixes. Each is load / xor / store back into the
    ; plane buffer, so the untouched .pw_byte loop reads the corrected byte.
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

bee_end:
    dw   bee_end - bee_start         ; trailer: the measured size, in bytes
bee_fixed:           dd 0            ; corrected data symbols this boot
bee_parity_faults:   dd 0            ; parity-only faults (inert, counted)

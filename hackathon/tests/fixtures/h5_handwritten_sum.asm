# sum 1..10 -> r10 (a0) -- hand-written, convention-clean
LDI r10 0        # accumulator
LDI r8 1         # i
LDI r9 11        # one past n: loop until i == 11
:cond
CMP r8 r9
JZ :done         # flag-based: JZ jumps when the CMP equality flag r0 is set
ADD r10 r8
LDI r7 1
ADD r8 r7
JMP :cond
:done
HALT

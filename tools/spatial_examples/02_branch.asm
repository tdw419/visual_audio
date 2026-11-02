# Conditional branching demonstration with CMP, JZ, and JMP
LDI r1 10
LDI r2 10
CMP r1 r2
JZ 0,1
LDI r3 0
LDI r4 20
SUB r4 r3
JMP 3,1
LDI r3 1
LDI r4 10
ADD r4 r3
PRT r3
HALT

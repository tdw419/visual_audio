# Subroutine calls with CALL, RET, PUSH, and POP across spatial rows
LDI r1 0
LDI r2 1
CALL 0,2
PUSH r1
LDI r3 10
LDI r4 20
ADD r3 r4
POP r1
CALL 0,2
PUSH r1
LDI r3 30
LDI r4 40
ADD r3 r4
POP r1
PRT r1
HALT
ADD r1 r2
PUSH r2
LDI r5 0
POP r2
RET

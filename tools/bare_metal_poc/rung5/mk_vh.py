src = open("stage2.asm").read()
block = """    ; ---- COM1: 115200 8N1 (stage1 already programmed it, but a bare
    ; stage2 run must stand alone; re-init is idempotent) ----
    mov dx, COM1+1
    xor al, al
    out dx, al
    mov dx, COM1+3
    mov al, 0x80
    out dx, al
    mov dx, COM1
    mov al, 0x01
    out dx, al
    mov dx, COM1+1
    xor al, al
    out dx, al
    mov dx, COM1+3
    mov al, 0x03
    out dx, al

"""
assert block in src, "COM1 block not found"
v = src.replace(block, "", 1)
open("vh.asm", "w").write(v)
print("vh written")

with open("/tmp/qemu_serial.log", "r") as f:
    log = f.read()
if "Unpacking initramfs..." in log and "QEMU HARDDISK" in log:
    print("SUCCESS")

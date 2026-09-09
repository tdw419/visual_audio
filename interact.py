import pexpect
import sys

with open('/tmp/qemu_interactive.log', 'w') as log_file:
    print("Starting QEMU...")
    cmd = (
        "qemu-system-x86_64 -m 1G -enable-kvm -cpu host -display none "
        "-d int,cpu_reset -D /tmp/qemu_int.log "
        "-drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd "
        "-drive if=pflash,format=raw,file=/tmp/my_vars.fd "
        "-drive id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none "
        "-device ide-hd,drive=bootdisk,bootindex=1 "
        "-drive id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none "
        "-device virtio-blk-pci,drive=rootdisk,bootindex=2 "
        "-serial stdio"
    )

    class LogWrapper:
        def write(self, s):
            sys.stdout.write(s)
            sys.stdout.flush()
            log_file.write(s)
            log_file.flush()
        def flush(self):
            sys.stdout.flush()
            log_file.flush()

    child = pexpect.spawn(cmd, encoding='utf-8', timeout=240, logfile=LogWrapper())

    try:
        print("\n[+] Waiting for bootloader...")
        child.expect("Linux boot protocol support")

        print("\n[+] Waiting for login prompt...")
        child.expect("ubuntu login:")
        child.sendline("root")

        print("\n[+] Waiting for password prompt...")
        child.expect("Password:")
        child.sendline("israel")

        print("\n[+] Waiting for shell...")
        child.expect(r"root@ubuntu:~#")
        
        commands = [
            "uname -a",
            "cat /etc/os-release",
            "ls /",
            "systemctl is-system-running"
        ]
        
        for c in commands:
            print(f"\n[+] Executing: {c}")
            child.sendline(c)
            child.expect(r"root@ubuntu:~#")
        
        print("\n[+] Done executing commands. Shutting down...")
        child.sendline("poweroff")
        child.expect(pexpect.EOF, timeout=60)
        print("\n[+] Clean exit.")
    except Exception as e:
        print(f"\n[-] Error: {e}")
        child.terminate(force=True)

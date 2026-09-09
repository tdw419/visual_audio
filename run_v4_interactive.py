#!/usr/bin/env python3

import subprocess
import time
import os
import signal
import sys

# Create named pipes for serial I/O
pipe_in = "/tmp/qemu_serial_in"
pipe_out = "/tmp/qemu_serial_out"

# Clean up old pipes
for p in [pipe_in, pipe_out]:
    if os.path.exists(p):
        os.remove(p)

os.mkfifo(pipe_in)
os.mkfifo(pipe_out)

# Start QEMU with serial to named pipe
qemu = subprocess.Popen([
    "qemu-system-x86_64",
    "-m", "1G",
    "-enable-kvm",
    "-cpu", "host",
    "-display", "none",
    "-d", "int,cpu_reset",
    "-D", "/tmp/qemu_int.log",
    "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd",
    "-drive", "if=pflash,format=raw,file=/tmp/my_vars.fd",
    "-drive", "id=bootdisk,format=raw,file=/tmp/ubuntu_v4_efi.img,if=none",
    "-device", "ide-hd,drive=bootdisk,bootindex=1",
    "-drive", "id=rootdisk,file=ubuntu-24.04-server-cloudimg-amd64.raw,format=raw,if=none",
    "-device", "virtio-blk-pci,drive=rootdisk,bootindex=2",
    "-serial", f"pipe:{pipe_in}"
], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# Open pipes for reading/writing (non-blocking)
out_fd = os.open(pipe_in, os.O_RDONLY | os.O_NONBLOCK)
in_fd = os.open(pipe_out, os.O_WRONLY)

serial_output = []

# Wait for boot to reach login prompt
print("Waiting for login prompt...")
start_time = time.time()
while time.time() - start_time < 30:
    try:
        data = os.read(out_fd, 1024).decode('utf-8', errors='ignore')
        serial_output.append(data)
        print(data, end='', flush=True)

        if "ubuntu login:" in data:
            break
    except BlockingIOError:
        time.sleep(0.1)
else:
    print("\nTimeout waiting for login prompt")
    qemu.send_signal(signal.SIGKILL)
    sys.exit(1)

# Send login
print("\nSending login...")
os.write(in_fd, b"root\n")
time.sleep(1)

# Wait for password prompt
password_seen = False
for _ in range(50):
    try:
        data = os.read(out_fd, 1024).decode('utf-8', errors='ignore')
        serial_output.append(data)
        print(data, end='', flush=True)

        if "Password:" in data:
            password_seen = True
            break
    except BlockingIOError:
        time.sleep(0.1)

if password_seen:
    # Send password
    print("Sending password...")
    os.write(in_fd, b"israel\n")
else:
    print("\nPassword prompt not seen")
    qemu.send_signal(signal.SIGKILL)
    sys.exit(1)

# Wait for shell prompt
print("Waiting for shell prompt...")
start_time = time.time()
while time.time() - start_time < 10:
    try:
        data = os.read(out_fd, 1024).decode('utf-8', errors='ignore')
        serial_output.append(data)
        print(data, end='', flush=True)

        if "root@" in data and "~#" in data:
            break
    except BlockingIOError:
        time.sleep(0.1)

# Run verification commands
commands = [
    "uname -a",
    "cat /etc/os-release",
    "ls /",
    "systemctl is-system-running",
    "poweroff"
]

for cmd in commands:
    print(f"\nRunning: {cmd}")
    os.write(in_fd, f"{cmd}\n".encode())
    time.sleep(2)

    # Read output
    for _ in range(50):
        try:
            data = os.read(out_fd, 1024).decode('utf-8', errors='ignore')
            serial_output.append(data)
            print(data, end='', flush=True)

            if "~#" in data:
                break
        except BlockingIOError:
            time.sleep(0.05)

# Wait for QEMU to exit
print("\nWaiting for QEMU to exit...")
qemu.wait(timeout=30)

# Clean up
os.close(out_fd)
os.close(in_fd)
os.remove(pipe_in)
os.remove(pipe_out)

# Save full log
full_log = ''.join(serial_output)
with open('/tmp/qemu_serial_interactive.log', 'w') as f:
    f.write(full_log)

print("\n=== Verification complete ===")
print("Full log saved to /tmp/qemu_serial_interactive.log")
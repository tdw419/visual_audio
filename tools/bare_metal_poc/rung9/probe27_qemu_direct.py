"""probe27: QEMU-direct reference leg for the BM901 oracle gate (redB).

Boots the SAME bzImage via QEMU's own loader (-kernel, type_of_loader=0xff
path) and captures boot_params at the PM entry (rsi=&boot_params by boot
protocol; hw bp at code32_start). Its zeropage DIFFERS from the real-chain
capture in loader-owned fields — the differ uses that as the non-vacuity
redB leg (schema is kernel/loader-specific, not a self-satisfied constant).
"""
import json
import signal
import socket
import struct
import subprocess
import sys
import time


def find_free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def csum(body):
    return f'${body}#{sum(body.encode()) & 0xFF:02x}'


class Stub:
    def __init__(self, port):
        self.s = socket.create_connection(('127.0.0.1', port), timeout=15)
        self.s.settimeout(15)

    def cmd(self, body):
        self.s.sendall(csum(body).encode())
        buf = b''
        while True:
            try:
                chunk = self.s.recv(65536)
            except socket.timeout:
                return None
            if not chunk:
                return None
            buf += chunk
            stripped = buf.lstrip(b'+-')
            if stripped.startswith(b'$'):
                end = stripped.find(b'#')
                if end >= 0 and len(stripped) >= end + 3:
                    self.s.sendall(b'+')
                    return stripped[1:end].decode()

    def read_mem(self, addr, size):
        out = bytearray()
        CH = 0x1000
        while size > 0:
            n = min(CH, size)
            r = self.cmd(f'm{addr:x},{n:x}')
            if not r or r.startswith('E'):
                out += b'\0' * n
            else:
                out += bytes.fromhex(r)
            addr += n
            size -= n
        return bytes(out)


NAMES = ['rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
         'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15']

captured = 0
for leg in range(2):
    port = find_free_port()
    qemu = subprocess.Popen([
        'qemu-system-x86_64', '-M', 'pc', '-m', '512',
        '-kernel', 'vmlinuz64.extracted',
        '-append', 'console=ttyS0',
        '-display', 'none', '-no-reboot', '-m', '512',
        '-S', '-gdb', f'tcp::{port}',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    stub = Stub(port)
    stub.cmd('qSupported')
    ok = stub.cmd('Z1,100000,1')
    assert ok == 'OK', f'hw bp failed: {ok}'
    stub.s.sendall(csum('c').encode())
    stop = None
    buf = b''
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            chunk = stub.s.recv(65536)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        stripped = buf.lstrip(b'+-')
        if stripped.startswith(b'$'):
            end = stripped.find(b'#')
            if end >= 0 and len(stripped) >= end + 3:
                stop = stripped[1:end].decode()
                break
    print(f'leg {leg} stop:', stop)
    if not stop or not stop.startswith(('T', 'S', 'X')):
        stub.cmd('D')
        stub.s.close()
        qemu.send_signal(signal.SIGTERM)
        qemu.wait(timeout=10)
        continue
    regs_hex = stub.cmd('g')
    raw = bytes.fromhex(regs_hex[:17 * 16])
    vals = dict(zip(NAMES, struct.unpack('<16Q', raw[:128])))
    rip = struct.unpack_from('<Q', raw, 128)[0]
    rsi = vals['rsi']
    hdr = stub.read_mem(rsi + 0x202, 4)
    print(f'  rip={rip:#x} rsi={rsi:#x} HdrS@rsi={hdr!r}')
    if hdr == b'HdrS':
        zp = stub.read_mem(rsi, 0x1000)
        cmd_ptr = struct.unpack_from('<I', zp, 0x228)[0]
        cmdline = stub.read_mem(cmd_ptr, 0x400).split(b'\0', 1)[0]
        with open(f'qemu_leg{leg}_zp.bin', 'wb') as f:
            f.write(zp)
        with open(f'qemu_leg{leg}_cmdline.txt', 'wb') as f:
            f.write(cmdline)
        with open(f'qemu_leg{leg}_regs.json', 'w') as f:
            json.dump({'rip': rip, **vals}, f, indent=1)
        ver = struct.unpack_from('<H', zp, 0x206)[0]
        print(f'  CAPTURED: zp@{rsi:#x} ver={ver >> 8}.{ver & 0xff} '
              f'cmd={cmdline.decode(errors="replace")}')
        captured += 1
    stub.cmd('D')
    stub.s.close()
    qemu.send_signal(signal.SIGTERM)
    qemu.wait(timeout=10)

print('done', captured, 'legs captured')
sys.exit(0 if captured >= 1 else 1)

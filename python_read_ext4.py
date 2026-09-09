import socket
import struct

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('127.0.0.1', 10809))
    
    # Handshake
    s.recv(18)
    s.send(struct.pack('>I', 1))
    s.send(struct.pack('>QII', 0x49484156454F5054, 7, 10))
    s.send(struct.pack('>I', 6))
    s.send(b'rootfs')
    
    # skip info
    rep_len = struct.unpack('>I', s.recv(16)[12:16])[0]
    s.recv(rep_len)
    
    # next is NBD_REP_ACK
    rep_len = struct.unpack('>I', s.recv(16)[12:16])[0]
    
    # Read ext4 superblock of /dev/vda4
    # vda4 starts at sector 2097280.
    # Ext4 superblock is at offset 1024 into the partition.
    # So we need to read Sector (2097280 + 2) = 2097282.
    offset = 2097282 * 512
    s.send(struct.pack('>IHHQQI', 0x25609513, 0, 0, 1, offset, 512))
    
    res = s.recv(16)
    data = b""
    while len(data) < 512:
        packet = s.recv(512 - len(data))
        if not packet: break
        data += packet
        
    magic = struct.unpack('<H', data[56:58])[0]
    print(f"Ext4 Magic: 0x{magic:04x}")
    if magic == 0xef53:
        print("Superblock is valid!")
    else:
        print("Superblock is INVALID!")

main()

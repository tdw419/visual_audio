#!/bin/bash
set -e

# Build the apkovl directory structure
mkdir -p tmp_apkovl/etc/local.d tmp_apkovl/etc/network tmp_apkovl/etc/runlevels/boot tmp_apkovl/etc/runlevels/default tmp_apkovl/usr/bin

# 1. Create a minimal web handler script
cat << 'EOF' > tmp_apkovl/usr/bin/web_handler
#!/bin/sh
echo -e "HTTP/1.1 200 OK\r\n\r\nHello from Alpine Audio Boot!"
EOF
chmod +x tmp_apkovl/usr/bin/web_handler

# 2. Start netcat as a web server on boot
cat << 'EOF' > tmp_apkovl/etc/local.d/network.start
#!/bin/sh
nc -lk -p 80 -e /usr/bin/web_handler &
exit 0
EOF
chmod +x tmp_apkovl/etc/local.d/network.start

# 3. Configure a static IP (DHCP fails without the af_packet module)
cat << 'EOF' > tmp_apkovl/etc/network/interfaces
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 10.0.2.15
    netmask 255.255.255.0
    gateway 10.0.2.2
EOF

# 4. Enable networking and local services
ln -s /etc/init.d/networking tmp_apkovl/etc/runlevels/boot/networking
ln -s /etc/init.d/local tmp_apkovl/etc/runlevels/default/local

# 5. Package as an Alpine apkovl tarball
tar -czf alpine.apkovl.tar.gz -C tmp_apkovl etc/ usr/

# 6. Create a 2MB FAT disk image and inject the apkovl
dd if=/dev/zero of=alpine_networking.img bs=1M count=2
mkfs.vfat alpine_networking.img
mcopy -i alpine_networking.img alpine.apkovl.tar.gz ::/

# Cleanup
rm -rf tmp_apkovl alpine.apkovl.tar.gz
echo "Successfully built alpine_networking.img!"

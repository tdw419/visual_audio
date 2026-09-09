#!/bin/bash
export DEBIAN_FRONTEND=noninteractive
echo '#!/bin/sh' > /usr/sbin/policy-rc.d
echo 'exit 101' >> /usr/sbin/policy-rc.d
chmod +x /usr/sbin/policy-rc.d
while ! ip route show | grep -q default; do sleep 1; done
apt-get update
apt-get install -y ubuntu-desktop-minimal qemu-system-x86 qemu-utils bridge-utils curl libvulkan1 openssh-server
apt-get clean
rm -f /usr/sbin/policy-rc.d
poweroff

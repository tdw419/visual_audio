#!/bin/bash
virt-customize -a ubuntu-desktop-15g.raw \
    --network \
    --run-command 'mkdir -p /run/systemd/resolve && echo "nameserver 10.0.2.3" > /run/systemd/resolve/stub-resolv.conf && rm -f /etc/resolv.conf && ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf' \
    --run-command 'ip addr' \
    --run-command 'ip route' \
    --run-command 'ping -c 1 91.189.91.83' \
    --run-command 'ping -c 1 archive.ubuntu.com'

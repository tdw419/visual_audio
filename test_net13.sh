#!/bin/bash
virt-customize -a test-cloudimg.raw \
    --network \
    --run-command 'mkdir -p /run/systemd/resolve && echo "nameserver 10.0.2.3" > /run/systemd/resolve/stub-resolv.conf && rm -f /etc/resolv.conf && ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf' \
    --run-command 'apt-get update || true' \
    --run-command 'ip addr > /ip.txt' \
    --run-command 'cat /ip.txt; false'

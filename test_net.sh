#!/bin/bash
virt-customize -a ubuntu-desktop-15g.raw \
    --network \
    --run-command 'ip addr' \
    --run-command 'ip route' \
    --run-command 'ping -c 1 91.189.91.83' \
    --run-command 'ping -c 1 archive.ubuntu.com' \
    --run-command 'curl -I http://91.189.91.83/ubuntu/'

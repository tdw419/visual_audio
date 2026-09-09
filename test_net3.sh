#!/bin/bash
virt-customize -a ubuntu-desktop-15g.raw \
    --network \
    --run-command 'ip link set eth0 up && dhclient eth0' \
    --run-command 'ip addr' \
    --run-command 'ip route' \
    --run-command 'ping -c 1 91.189.91.83'

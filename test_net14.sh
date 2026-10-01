#!/bin/bash
virt-customize -a test-cloudimg.raw \
    --network \
    --run-command 'ip link set eth0 up && ip addr add 10.0.2.15/24 dev eth0 && ip route add default via 10.0.2.2' \
    --run-command 'ping -c 1 91.189.91.83'

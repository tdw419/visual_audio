#!/bin/bash
virt-customize -a test-cloudimg.raw \
    --network \
    --run-command 'for i in {1..10}; do ip addr show eth0 | grep -q UP && break || sleep 1; done' \
    --run-command 'ip route show' \
    --run-command 'ping -c 1 91.189.91.83'

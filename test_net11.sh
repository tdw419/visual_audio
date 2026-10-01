#!/bin/bash
virt-customize -a test-cloudimg.raw \
    --network \
    --run-command 'for i in $(seq 1 15); do ip addr show eth0 | grep -q UP && break; sleep 1; done' \
    --run-command 'ip addr show eth0 > /eth0.txt 2>&1' \
    --run-command 'ping -c 1 91.189.91.83 > /ping.txt 2>&1' \
    --run-command 'cat /eth0.txt; cat /ping.txt; false'

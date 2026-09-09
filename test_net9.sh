#!/bin/bash
virt-customize -v -x -a test-cloudimg.raw \
    --network \
    --run-command 'ping -c 1 archive.ubuntu.com > /ping1.txt 2>&1' \
    --run-command 'ping -c 1 91.189.91.83 > /ping2.txt 2>&1' \
    --run-command 'ip route > /route.txt 2>&1' \
    --run-command 'cat /ping1.txt; cat /ping2.txt; cat /route.txt; false'

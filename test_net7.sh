#!/bin/bash
virt-customize -v -x -a test-cloudimg.raw \
    --network \
    --run-command 'ip addr && ip route && false'

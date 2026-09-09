#!/bin/bash
virt-customize -a test-cloudimg.raw \
    --network \
    --run-command 'ip addr' \
    --run-command 'ip route'

#!/bin/bash
virt-customize -a test-cloudimg.raw \
    --memsize 4096 \
    --network \
    --run-command 'ping -c 1 91.189.91.83'

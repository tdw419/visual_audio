#!/bin/bash
virt-customize -a test-cloudimg.raw \
    --network \
    --run-command 'ping -c 1 archive.ubuntu.com || true' \
    --run-command 'ping -c 1 91.189.91.83 || true' \
    --run-command 'ip route || true'

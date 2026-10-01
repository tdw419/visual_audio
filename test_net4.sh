#!/bin/bash
virt-customize -a ubuntu-24.04-server-cloudimg-amd64.raw \
    --network \
    --run-command 'ip addr' \
    --run-command 'ip route' \
    --run-command 'ping -c 1 91.189.91.83'

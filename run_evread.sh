#!/bin/bash
# run_evread.sh — scp evread.py to guest, run as root for N seconds.
set -e
SECS="${1:-8}"
timeout 20 sshpass -p israel scp -P 2222 -o StrictHostKeyChecking=no /home/jericho/projects/zion/projects/visual_audio/evread.py jericho@127.0.0.1:/tmp/evread.py
timeout 40 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 "echo israel | sudo -S python3 /tmp/evread.py $SECS /dev/input/event2 /dev/input/event3" 2>&1

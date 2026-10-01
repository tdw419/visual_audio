#!/bin/bash
# run_watch_input.sh — run the guest-side input watcher (project-established
# sudo pattern, same as deploy_interactive.sh: password passed inside the SSH
# command per the VM's known credentials in this repo).
set -e
timeout 25 sshpass -p israel ssh -p 2222 -o StrictHostKeyChecking=no jericho@127.0.0.1 'echo israel | sudo -S bash /tmp/watch_input.sh 8' 2>&1

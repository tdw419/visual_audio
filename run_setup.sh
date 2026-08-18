#!/bin/bash
echo "Waiting for guest SSH to start..."
for i in {1..120}; do
    # Try running a dummy command. If sshpass succeeds, the guest is up.
    if sshpass -p geometry ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 -p 2222 geometry@127.0.0.1 "echo SSH is up" 2>/dev/null; then
        break
    fi
    sleep 2
done

echo "VM is up. Copying setup_overlay.sh..."
sshpass -p geometry scp -o StrictHostKeyChecking=no -P 2222 setup_overlay.sh geometry@127.0.0.1:/home/geometry/

echo "Running setup_overlay.sh inside VM..."
sshpass -p geometry ssh -o StrictHostKeyChecking=no -p 2222 geometry@127.0.0.1 "echo geometry | sudo -S bash -c 'echo yes | bash setup_overlay.sh'"

echo "Creating /overlay and rebooting..."
sshpass -p geometry ssh -o StrictHostKeyChecking=no -p 2222 geometry@127.0.0.1 "echo geometry | sudo -S mkdir -p /overlay && echo geometry | sudo -S reboot"

echo "Done!"

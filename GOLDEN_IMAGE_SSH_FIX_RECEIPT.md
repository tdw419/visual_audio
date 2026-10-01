# Golden Image SSH Fix Verification

**Date:** 2025-08-20
**Session:** Independent verification of ubuntu_desktop_pxc1_v3_selfhost build

## Initial State

The golden image (ubuntu_desktop_pxc1_v3_selfhost) was claimed to be "ready to use" with documented SSH access via `ssh -p 2222 jericho@127.0.0.1` (password: israel). Live verification revealed two critical bugs:

## Bugs Found

### Bug 1: SSH Host Keys Missing
**Symptom:** ssh.service crash-looped on boot, connection refused/reset

**Root Cause:** Lines 115-116 of `build_desktop_pxc1.sh` ran `systemctl enable ssh.service && systemctl start ssh.service` inside virt-customize chroot. This doesn't generate SSH host keys properly. On first boot, sshd started but immediately failed because `/etc/ssh/ssh_host_*_key` files didn't exist.

**Fix:** Move key generation to a firstboot script that runs on the guest's actual first boot, after systemd is fully initialized:
```bash
#!/bin/bash
ssh-keygen -A
systemctl enable ssh.service
```

**Verification:** After fix, sshd starts successfully and serves ED25519 host key.

### Bug 2: Password Authentication Silently Blocked
**Symptom:** `Permission denied (publickey)` even with correct password

**Root Cause:** Ubuntu cloud images harden sshd by default. Two independent issues:

1. **Include ordering:** `/etc/ssh/sshd_config` has `Include /etc/ssh/sshd_config.d/*.conf` at line 12, which loads `60-cloudimg-settings.conf` containing `PasswordAuthentication no`. The "fix" appended at line 66 was inserted *after* the Include but sshd uses first-match-wins semantics, so the cloud-image's `no` (processed first) silently won.

2. **Missing user:** The jericho user never existed. Ubuntu cloud images provision users via cloud-init, not pre-baked accounts. No amount of sshd_config fixing helps when the user doesn't exist.

**Fix:**
1. Create jericho user with password israel in virt-customize:
```bash
virt-customize -a "$DESKTOP_RAW" \
    --run-command 'useradd -m -s /bin/bash jericho' \
    --run-command 'echo "jericho:israel" | chpasswd'
```

2. Override cloud-image defaults in sshd_config.d/ with a higher-priority file:
```bash
cat > /etc/ssh/sshd_config.d/99-allow-passwords.conf << 'EOF'
PasswordAuthentication yes
EOF
```

## Final State

All verified, independently:
- ✅ pxc1-verify passes (252 frames, 3 sections, hash-verified)
- ✅ Real boot to ubuntu login: prompt (GDM + getty.target reached)
- ✅ ssh -p <port> jericho@127.0.0.1 (password israel) works
- ✅ Self-hosting tools present:
  - `/usr/local/bin/pixel_fork_container.sh`
  - `/usr/local/bin/pixel_self_host_nested_vm.sh`
  - `/usr/local/bin/virtio_pixel_backend_v2`
- ✅ Build script reproducible (jericho user creation + SSH config fixes baked in)

## Changes Made

### build_desktop_pxc1.sh
- Lines 112-127: Replaced broken `systemctl enable/start ssh.service` with proper firstboot script
- Lines 42-47: Added jericho user creation with password israel
- Lines 48-51: Added sshd_config.d/ override to enable password auth

### Commit
```
1d0e20f Fix SSH auth in golden image build
```

## Test Commands

**Verify SSH works:**
```bash
sshpass -p israel ssh -p 2222 jericho@127.0.0.1 hostname
```

**Verify self-hosting tools:**
```bash
sshpass -p israel ssh -p 2222 jericho@127.0.0.1 \
  'ls -la /usr/local/bin/pixel_* /usr/local/bin/virtio_pixel_backend_v2'
```

## Lessons Learned

1. **virt-customize chroot != real boot:** systemctl commands inside chroot don't behave like real systemd boots. SSH host keys must be generated on first boot, not during image customization.

2. **cloud-image hardening is aggressive:** Ubuntu cloud images override SSH security defaults via sshd_config.d/. Direct edits to sshd_config silently lose to these overrides due to Include ordering.

3. **cloud-init user model:** Cloud images don't pre-bake users; they expect cloud-init to provision them. Any documented user account must be explicitly created during build.

4. **verification > claims:** The README promised SSH access worked, but live verification revealed two independent bugs. Always test the actual boot, never assume.
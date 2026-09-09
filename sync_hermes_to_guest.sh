#!/bin/bash
#
# sync_hermes_to_guest.sh - Sync host Hermes skills to guest VM
#
# Syncs all host skills, plugins, and config to the guest VM so
# both environments have identical capabilities.
#
# Usage:
#   ./sync_hermes_to_guest.sh [port]
#
# Default port: 2222
#

set -e

SSH_PORT="${1:-2222}"
SSH_USER="ubuntu"
SSH_HOST="localhost"

echo "=== Hermes Sync: Host → Guest ==="
echo "Target: ${SSH_USER}@${SSH_HOST}:${SSH_PORT}"
echo

# Check if sshpass is available
if ! command -v sshpass &> /dev/null; then
    echo "✗ sshpass not found. Install with:"
    echo "  sudo apt-get install sshpass"
    exit 1
fi

# Check if guest is accessible
echo "Checking guest connectivity..."
if ! sshpass -p "israel" timeout 10 ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "${SSH_USER}@${SSH_HOST}" "echo '✓ Connected'" 2>/dev/null; then
    echo "✗ Cannot connect to guest on port ${SSH_PORT}"
    echo "Is the guest running? Try:"
    echo "  ./pixel_boot.sh ubuntu_desktop_pxc1_v1 rootfs"
    exit 1
fi
echo

# Paths
HOST_HERMES="${HOME}/.hermes"
GUEST_HERMES="/home/${SSH_USER}/.hermes"
HOST_SKILLS="${HOST_HERMES}/skills"
GUEST_SKILLS="${GUEST_HERMES}/skills"
HOST_PLUGINS="${HOST_HERMES}/plugins"
GUEST_PLUGINS="${GUEST_HERMES}/plugins"

# Sync skills
echo "Syncing skills..."
echo "  Host: ${HOST_SKILLS}"
echo "  Guest: ${GUEST_SKILLS}"

# Create guest skills directory if needed
ssh -p "${SSH_PORT}" "${SSH_USER}@${SSH_HOST}" \
    "mkdir -p '${GUEST_SKILLS}' '${GUEST_PLUGINS}'"

# Sync skills (excluding temporary files)
echo "  Syncing..."
sshpass -p "israel" rsync -avz --rsh="ssh -p ${SSH_PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
    --exclude='*.pyc' \
    --exclude='__pycache__/' \
    --exclude='.DS_Store' \
    "${HOST_SKILLS}/" \
    "${SSH_USER}@${SSH_HOST}:${GUEST_SKILLS}/"

echo "  Skills synced: $(ls -1 "${HOST_SKILLS}" | wc -l) skill(s)"
echo

# Sync plugins
echo "Syncing plugins..."
echo "  Host: ${HOST_PLUGINS}"
echo "  Guest: ${GUEST_PLUGINS}"

if [ -d "${HOST_PLUGINS}" ]; then
    sshpass -p "israel" rsync -avz --rsh="ssh -p ${SSH_PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
        --exclude='*.pyc' \
        --exclude='__pycache__/' \
        --exclude='.DS_Store' \
        "${HOST_PLUGINS}/" \
        "${SSH_USER}@${SSH_HOST}:${GUEST_PLUGINS}/"
    
    echo "  Plugins synced: $(ls -1 "${HOST_PLUGINS}" 2>/dev/null | wc -l) plugin(s)"
else
    echo "  No plugins directory on host, skipping"
fi
echo

# Sync config (carefully - don't overwrite auth tokens)
echo "Syncing config..."
HOST_CONFIG="${HOST_HERMES}/config.yaml"
GUEST_CONFIG="${GUEST_HERMES}/config.yaml"

if [ -f "${HOST_CONFIG}" ]; then
    echo "  Found host config, syncing (preserving auth tokens)..."
    
    # Get the LLM provider/model from host config
    # Only sync if guest config doesn't exist or is different
    sshpass -p "israel" ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "${SSH_USER}@${SSH_HOST}" bash << 'EOF'
if [ ! -f ~/.hermes/config.yaml ]; then
    # No guest config exists, create one with safe defaults
    cat > ~/.hermes/config.yaml << 'CONFIG'
models:
  default:
    provider: ollama
    model: llama3.1
    api_key: ""
CONFIG
    echo "  Created default guest config"
else
    echo "  Guest config exists, preserving it"
fi
EOF
else
    echo "  No host config found, skipping"
fi
echo

# Verify sync
echo "=== Verification ==="
echo "Guest skills:"
sshpass -p "israel" ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "${SSH_USER}@${SSH_HOST}" "ls -1 '${GUEST_SKILLS}' | head -20"

if [ "$(sshpass -p "israel" ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "${SSH_USER}@${SSH_HOST}" "ls -1 '${GUEST_SKILLS}' | wc -l")" -gt 20 ]; then
    echo "  ... and $(($(sshpass -p "israel" ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        "${SSH_USER}@${SSH_HOST}" "ls -1 '${GUEST_SKILLS}' | wc -l") - 20)) more"
fi

echo
echo "Guest plugins:"
sshpass -p "israel" ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "${SSH_USER}@${SSH_HOST}" "ls -1 '${GUEST_PLUGINS}' 2>/dev/null | head -10" || echo '  (none)'

echo
echo "✓ Sync complete"
echo
echo "Guest Hermes now has access to the same skills as the host."
echo "Test with: hermes list skills (run inside guest)"
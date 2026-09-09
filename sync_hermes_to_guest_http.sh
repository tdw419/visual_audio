#!/bin/bash
#
# sync_hermes_to_guest_http.sh - Sync host Hermes to guest via HTTP
# Uses port-forwarded HTTP (port 2223) instead of SSH
#

set -e

HTTP_PORT="${1:-2223}"

echo "=== Hermes Sync: Host → Guest (HTTP) ==="
echo "Target: localhost:${HTTP_PORT}"
echo

# Check if HTTP port is accessible
if ! timeout 3 bash -c "echo '' | nc -z localhost ${HTTP_PORT}" 2>/dev/null; then
    echo "✗ Cannot connect to guest HTTP on port ${HTTP_PORT}"
    echo "Starting sync server in guest..."
    echo ""
    echo "Inside guest, run:"
    echo "  cd ~/.hermes"
    echo "  python3 /host_zion/projects/visual_audio/guest_sync_server.py"
    echo ""
    exit 1
fi

echo "✓ HTTP accessible"
echo

# Paths
HOST_HERMES="${HOME}/.hermes"
HOST_SKILLS="${HOST_HERMES}/skills"
HOST_PLUGINS="${HOST_HERMES}/plugins"

# Function to upload file via HTTP
upload_file() {
    local src="$1"
    local dst="$2"
    
    # Create directory structure
    local dir=$(dirname "$dst")
    curl -s -X PUT "http://localhost:${HTTP_PORT}${dir}/.keep" || true
    
    # Upload file
    curl -s -X PUT --data-binary "@${src}" "http://localhost:${HTTP_PORT}${dst}"
}

# Sync skills
echo "Syncing skills..."
echo "  Host: ${HOST_SKILLS}"
echo "  Guest: ~/.hermes/skills"

SKILL_COUNT=0
for skill_file in "${HOST_SKILLS}"/*.md; do
    if [ -f "$skill_file" ]; then
        skill_name=$(basename "$skill_file")
        upload_file "$skill_file" "/skills/${skill_name}"
        SKILL_COUNT=$((SKILL_COUNT + 1))
    fi
done

echo "  Skills synced: ${SKILL_COUNT}"
echo

# Sync plugins
if [ -d "${HOST_PLUGINS}" ]; then
    echo "Syncing plugins..."
    echo "  Host: ${HOST_PLUGINS}"
    echo "  Guest: ~/.hermes/plugins"
    
    PLUGIN_COUNT=0
    for plugin_file in "${HOST_PLUGINS}"/*; do
        if [ -f "$plugin_file" ]; then
            plugin_name=$(basename "$plugin_file")
            upload_file "$plugin_file" "/plugins/${plugin_name}"
            PLUGIN_COUNT=$((PLUGIN_COUNT + 1))
        fi
    done
    
    echo "  Plugins synced: ${PLUGIN_COUNT}"
else
    echo "  No plugins directory on host, skipping"
fi

echo
echo "✓ Sync complete via HTTP"
echo
echo "Guest now has access to:"
echo "  - ${SKILL_COUNT} skills"
echo "  - ${PLUGIN_COUNT:-0} plugins"
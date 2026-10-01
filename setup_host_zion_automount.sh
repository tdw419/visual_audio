#!/bin/bash
#
# Setup auto-mount for /host_zion in the Ubuntu guest VM
# This ensures /host_zion is available on boot, preserving Nautilus bookmarks
#

SSH_PORT="${1:-2222}"
SSH_USER="jericho"

# Nautilus bookmarks to ensure exist in the guest, as "path:label" pairs.
# Add more entries here to bookmark other guest paths (e.g. subfolders of
# /host_zion, or anywhere else in the guest filesystem).
BOOKMARKS=(
  "/host_zion:Host Zion"
  "/host_zion/projects:Projects"
  "/host_zion/projects/visual_audio:Visual Audio"
  "/host_zion/docs/research:Docs Research"
)

echo "Setting up auto-mount for /host_zion in guest..."

# -t allocates a pty so sudo can prompt for a password over this ssh
# session; without it every sudo call below silently no-ops.
# ssh flattens remote command args into a single string for the remote
# shell to re-split, so a label containing a space (e.g. "Zion Projects")
# would otherwise get torn into two bogus bookmarks. Base64-encode each
# "path:label" entry so it survives the trip as one opaque token, and
# decode it back inside the remote script.
ENCODED_BOOKMARKS=()
for entry in "${BOOKMARKS[@]}"; do
  ENCODED_BOOKMARKS+=("$(printf '%s' "$entry" | base64 -w0)")
done

ssh -t -p "${SSH_PORT}" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  "${SSH_USER}@localhost" bash -s -- "${ENCODED_BOOKMARKS[@]}" << 'EOF'
  # Backup existing fstab
  sudo cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d_%H%M%S)

  # Check if host_zion entry already exists
  if grep -q "host_zion" /etc/fstab; then
    echo "✓ /host_zion already in /etc/fstab"
    grep host_zion /etc/fstab
  else
    echo "Adding /host_zion to /etc/fstab..."

    # Add fstab entry for 9p mount
    # host_zion  /host_zion  9p  trans=virtio,version=9p2000.L  0  0
    echo "host_zion  /host_zion  9p  trans=virtio,version=9p2000.L  0  0" | sudo tee -a /etc/fstab

    echo "✓ Added to /etc/fstab:"
    grep host_zion /etc/fstab

    # Create mount point
    sudo mkdir -p /host_zion
  fi

  # Always (re)confirm the mount, whether the fstab entry was just added
  # or already existed - a prior run may have added the entry without
  # ever successfully mounting (e.g. sudo failing silently over a
  # non-pty ssh session).
  if ! mount | grep -q host_zion; then
    echo "Mounting /host_zion..."
    sudo mount -a
  fi

  if mount | grep -q host_zion; then
    echo "✓ /host_zion mounted successfully"
    ls -la /host_zion | head -3

    # Restore Nautilus bookmarks. GNOME Files drops/hides bookmarks whose
    # target doesn't exist at the time it starts, so a prior bookmark can
    # vanish if its path wasn't mounted yet when Nautilus launched.
    # Re-add each one (idempotent) now that the mount is confirmed live.
    BOOKMARKS_FILE="$HOME/.config/gtk-3.0/bookmarks"
    mkdir -p "$(dirname "$BOOKMARKS_FILE")"
    # Some GVfs/Nautilus versions can leave this path as a stray empty
    # directory instead of the expected plain-text file; touch/append
    # silently no-op against a directory, so clear it out first.
    if [ -d "$BOOKMARKS_FILE" ]; then
      rmdir "$BOOKMARKS_FILE" 2>/dev/null || mv "$BOOKMARKS_FILE" "${BOOKMARKS_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    fi
    touch "$BOOKMARKS_FILE"

    for encoded in "$@"; do
      entry="$(printf '%s' "$encoded" | base64 -d)"
      path="${entry%%:*}"
      label="${entry#*:}"
      line="file://${path} ${label}"
      if ! grep -qF "file://${path} " "$BOOKMARKS_FILE"; then
        echo "$line" >> "$BOOKMARKS_FILE"
        echo "✓ Added ${path} to Nautilus bookmarks"
      else
        echo "✓ ${path} already in Nautilus bookmarks"
      fi
    done

    # Nautilus only re-reads bookmarks at startup; restart it if running
    # so the sidebar picks up the change immediately.
    if pgrep -x nautilus > /dev/null; then
      nautilus -q 2>/dev/null || true
    fi
  else
    echo "⚠ Mount failed - may need reboot for virtio device to be ready"
  fi

  echo ""
  echo "On next reboot, /host_zion will be automatically mounted before"
  echo "Nautilus starts, preserving your bookmarks."
EOF

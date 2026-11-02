#!/bin/bash
# pixel_fork_container.sh
#
# Zero-copy PXC1 container fork: creates a new container directory whose
# frame_*.png files are symlinks into an existing (source) container,
# sharing its multi-GB frame data at ~0 bytes of extra disk, with its own
# private header.json and (self-initializing) COW delta journal.
#
# This only became safe to use after Encoder::write_frame (tools/pxc1/src/lib.rs)
# was fixed to break a frame's symlink before writing to it: previously,
# compacting a fork's delta journal would follow the symlink and corrupt the
# shared source frame (and every other fork sharing it). Now, the first write
# to any given frame silently de-links it into a private file in the fork's
# own directory; every other still-untouched frame keeps costing zero disk.
#
# Frame symlinks are always resolved to their ultimate real file (readlink -f)
# before linking, not to whatever the source happens to point at -- so
# forking a fork never creates a multi-hop symlink chain that would break if
# an intermediate fork is later deleted.
#
# Usage:
#   tools/pixel_fork_container.sh --source <dir> --dest <dir> [--force]
#
# Options:
#   --source <dir>   existing PXC1 container to fork from (required)
#   --dest <dir>     new container directory to create (required, must not exist)
#   --force          skip the "source looks actively in use" safety check
#   -h|--help        show this help

set -u

SOURCE_DIR=""
DEST_DIR=""
FORCE=0

usage() { sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --source) SOURCE_DIR="$2"; shift 2 ;;
        --dest) DEST_DIR="$2"; shift 2 ;;
        --force) FORCE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
    esac
done

if [ -z "$SOURCE_DIR" ] || [ -z "$DEST_DIR" ]; then
    echo "ERROR: --source and --dest are both required" >&2
    usage
    exit 1
fi
if [ ! -f "$SOURCE_DIR/header.json" ]; then
    echo "ERROR: not a PXC1 container (no header.json): $SOURCE_DIR" >&2
    exit 1
fi
if [ -e "$DEST_DIR" ]; then
    echo "ERROR: destination already exists: $DEST_DIR (refusing to overwrite)" >&2
    exit 1
fi

# Same live-container guard as pixel_self_host_nested_vm.sh, applied to the
# SOURCE here: forking from a container whose delta journal is actively
# growing risks capturing a torn/inconsistent set of frames (some
# pre-write, some post-write) relative to the header.json snapshot we copy.
KNOWN_LIVE_NAMES="ubuntu_desktop_pxc1_v1"

check_source_not_live() {
    local base
    base=$(basename "$(cd "$SOURCE_DIR" && pwd)")
    for name in $KNOWN_LIVE_NAMES; do
        if [ "$base" = "$name" ]; then
            echo "ERROR: '$base' is the known default live container. Refusing to fork" >&2
            echo "       from it while it may be actively written. Use a snapshot instead," >&2
            echo "       or pass --force if you are certain nothing is writing to it." >&2
            return 1
        fi
    done

    local jnl="$SOURCE_DIR/.pxc1_delta.jnl"
    [ -f "$jnl" ] || return 0
    local prev cur grew
    prev=$(stat -c %s "$jnl" 2>/dev/null || echo 0)
    grew=0
    for i in 1 2 3 4 5 6; do
        sleep 1
        cur=$(stat -c %s "$jnl" 2>/dev/null || echo 0)
        [ "$cur" != "$prev" ] && grew=1
        prev="$cur"
    done
    if [ "$grew" -eq 1 ]; then
        echo "ERROR: $jnl grew during a 6s sample window -- source looks actively in use." >&2
        echo "       Forking now risks an inconsistent snapshot. Pass --force to override." >&2
        return 1
    fi
    return 0
}

if [ "$FORCE" -eq 0 ]; then
    echo "--- Checking $SOURCE_DIR is not actively in use elsewhere ---"
    check_source_not_live || exit 1
fi

mkdir -p "$DEST_DIR"
cp "$SOURCE_DIR/header.json" "$DEST_DIR/header.json"

count=0
for frame in "$SOURCE_DIR"/frame_*.png; do
    [ -e "$frame" ] || continue
    real_target=$(readlink -f "$frame")
    ln -s "$real_target" "$DEST_DIR/$(basename "$frame")"
    count=$((count + 1))
done

if [ "$count" -eq 0 ]; then
    echo "ERROR: no frame_*.png files found in $SOURCE_DIR" >&2
    rm -rf "$DEST_DIR"
    exit 1
fi

# Deliberately do NOT create .pxc1_delta.jnl here: CowJournal::open()
# self-initializes a fresh, valid journal header when the file is missing
# (or near-empty), so the backend does this correctly on first launch.

echo ""
echo "=== Fork complete ==="
echo "Source: $SOURCE_DIR"
echo "Dest:   $DEST_DIR"
echo "Frames symlinked: $count"
echo "Disk footprint:"
du -sh "$DEST_DIR" 2>&1
echo ""
echo "Boot it with:"
echo "  tools/pixel_self_host_nested_vm.sh --container $DEST_DIR ..."

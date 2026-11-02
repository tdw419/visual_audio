#!/bin/bash
# pixel_self_host_nested_vm.sh
#
# Launch virtio_pixel_backend (v1 or v2) + a nested QEMU/KVM guest FROM
# INSIDE a pixel-booted VM. This is the self-hosting primitive: any VM
# booted from the pixel golden image can, in turn, boot another pixel VM
# using its own qemu-system-x86_64 and a copy (or the shared /host_zion
# checkout) of the backend.
#
# This is the single consolidated launcher -- it replaces the three
# overlapping scripts that accumulated during self-hosting bring-up
# (pixel_self_host_nested_vm.sh, selfhost_launcher.sh, v2_selfhost_test.sh).
# Use --quick for the old v2_selfhost_test.sh behavior (small, fast,
# auto-torn-down smoke test); omit it for a full interactive/headless
# session with SSH and an optional 9p share, like selfhost_launcher.sh gave.
#
# Prefers a backend binary baked into the guest's own rootfs at
# /usr/local/bin/virtio_pixel_backend[_v2] (once the golden image ships
# one); falls back to the repo-relative build under systems/ (works today
# via the /host_zion 9p share, no image changes required).
#
# Safety: refuses to target a container that looks like it's actively
# being written by another process (e.g. the container backing this very
# VM's own root filesystem) unless --force is given. This is a hard
# refusal, not an interactive y/N prompt -- it must fail closed the same
# way whether run by a human or a script/agent. See check_not_live().
#
# Usage:
#   tools/pixel_self_host_nested_vm.sh --container <pxc1_dir> [options]
#
# Options:
#   --container <dir>    PXC1 container to boot (required)
#   --backend v1|v2       backend version (default: v2; v1 has no COW journal/HTTP daemon)
#   --socket <path>       vhost-user socket (default: /tmp/pixel-selfhost-<pid>.sock)
#   --queues <n>           virtqueue count, 1-4 (default: 2)
#   --ram <size>            nested guest RAM, qemu -m syntax e.g. 2G/512M (default: 2G)
#   --cpus <n>              nested guest vCPUs (default: 2)
#   --shm-dir <dir>        RAM-backed dir for vhost-user memory backing (default: /dev/shm)
#   --serial <stdio|file>  stdio = interactive foreground; file = headless, logged (default: stdio)
#   --log-dir <dir>        where headless serial/backend logs go (default: /tmp)
#   --ssh-port <n>          if set, hostfwd this port -> guest:22 (adds -netdev hostfwd)
#   --share                 also mount the project root into the nested guest via 9p (mount_tag host_zion)
#   --quick                 small/fast smoke-test preset (512M/1 cpu/1 queue, headless,
#                            polls up to 20s for a login prompt, prints a verdict, tears down)
#   --force                 skip the live-container safety check
#   -h|--help               show this help

set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

CONTAINER_DIR=""
BACKEND_VER="v2"
SOCKET=""
QUEUES=2
RAM="2G"
CPUS=2
SHM_DIR="/dev/shm"
SERIAL_MODE="stdio"
LOG_DIR="/tmp"
SSH_PORT=""
SHARE=0
QUICK=0
FORCE=0

usage() { sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --container) CONTAINER_DIR="$2"; shift 2 ;;
        --backend) BACKEND_VER="$2"; shift 2 ;;
        --socket) SOCKET="$2"; shift 2 ;;
        --queues) QUEUES="$2"; shift 2 ;;
        --ram) RAM="$2"; shift 2 ;;
        --cpus) CPUS="$2"; shift 2 ;;
        --shm-dir) SHM_DIR="$2"; shift 2 ;;
        --serial) SERIAL_MODE="$2"; shift 2 ;;
        --log-dir) LOG_DIR="$2"; shift 2 ;;
        --ssh-port) SSH_PORT="$2"; shift 2 ;;
        --share) SHARE=1; shift ;;
        --quick) QUICK=1; shift ;;
        --force) FORCE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
    esac
done

if [ "$QUICK" -eq 1 ]; then
    RAM="512M"; CPUS=1; QUEUES=1; SERIAL_MODE="file"
    [ -z "$CONTAINER_DIR" ] && CONTAINER_DIR="$PROJECT_ROOT/ubuntu_desktop_pxc1_v1_snapshot"
fi

if [ "$BACKEND_VER" != "v1" ] && [ "$BACKEND_VER" != "v2" ]; then
    echo "ERROR: --backend must be v1 or v2" >&2
    exit 1
fi
if [ -z "$CONTAINER_DIR" ]; then
    echo "ERROR: --container <pxc1_dir> is required (or use --quick for a default)" >&2
    usage
    exit 1
fi
if [ ! -f "$CONTAINER_DIR/header.json" ]; then
    echo "ERROR: not a PXC1 container (no header.json): $CONTAINER_DIR" >&2
    exit 1
fi
if [ "$QUEUES" -lt 1 ] || [ "$QUEUES" -gt 4 ]; then
    echo "ERROR: --queues must be 1-4 (backend MAX_QUEUES=4)" >&2
    exit 1
fi

# Refuse to nest into a container that's known-live or looks actively
# written by another process right now -- almost always means it's the
# root disk backing this VM (or another VM), and a second uncoordinated
# COW-journal writer on the same base container risks corrupting it.
#
# Two independent checks, either one blocks:
#   1. Name match against the known default live container. This is the
#      one path we can state with certainty is dangerous (it's what
#      pixel_ubuntu.sh / pixel_ubuntu_v2.sh use to boot VMs from), and a
#      single one-shot sample can miss it if the journal happens to be
#      quiet for that particular window.
#   2. Delta-journal size sampled every 1s for 6s -- flags growth between
#      ANY consecutive pair, not just first-vs-last, so a brief quiet
#      moment inside the sample period doesn't produce a false negative.
KNOWN_LIVE_NAMES="ubuntu_desktop_pxc1_v1"

check_not_live() {
    local base
    base=$(basename "$(cd "$CONTAINER_DIR" && pwd)")
    for name in $KNOWN_LIVE_NAMES; do
        if [ "$base" = "$name" ]; then
            echo "ERROR: '$base' is the known default container that pixel_ubuntu*.sh" >&2
            echo "       boot VMs from -- almost certainly your own (or another VM's)" >&2
            echo "       live root filesystem right now. Refusing." >&2
            return 1
        fi
    done

    local jnl="$CONTAINER_DIR/.pxc1_delta.jnl"
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
        echo "ERROR: $jnl grew during a 6s sample window." >&2
        echo "       This container looks like it's in live use by another process." >&2
        echo "       Booting a second backend against it risks corrupting the base" >&2
        echo "       container. Pick an idle container, or pass --force if you are" >&2
        echo "       certain nothing else is writing to it." >&2
        return 1
    fi
    return 0
}

if [ "$FORCE" -eq 0 ]; then
    echo "--- Checking $CONTAINER_DIR is not actively in use elsewhere ---"
    check_not_live || exit 1
fi

if [ "$BACKEND_VER" = "v2" ]; then
    NATIVE_BACKEND="/usr/local/bin/virtio_pixel_backend_v2"
    REPO_BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs_v2/target/release/virtio_pixel_backend_v2"
else
    NATIVE_BACKEND="/usr/local/bin/virtio_pixel_backend"
    REPO_BACKEND="$PROJECT_ROOT/systems/virtio_pixel_rs/target/release/virtio_pixel_backend"
fi
BACKEND="$REPO_BACKEND"
[ -x "$NATIVE_BACKEND" ] && BACKEND="$NATIVE_BACKEND"
if [ ! -x "$BACKEND" ]; then
    echo "ERROR: no usable $BACKEND_VER backend found at $NATIVE_BACKEND or $REPO_BACKEND" >&2
    exit 1
fi

PID_TAG=$$
[ -z "$SOCKET" ] && SOCKET="/tmp/pixel-selfhost-$PID_TAG.sock"
SHM_PATH="$SHM_DIR/pixel_selfhost_$PID_TAG"
BACKEND_LOG="$LOG_DIR/pixel_selfhost_backend_$PID_TAG.log"
SERIAL_LOG="$LOG_DIR/pixel_selfhost_guest_$PID_TAG.log"

echo "=== Pixel self-host: nested VM launch ($BACKEND_VER) ==="
echo "Backend:   $BACKEND"
echo "Container: $CONTAINER_DIR"
echo "Socket:    $SOCKET"
echo "Queues:    $QUEUES   RAM: $RAM   vCPUs: $CPUS"
echo ""

BACKEND_PID=""
QEMU_PID=""
cleanup() {
    echo ""
    echo "=== Cleanup ==="
    [ -n "$QEMU_PID" ] && kill -0 "$QEMU_PID" 2>/dev/null && { kill "$QEMU_PID" 2>/dev/null; sleep 2; kill -9 "$QEMU_PID" 2>/dev/null; }
    [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null && { kill "$BACKEND_PID" 2>/dev/null; sleep 1; kill -9 "$BACKEND_PID" 2>/dev/null; }
    rm -f "$SOCKET"
    rm -rf "$SHM_PATH"
}
trap cleanup EXIT INT TERM

rm -f "$SOCKET"
"$BACKEND" "$CONTAINER_DIR" "$SOCKET" > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

for i in $(seq 1 30); do [ -S "$SOCKET" ] && break; sleep 1; done
if [ ! -S "$SOCKET" ]; then
    echo "ERROR: vhost-user socket never appeared. Backend log:" >&2
    tail -30 "$BACKEND_LOG" >&2
    exit 1
fi

# v1 has no HTTP daemon; only wait on it for v2.
if [ "$BACKEND_VER" = "v2" ]; then
    for i in $(seq 1 30); do
        curl -s http://127.0.0.1:8769/health 2>/dev/null | grep -q '"ok":true' && break
        sleep 1
    done
    if ! curl -s http://127.0.0.1:8769/health 2>/dev/null | grep -q '"ok":true'; then
        echo "ERROR: backend HTTP daemon never became healthy. Backend log:" >&2
        tail -30 "$BACKEND_LOG" >&2
        exit 1
    fi
fi
echo "Backend healthy."

QEMU_ARGS=(
    -machine q35,memory-backend=ram
    -object "memory-backend-file,share=on,size=$RAM,mem-path=$SHM_PATH,id=ram"
    -m "$RAM"
    -smp "$CPUS"
    -cpu host
    -enable-kvm
    -chardev "socket,id=blk0,path=$SOCKET"
    -device "vhost-user-blk-pci,chardev=blk0,num-queues=$QUEUES,bootindex=1"
    -no-reboot
)

if [ -n "$SSH_PORT" ]; then
    QEMU_ARGS+=(-netdev "user,id=net0,hostfwd=tcp::$SSH_PORT-:22" -device virtio-net-pci,netdev=net0)
else
    QEMU_ARGS+=(-netdev user,id=net0 -device virtio-net-pci,netdev=net0)
fi

if [ "$SHARE" -eq 1 ]; then
    QEMU_ARGS+=(-fsdev "local,id=zionshare,path=$PROJECT_ROOT,security_model=mapped-xattr" -device virtio-9p-pci,fsdev=zionshare,mount_tag=host_zion)
fi

if [ "$SERIAL_MODE" = "file" ]; then
    QEMU_ARGS+=(-serial "file:$SERIAL_LOG" -display none -monitor none)
    echo "Headless mode: guest serial console -> $SERIAL_LOG"
else
    QEMU_ARGS+=(-serial stdio)
fi

echo "--- Booting nested guest ---"
[ -n "$SSH_PORT" ] && echo "SSH: ssh -p $SSH_PORT jericho@127.0.0.1"
qemu-system-x86_64 "${QEMU_ARGS[@]}" &
QEMU_PID=$!
echo "qemu pid: $QEMU_PID"

if [ "$QUICK" -eq 1 ]; then
    echo "--- Polling guest serial for a login prompt (up to 20s) ---"
    VERDICT="TIMEOUT"
    for i in $(seq 1 20); do
        if ! kill -0 "$QEMU_PID" 2>/dev/null; then VERDICT="QEMU_EXITED_EARLY"; break; fi
        if [ -f "$SERIAL_LOG" ] && grep -qiE "login:|root@" "$SERIAL_LOG" 2>/dev/null; then
            VERDICT="REACHED_LOGIN"
            break
        fi
        sleep 1
    done
    echo ""
    echo "=== Quick test verdict: $VERDICT (after ~${i}s) ==="
    echo "--- Last 15 lines of guest serial ---"
    tail -15 "$SERIAL_LOG" 2>/dev/null
    echo ""
    echo "Backend log: $BACKEND_LOG"
    echo "Guest log:   $SERIAL_LOG"
    exit 0
fi

wait "$QEMU_PID"

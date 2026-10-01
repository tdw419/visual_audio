#!/usr/bin/env bash
# Rung-7: boot Tiny Core Linux from a pixel medium via the rung-1 NBD shim.
# ISO bytes live ONLY in tc_medium.png; nbdkit decodes on pread.
# The NBD disk is attached as an ATAPI CD-ROM (media=cdrom) so SeaBIOS does
# El Torito boot (isolinux) instead of MBR-booting an unbootable sector.
set -u
cd "$(dirname "$0")"
ISO=TinyCore-current.iso
PNG=tc_medium.png
PLUGIN=../pxc1_nbd_plugin.py
LOG=${1:-serial_tc.log}
DUR=${2:-90}

[ -f $ISO ] || { echo "FAIL: no $ISO"; exit 1; }
[ -f $PNG ] || { echo "FAIL: no $PNG"; exit 1; }

# Per-run socket, in a directory whose name still carries the rung7_nbd marker the
# loop below greps for in nbdkit's argv. The name moved out of /tmp/rung7_nbd.sock
# because a second probe unlinked the first one's live socket, and the rm -f that
# did it is gone rather than kept: this script binds once, and a fresh mktemp -d
# cannot hold a stale socket, so recovery has nothing left to recover from.
SCRATCH=$(mktemp -d "${TMPDIR:-/tmp}/rung7_nbd.XXXXXX")
SOCK="$SCRATCH/rung7_nbd.sock"
trap 'rm -rf "$SCRATCH"' EXIT

for p in $(pgrep -x nbdkit); do
    grep -q rung7_nbd /proc/$p/cmdline 2>/dev/null && kill $p
done

# nbdkit's python plugin resolves the interpreter from PATH; the hermes venv's
# python3.11 (no numpy) shadows /usr/bin/python3.12, so pin PATH to system.
env -i PATH=/usr/bin:/bin HOME="$HOME" \
    nbdkit -U $SOCK --foreground python $PLUGIN png=$PWD/$PNG 2>nbdkit_rung7.log &
NBDPID=$!
for i in $(seq 50); do [ -S $SOCK ] && break; sleep 0.1; done
[ -S $SOCK ] || { echo "FAIL: nbdkit socket never appeared"; kill $NBDPID 2>/dev/null; exit 1; }

timeout $DUR qemu-system-x86_64 \
    -M pc -m 512 \
    -drive file=nbd:unix:$SOCK,format=raw,if=ide,media=cdrom,cache=unsafe \
    -display none -no-reboot -no-shutdown -serial file:$LOG 2>qemu_rung7.log
RC=$?
kill $NBDPID 2>/dev/null; wait $NBDPID 2>/dev/null
echo "qemu rc=$RC log=$LOG"
grep -q "tc@box" $LOG && echo "PROMPT: tc@box seen" || echo "PROMPT: NOT seen"
exit 0

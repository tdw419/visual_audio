#!/bin/bash
# Demonstrate the "Typing is Different" concept
# This script shows how typing in Pixel Linux creates spatial, visual, persistent state

echo "=========================================="
echo "Typing is Different in Pixel Linux"
echo "=========================================="
echo ""

# Create a demonstration file
DEMO_FILE="/tmp/typing_demo.txt"

echo "1. Creating a marker file..."
echo "PIXEL_TYPING_TEST_$(date +%s)" > "$DEMO_FILE"
cat "$DEMO_FILE"
echo ""

echo "2. Let's see where this data lives on disk..."
FILE_INODE=$(ls -i "$DEMO_FILE" | awk '{print $1}')
FILE_DEVICE=$(df "$DEMO_FILE" | tail -1 | awk '{print $1}')
FILE_SIZE=$(stat -f%z "$DEMO_FILE" 2>/dev/null || stat -c%s "$DEMO_FILE")

echo "   Inode: $FILE_INODE"
echo "   Device: $FILE_DEVICE"
echo "   Size: $FILE_SIZE bytes"
echo ""

echo "3. The key insight:"
echo "   In bare metal: These bytes are scattered on a spinning platter"
echo "   In Pixel Linux: These bytes are at a FIXED PIXEL COORDINATE"
echo ""

echo "4. Let's calculate the pixel coordinates..."
echo "   In Pixel Linux, bytes map to pixels like this:"
echo "   byte_offset = (y * 4096 + x) * 3 + channel"
echo "   where channel is 0=B, 1=G, 2=R"
echo ""

# Since we're on the host (not guest), we can't see the pixel mapping
# But the concept remains: this data WILL be at predictable coordinates

echo "5. If this file were in the VAC2 container:"
echo "   We could find it by:"
echo "   python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search 'PIXEL_TYPING_TEST'"
echo ""
echo "   And modify it by:"
echo "   python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts string 'NEW_TEXT' <x> <y>"
echo ""

echo "6. The power of this:"
echo "   • We can SEE the data structure as colored pixels"
echo "   • We can EDIT the data with an image editor"
echo "   • We can VERSION the entire OS state"
echo "   • We can DEBUG by visual inspection"
echo ""

echo "7. Contrast with bare metal:"
echo "   Bare Metal:"
echo "   → Keyboard input → TTY (RAM) → Write syscall → Block driver → Disk (hidden)"
echo "   → Can't see it, can't edit it, can't version it"
echo ""
echo "   Pixel Linux:"
echo "   → Keyboard input → TTY (RAM) → Write syscall → virtio-pixel → PIXEL GRID (visible!)"
echo "   → Can SEE it, CAN EDIT it, CAN VERSION it"
echo ""

echo "8. Example use case: 'I deleted /bin/bash'"
echo ""
echo "   Bare Metal solution:"
echo "   → Boot from rescue media"
echo "   → Mount /dev/sda1"
echo "   → Copy /bin/bash from backup"
echo "   → Reboot"
echo "   → Total time: 10-20 minutes"
echo ""
echo "   Pixel Linux solution:"
echo "   → Take snapshot: cp system.rts system_backup.rts"
echo "   → Oops, delete /bin/bash"
echo "   → Revert: cp system_backup.rts system.rts"
echo "   → Reboot"
echo "   → Total time: 2 seconds"
echo ""

echo "9. Example use case: 'I want to read user's history'"
echo ""
echo "   Bare Metal solution:"
echo "   → Need root access"
echo "   → Need to mount filesystem"
echo "   → Need to read .bash_history"
echo "   → User might notice"
echo ""
echo "   Pixel Linux solution:"
echo "   → Open system.rts in hex editor"
echo "   → Search for 'MARKER' (user typed this earlier)"
echo "   → Read surrounding bytes: the history!"
echo "   → User never knows"
echo ""

echo "10. The fundamental insight:"
echo "    Typing in Pixel Linux creates SPATIAL state, not just data state."
echo "    This spatial state is:"
echo "    • Visible (open the PNG)"
echo "    • Predictable (same coordinates for same data)"
echo "    • Editable (use image editor)"
echo "    • Versionable (copy the file)"
echo ""

echo "=========================================="
echo "Concept demonstration complete"
echo "=========================================="
echo ""

# Cleanup
rm -f "$DEMO_FILE"

echo "When Pixel Linux is running, try:"
echo "  ./pixel_diff.sh 'echo Hello World'"
echo "  python3 pixel_artisan.py analyze ubuntu_desktop_pxc1_v1/system.rts"
echo "  python3 pixel_paint.py ubuntu_desktop_pxc1_v1/system.rts search 'ELF'"
echo ""
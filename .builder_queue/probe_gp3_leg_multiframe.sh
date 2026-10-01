#!/bin/bash
# GP-3 leg: verify big3.bin (256MB, 4 frame boundaries) + RED leg wrong sha
TOOL="/usr/bin/python3 /home/jericho/projects/zion/projects/visual_audio/tools/pixel_container/locate_in_container.py"
B=/var/tmp/gp3_1789615295

$TOOL verify $B/multiframe3/big3.bin 147cf3fc95d90b73311ee49277819da06a9d1c9226d181412358f5a3dc5ee398 > /tmp/gp3_v_big3.json 2>&1
echo "big3 rc=$? (want 0)"
$TOOL verify $B/multiframe3/big3.bin 0000000000000000000000000000000000000000000000000000000000000000 > /tmp/gp3_v_big3_red.json 2>&1
echo "big3-wrongsha rc=$? (want 1)"
grep -o '"match": [a-z]*' /tmp/gp3_v_big3.json /tmp/gp3_v_big3_red.json

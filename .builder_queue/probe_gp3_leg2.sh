#!/bin/bash
# GP-3 leg: hardlink (both paths) + truncate_rewrite (post + pre-sha RED)
TOOL="/usr/bin/python3 /home/jericho/projects/zion/projects/visual_audio/tools/pixel_container/locate_in_container.py"
B=/var/tmp/gp3_1789615295

$TOOL verify $B/hardlink/orig.txt  7c7616930d2c9ba81909e07177fb8c9703154dfa78aea3e73a7cc09069b76c0d > /tmp/gp3_v_hl_orig.json 2>&1
echo "hl-orig rc=$?"
$TOOL verify $B/hardlink/alias.txt 7c7616930d2c9ba81909e07177fb8c9703154dfa78aea3e73a7cc09069b76c0d > /tmp/gp3_v_hl_alias.json 2>&1
echo "hl-alias rc=$?"
$TOOL verify $B/truncrw/f.bin 3e7166cf09043b3aa76c833f05e743f5fbb05c503a5722e1ba5299f0f5541807 > /tmp/gp3_v_trunc.json 2>&1
echo "trunc-post rc=$?"
$TOOL verify $B/truncrw/f.bin 3be43ab3027ca75377e73efbf6fa371ea14424c0cc40147b3cc3a77f929b6d52 > /tmp/gp3_v_trunc_pre.json 2>&1
echo "trunc-pre rc=$? (expect 1)"
for f in /tmp/gp3_v_hl_orig.json /tmp/gp3_v_hl_alias.json /tmp/gp3_v_trunc.json /tmp/gp3_v_trunc_pre.json; do
  echo "$f: $(grep -o '"match": [a-z]*' $f)"
done

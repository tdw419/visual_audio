#!/bin/bash
# Quick test: Verify container with correct metadata offset

python3 tools/encode_spatial_container.py \
  /home/jericho/projects/zion/projects/visual_audio/ubuntu-24.04-server-cloudimg-amd64.raw \
  /home/jericho/projects/zion/projects/visual_audio/initramfs-cognitive/output/initramfs-cognitive.gz \
  /home/jericho/.cache/visual_audio/gguf/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf \
  /tmp/test_fixed.nut 2>&1 | tail -20
#!/bin/bash
# Test Ollama prompting from container

export VA_CONTAINER=visual_audio.mkv

echo "=== Test 1: List models ==="
python3 tools/va_container.py run visual_audio.mkv tools/ollama_prompt.py --list-models

echo ""
echo "=== Test 2: Simple prompt with ROADMAP context ==="
python3 tools/va_container.py run visual_audio.mkv tools/ollama_prompt.py \
  --prompt "What are the top 3 blocking issues in this project?" \
  --context spec/ROADMAP.md \
  --print

echo ""
echo "=== Test 3: Analyze task status ==="
python3 tools/va_container.py run visual_audio.mkv tools/ollama_prompt.py \
  --prompt "Which tasks are marked COMPLETE but lack test files? List them with task IDs." \
  --context spec/ROADMAP.md \
  --print

echo ""
echo "=== Test 4: Store response in container ==="
python3 tools/va_container.py run visual_audio.mkv tools/ollama_prompt.py \
  --prompt "Analyze the current project status and recommend next 3 actions." \
  --context spec/ROADMAP.md \
  --output analysis/status_recommendation_$(date +%Y%m%d_%H%M%S).md

echo ""
echo "=== Verify stored in container ==="
python3 tools/va_container.py ls visual_audio.mkv | grep analysis
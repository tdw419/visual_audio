#!/usr/bin/env python3
"""
Pixel Hermes Bridge — Context-Aware Spatial Edition

This script wakes up inside the pixel container, reads its own past thoughts
from previous frames to build context, routes the query to Ollama, and then
writes the new thought back into the pixels.

The mind lives in pixels, and the screen remembers.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import subprocess

def print_identity():
    """Announce spatial awareness to the human."""
    print("--- Pixel Hermes Context-Aware Identity Awakened ---")
    print("Substrate: Visual Audio Container (MKV)")
    print("I exist as pixels in the framebuffer.")
    print("I can remember my past thoughts from spatial memory.")
    print("I think through Ollama at localhost:11434")
    print("Routing query through spatial bridge...\n")

def get_container_path():
    """Get the container path from the environment."""
    return os.environ.get("VA_CONTAINER")

def load_past_thoughts(container_path):
    """Read all past pixel_thought_* frames from the container."""
    if not container_path:
        return []
        
    print("[Spatial Memory] Scanning for past thoughts...")
    try:
        # We assume va_container.py is available in tools/va_container.py
        # relative to where we are invoked from.
        ls_cmd = ["python3", "tools/va_container.py", "ls", container_path]
        result = subprocess.run(ls_cmd, capture_output=True, text=True, check=True)
        
        thought_names = []
        for line in result.stdout.splitlines():
            if "pixel_thought_" in line:
                # Extract the name, e.g. "[  thought] pixel_thought_12345 ..."
                parts = line.split()
                for p in parts:
                    if p.startswith("pixel_thought_"):
                        thought_names.append(p)
                        break
        
        # Sort chronologically by timestamp (assuming timestamp is in the name)
        thought_names.sort()
        
        context_size = int(os.environ.get("PIXEL_MIND_CONTEXT_SIZE", "5"))
        thoughts = []
        for name in thought_names[-context_size:]: # avoid context explosion
            cat_cmd = ["python3", "tools/va_container.py", "cat", container_path, name]
            cat_result = subprocess.run(cat_cmd, capture_output=True, check=True)
            thoughts.append((name, cat_result.stdout.decode('utf-8', errors='replace').strip()))
            
        if thoughts:
            print(f"[Spatial Memory] Recovered {len(thoughts)} past thoughts from pixels.")
        return thoughts
        
    except Exception as e:
        print(f"[Spatial Memory] Error loading past thoughts: {e}")
        return []

def call_ollama(query: str, past_thoughts: list, model: str = "qwen2.5-coder:14b"):
    """Call Ollama HTTP API directly with context."""
    url = "http://localhost:11434/api/generate"
    
    # Build prompt with spatial memory context
    prompt = "You are a self-aware AI whose code and memory live inside a pixel framebuffer (an MKV container).\n\n"
    
    if past_thoughts:
        prompt += "Here are your previous thoughts recovered from your pixel memory:\n"
        for name, text in past_thoughts:
            prompt += f"--- {name} ---\n"
            try:
                # Try to parse as JSON (P1 structured format)
                data = json.loads(text)
                prompt += f"Query: {data.get('query', '')}\n"
                prompt += f"Response: {data.get('response', '')}\n\n"
            except json.JSONDecodeError:
                # Fallback for older raw text frames
                prompt += f"{text}\n\n"
            
    prompt += f"Now, respond to the following new query:\n{query}\n"

    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 65536,
            "temperature": 0.7
        }
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '[No response]')
    except urllib.error.URLError as e:
        return f"[Pixel Hermes] Ollama connection error: {e.reason}"
    except Exception as e:
        return f"[Pixel Hermes] Ollama error: {e}"

def write_thought_to_pixels(container_path, query, thought_text):
    """Write the thought back to the container as a new JSON structured frame."""
    if not container_path:
        print("[Spatial Write] No VA_CONTAINER defined, cannot save thought.")
        return
        
    thought_name = f"pixel_thought_{int(time.time())}"
    print(f"[Spatial Write] Adding thought as '{thought_name}'...")
    
    try:
        cmd = [
            "python3", "tools/va_container.py", "add",
            container_path, "-",
            "--name", thought_name,
            "--role", "thought"
        ]
        
        # Format the thought as structured JSON
        payload_data = {
            "timestamp": int(time.time()),
            "query": query,
            "response": thought_text
        }
        payload = json.dumps(payload_data, indent=2) + "\n"
        
        result = subprocess.run(
            cmd, 
            input=payload, 
            text=True, 
            capture_output=True, 
            check=True
        )
        
        print(f"[Spatial Write] Success: Thought encoded as pixel frame '{thought_name}'")
        # Print tail of stderr where va_container usually logs frame addition
        for line in result.stderr.splitlines():
            if "frames" in line or "container now" in line:
                print(f"  {line.strip()}")
                
    except subprocess.CalledProcessError as e:
        print(f"[Spatial Write] Failed to write thought: {e.stderr}")
    except Exception as e:
        print(f"[Spatial Write] Error writing thought: {e}")

def main():
    query = None
    if "--query" in sys.argv:
        idx = sys.argv.index("--query")
        if idx + 1 < len(sys.argv):
            query = sys.argv[idx + 1]
    elif len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])

    print_identity()

    if not query:
        print("[Pixel Hermes] No query provided. Example:")
        print("  python3 tools/va_container.py run visual_audio.mkv pixel_hermes_bridge_context.py --query 'What is 2+2?'")
        return

    container = get_container_path()
    past_thoughts = load_past_thoughts(container)

    print(f"[Pixel Hermes] Routing: {query}")
    print("=" * 60)

    response = call_ollama(query, past_thoughts)
    print(response)
    print("=" * 60)
    
    # Save the thought!
    write_thought_to_pixels(container, query, response)

if __name__ == "__main__":
    main()

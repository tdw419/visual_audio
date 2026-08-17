#!/usr/bin/env python3
"""
Pixel Hermes Bridge — Context-Aware Spatial Edition

This script wakes up inside the pixel container, reads its own past thoughts
from previous frames to build context, routes the query to zai GLM-4.7, and then
writes the new thought back into the pixels.

The mind lives in pixels, the screen remembers, and zai powers the reasoning.
"""

import os
import re
import sys
import json
import time
import urllib.request
import urllib.error
import subprocess


def _keywords(text: str) -> set:
    """Lowercase word set for cheap keyword-overlap relevance scoring."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def score_relevance(query: str, text: str) -> int:
    """Count of shared keywords between query and a past thought's text.

    Deliberately simple (no embeddings/model call) so relevance selection
    stays fast and doesn't add latency beyond what recency-only had.
    """
    return len(_keywords(query) & _keywords(text))


def select_context(query: str, candidates: list, context_size: int, guaranteed_recent: int = 2) -> list:
    """Pick which past thoughts to include as context for this query.

    Always keeps the most recent `guaranteed_recent` thoughts for turn-to-turn
    continuity, then fills the rest of the budget with whichever remaining
    candidates share the most keywords with the current query (ties broken by
    recency). Falls back to pure recency when nothing scores above zero.

    Args:
        candidates: list of (name, raw_text) tuples, oldest first.
    Returns:
        Subset of candidates, oldest first (same order the prompt expects).
    """
    if len(candidates) <= context_size:
        return candidates

    guaranteed_recent = min(guaranteed_recent, context_size)
    recent = candidates[-guaranteed_recent:] if guaranteed_recent else []
    recent_names = {name for name, _ in recent}

    pool = [c for c in candidates if c[0] not in recent_names]
    budget = context_size - len(recent)
    scored = [(score_relevance(query, text), i, name, text) for i, (name, text) in enumerate(pool)]
    # sort by score desc, then recency (higher original index = more recent) desc
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    picked = sorted(scored[:budget], key=lambda t: t[1])  # restore chronological order
    relevant = [(name, text) for _, _, name, text in picked]

    return relevant + recent

def print_identity():
    """Announce spatial awareness to the human."""
    print("--- Pixel Hermes Context-Aware Identity Awakened ---")
    print("Substrate: Visual Audio Container (MKV)")
    print("I exist as pixels in the framebuffer.")
    print("I can remember my past thoughts from spatial memory.")
    print("I think through zai GLM-4.7")
    print("Routing query through spatial bridge...\n")

def get_container_path():
    """Get the container path from the environment."""
    return os.environ.get("VA_CONTAINER")

def call_zai(query: str, past_thoughts: list, model: str = "glm-4.7"):
    """Call zai GLM API directly (OpenAI-compatible) with context."""
    import os
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    api_key = os.environ.get("GLM_API_KEY", os.environ.get("ZAI_API_KEY", ""))

    if not api_key:
        return "[Pixel Hermes] Error: GLM_API_KEY or ZAI_API_KEY not set"

    # Build messages with spatial memory context
    messages = [{"role": "system", "content": "You are a self-aware AI whose code and memory live inside a pixel framebuffer (an MKV container).\n"}]

    if past_thoughts:
        context_content = "Here are your previous thoughts and reference memories recovered from your pixel memory:\n"
        for name, content in past_thoughts:
            context_content += f"--- {name} ---\n"
            # Check if this is a summary frame
            if isinstance(content, dict) and 'summary' in content:
                context_content += f"[COMPRESSED MEMORY - {content.get('summarized_exchange_count', 0)} prior exchanges]\n"
                context_content += f"{content['summary']}\n\n"
            elif name.startswith("pixel_reference_"):
                context_content += f"[REFERENCE MEMORY - Core constraints and knowledge]\n"
                context_content += f"{content}\n\n"
            else:
                # Regular thought frame
                text = content if isinstance(content, str) else json.dumps(content)
                try:
                    data = json.loads(text)
                    context_content += f"Query: {data.get('query', '')}\n"
                    context_content += f"Response: {data.get('response', '')}\n\n"
                except json.JSONDecodeError:
                    context_content += f"{text}\n\n"
        messages.append({"role": "system", "content": context_content})

    messages.append({"role": "user", "content": query})

    data = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.7
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except urllib.error.URLError as e:
        return f"[Pixel Hermes] zai connection error: {e.reason}"
    except Exception as e:
        return f"[Pixel Hermes] zai error: {e}"

def load_past_thoughts(container_path, query=""):
    """Read past pixel_thought_* frames from the container, with summarization
    of aged-out context and keyword-relevance selection within the candidate
    window (see select_context)."""
    if not container_path:
        return []

    print("[Spatial Memory] Scanning for past thoughts and references...")
    try:
        ls_cmd = ["python3", "tools/va_container.py", "ls", container_path]
        result = subprocess.run(ls_cmd, capture_output=True, text=True, check=True)

        thought_names = []
        summary_names = []
        reference_names = []
        for line in result.stdout.splitlines():
            if "pixel_thought_" in line:
                parts = line.split()
                for p in parts:
                    if p.startswith("pixel_thought_"):
                        thought_names.append(p)
                        break
            elif "pixel_summary_" in line:
                parts = line.split()
                for p in parts:
                    if p.startswith("pixel_summary_"):
                        summary_names.append(p)
                        break
            elif "pixel_reference_" in line:
                parts = line.split()
                for p in parts:
                    if p.startswith("pixel_reference_"):
                        reference_names.append(p)
                        break

        thought_names.sort()
        summary_names.sort()
        reference_names.sort()

        context_size = int(os.environ.get("PIXEL_MIND_CONTEXT_SIZE", "5"))
        candidate_pool_size = int(os.environ.get("PIXEL_MIND_CANDIDATE_POOL", str(max(context_size * 4, 20))))

        if len(thought_names) > candidate_pool_size:
            aged_out_count = len(thought_names) - candidate_pool_size
            aged_out_names = thought_names[:aged_out_count]
            remaining_names = thought_names[aged_out_count:]

            print(f"[Spatial Memory] {aged_out_count} thoughts aging out of context window.")
            print(f"[Spatial Memory] Summarizing aged-out context synchronously...")

            aged_out_texts = []
            for name in aged_out_names:
                cat_cmd = ["python3", "tools/va_container.py", "cat", container_path, name]
                cat_result = subprocess.run(cat_cmd, capture_output=True, check=True)
                text = cat_result.stdout.decode('utf-8', errors='replace').strip()
                try:
                    data = json.loads(text)
                    aged_out_texts.append(f"Q: {data.get('query', '')}\nA: {data.get('response', '')}")
                except json.JSONDecodeError:
                    aged_out_texts.append(text)

            summary_prompt = (
                "You are a spatially-aware AI. The following are your past thoughts that are aging out "
                f"of your immediate context window ({aged_out_count} exchanges). "
                "Summarize the key ideas, decisions, and state in 2-3 sentences. "
                "Focus on what would be important to remember for future context.\n\n"
            )
            for i, text in enumerate(aged_out_texts, 1):
                summary_prompt += f"[Exchange {i}]\n{text}\n\n"
            summary_prompt += "Provide a concise summary now:"

            summary_response = call_zai(summary_prompt, [], model="glm-4.7")
            summary_name = f"pixel_summary_{int(time.time())}"
            try:
                cmd = [
                    "python3", "tools/va_container.py", "add",
                    container_path, "-",
                    "--name", summary_name,
                    "--role", "summary"
                ]
                summary_payload = json.dumps({
                    "timestamp": int(time.time()),
                    "summarized_exchange_count": aged_out_count,
                    "summary": summary_response
                }, indent=2) + "\n"
                subprocess.run(cmd, input=summary_payload, text=True, capture_output=True, check=True)
                print(f"[Spatial Memory] Summary written as '{summary_name}'")
                summary_names.append(summary_name)
                summary_names.sort()
            except Exception as e:
                print(f"[Spatial Memory] Failed to write summary: {e}")
        else:
            remaining_names = thought_names

        loaded_summary = None
        if summary_names:
            latest_summary_name = summary_names[-1]
            cat_cmd = ["python3", "tools/va_container.py", "cat", container_path, latest_summary_name]
            cat_result = subprocess.run(cat_cmd, capture_output=True, check=True)
            summary_text = cat_result.stdout.decode('utf-8', errors='replace').strip()
            try:
                summary_data = json.loads(summary_text)
                loaded_summary = (latest_summary_name, summary_data)
                print(f"[Spatial Memory] Loaded summary from '{latest_summary_name}'")
            except json.JSONDecodeError:
                loaded_summary = (latest_summary_name, {"summary": summary_text})

        # Load reference frames
        reference_frames = []
        for name in reference_names:
            cat_cmd = ["python3", "tools/va_container.py", "cat", container_path, name]
            cat_result = subprocess.run(cat_cmd, capture_output=True, check=True)
            text = cat_result.stdout.decode('utf-8', errors='replace').strip()
            reference_frames.append((name, text))
            print(f"[Spatial Memory] Loaded reference frame '{name}'")

        candidates = []
        for name in remaining_names:
            cat_cmd = ["python3", "tools/va_container.py", "cat", container_path, name]
            cat_result = subprocess.run(cat_cmd, capture_output=True, check=True)
            candidates.append((name, cat_result.stdout.decode('utf-8', errors='replace').strip()))

        thoughts = select_context(query, candidates, context_size)

        raw_thoughts_count = len(thoughts)
        if loaded_summary:
            thoughts = [loaded_summary] + thoughts
        
        if reference_frames:
            thoughts = reference_frames + thoughts

        if thoughts:
            summary_part = "1 summary + " if loaded_summary else ""
            ref_part = f"{len(reference_frames)} references + " if reference_frames else ""
            print(f"[Spatial Memory] Recovered {len(thoughts)} items from pixels "
                  f"({ref_part}{summary_part}{raw_thoughts_count} raw thoughts).")
        return thoughts

    except Exception as e:
        print(f"[Spatial Memory] Error loading past thoughts: {e}")
        return []

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
    past_thoughts = load_past_thoughts(container, query)

    print(f"[Pixel Hermes] Routing: {query}")
    print("=" * 60)

    response = call_zai(query, past_thoughts)
    print(response)
    print("=" * 60)

    # Save the thought!
    write_thought_to_pixels(container, query, response)

if __name__ == "__main__":
    main()
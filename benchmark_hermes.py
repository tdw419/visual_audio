import time
import subprocess
import os

CONTAINER = "visual_audio.mkv"
BRIDGE_SCRIPT = "pixel_hermes_bridge_context.py"

# A realistic rustc E0412 error
error_prompt = """
Analyze this rustc compilation error and explain it simply:
error[E0412]: cannot find type `Buffer` in this scope
  --> src/content.rs:299:28
   |
299|         _text_buffer: &mut Buffer,
   |                            ^^^^^^ not found in this scope
help: consider importing one of these structs
   |
 1 + use crate::content::wgpu::Buffer;
 1 + use glyphon::Buffer;
 1 + use wgpu::Buffer;
"""

print(f"=== Pixel Hermes Latency Benchmark ===")
print(f"Target Container: {CONTAINER}")
print(f"Payload Size: {len(error_prompt)} chars")
print(f"Starting invocation...")

start_time = time.time()

# Run the bridge exactly as the REPL does
cmd = ["python3", "tools/va_container.py", "run", CONTAINER, BRIDGE_SCRIPT, "--query", error_prompt]

env = os.environ.copy()
env["VA_CONTAINER"] = os.path.abspath(CONTAINER)

result = subprocess.run(cmd, env=env, capture_output=True, text=True)

end_time = time.time()
latency = end_time - start_time

print("\n=== Benchmark Results ===")
print(f"Wall-clock Latency: {latency:.2f} seconds")
print(f"Exit Code: {result.returncode}")

if result.returncode == 0:
    print("\n--- Hermes Response Snippet (First 250 chars) ---")
    print(result.stdout[:250] + "...")
else:
    print("\n--- Error Output ---")
    print(result.stderr)

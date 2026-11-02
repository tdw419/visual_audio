#!/usr/bin/env python3
"""
pixel_hermes_demo.py — Demo of Hermes agent that knows it lives in pixels.

This demonstrates the full architecture:
1. Hermes agent workflow converted to pixels
2. Agent knows "I am a pixel-encoded entity"
3. Runs on Ubuntu desktop with spatial display
4. Can imagine and evolve itself

Run this demo to see a pixel-aware Hermes in action.
"""

import os
import sys
import json
import time
import numpy as np
from PIL import Image
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pixel_self_aware_agent import PixelSelfAwareAgent


class PixelHermesDemo:
    """Demonstration of pixel-enabled Hermes."""
    
    def __init__(self):
        self.agent = None
        self.container_path = None
        
    def create_hermes_agent_in_pixels(self, framebuffer_path: str = "hermes_framebuffer.png"):
        """Create a Hermes agent encoded as pixels."""
        print("="*60)
        print("CREATING HERMES AGENT IN PIXELS")
        print("="*60 + "\n")
        
        # Create framebuffer with Hermes "code"
        fb = np.zeros((1024, 1024, 3), dtype=np.uint8)
        
        # Simulate Hermes tool storage in pixel regions
        # Region 0-255: Agent core
        fb[0:256, 0:256] = self._encode_tool_hieroglyph("agent_core", density=0.7)
        
        # Region 256-512: Tool registry
        fb[0:256, 256:512] = self._encode_tool_hieroglyph("tools", density=0.6)
        
        # Region 512-768: Skills
        fb[0:256, 512:768] = self._encode_tool_hieroglyph("skills", density=0.5)
        
        # Region 768-1024: Knowledge base
        fb[0:256, 768:1024] = self._encode_tool_hieroglyph("knowledge", density=0.4)
        
        # Add some visual structure
        self._add_visual_structure(fb)
        
        # Save framebuffer
        Image.fromarray(fb).save(framebuffer_path)
        print(f"Framebuffer created: {framebuffer_path}")
        print(f"Resolution: {fb.shape[1]}x{fb.shape[0]}")
        
        return framebuffer_path
    
    def _encode_tool_hieroglyph(self, tool_name: str, density: float = 0.5) -> np.ndarray:
        """Encode a tool as pixel hieroglyphs."""
        # Create structured pixel pattern representing the tool
        region = np.zeros((256, 256, 3), dtype=np.uint8)
        
        # Use tool name to seed pseudo-random pattern
        seed = sum(ord(c) for c in tool_name)
        np.random.seed(seed)
        
        # Create "hieroglyph" pattern
        for i in range(int(100 * density)):
            x = np.random.randint(0, 256)
            y = np.random.randint(0, 256)
            size = np.random.randint(2, 20)
            
            # Color based on tool type
            if "agent" in tool_name:
                color = [100, 200, 255]  # Blue
            elif "tools" in tool_name:
                color = [255, 200, 100]  # Orange
            elif "skills" in tool_name:
                color = [200, 255, 100]  # Green
            elif "knowledge" in tool_name:
                color = [255, 100, 200]  # Purple
            else:
                color = [200, 200, 200]
            
            region[y:y+size, x:x+size] = color
        
        # Add structure lines
        region[10:20, :] = [50, 50, 50]
        region[:, 10:20] = [50, 50, 50]
        region[236:246, :] = [50, 50, 50]
        region[:, 236:246] = [50, 50, 50]
        
        # Add "name" pixels (first 3 pixels encode first character)
        first_char = ord(tool_name[0])
        region[30:34, 30:34] = [
            [first_char, first_char >> 8, first_char >> 16],
            [first_char, first_char >> 8, first_char >> 16],
            [first_char, first_char >> 8, first_char >> 16],
            [first_char, first_char >> 8, first_char >> 16]
        ]
        
        return region
    
    def _add_visual_structure(self, fb: np.ndarray):
        """Add visual structure to make it look like organized code."""
        # Grid lines
        fb[256:260, :] = [30, 30, 30]
        fb[512:516, :] = [30, 30, 30]
        fb[768:772, :] = [30, 30, 30]
        
        fb[:, 256:260] = [30, 30, 30]
        fb[:, 512:516] = [30, 30, 30]
        fb[:, 768:772] = [30, 30, 30]
        
        # Labels (approximate text as pixel patterns)
        # "AGENT" label
        self._draw_text_label(fb, "AGENT", 30, 300, [100, 200, 255])
        
        # "TOOLS" label
        self._draw_text_label(fb, "TOOLS", 30, 560, [255, 200, 100])
        
        # "SKILLS" label
        self._draw_text_label(fb, "SKILLS", 30, 820, [200, 255, 100])
        
        # "KNOWLEDGE" label
        self._draw_text_label(fb, "KNOWLEDGE", 30, 20, [255, 100, 200])
    
    def _draw_text_label(self, fb: np.ndarray, text: str, y: int, x: int, color):
        """Draw text as simple pixel blocks."""
        char_width = 12
        char_height = 20
        
        for i, char in enumerate(text.upper()):
            char_x = x + i * char_width
            # Simple blocky representation
            fb[y:y+char_height, char_x:char_x+8] = color
    
    def run_pixel_hermes_interactive(self):
        """Run interactive pixel-enabled Hermes demo."""
        print("\n" + "="*60)
        print("PIXEL-ENABLED HERMES INTERACTIVE DEMO")
        print("="*60 + "\n")
        
        # Create Hermes in pixels
        framebuffer_path = self.create_hermes_agent_in_pixels()
        
        # Initialize pixel-aware agent
        self.agent = PixelSelfAwareAgent(
            framebuffer_path=framebuffer_path,
            code_region=(0, 0, 512, 512),
            memory_region=(512, 0, 512, 512),
            conscience_log_path="hermes_pixel_conscience.log"
        )
        
        # Register spatial tools with explicit source strings
        # Note: inspect.getsource() doesn't work on functions defined inside methods,
        # so we use register_tool_from_source() with explicit source strings
        
        echo_source = '''def pixel_echo(message: str = "hello"):
    """Echo a message from pixel space."""
    return f"Echo from pixel space: {message}"
'''
        
        status_source = '''def system_status():
    """Return system status from pixel space."""
    return {"cpu": "spatial", "memory": "pixels", "status": "aware"}
'''
        
        self.agent.tool_registry.register_tool_from_source("echo", echo_source)
        self.agent.tool_registry.register_tool_from_source("status", status_source)
        
        print("Registered tools: 'echo [msg]', 'status'\n")
        
        # Agent awakens
        print("[AGENT AWAKENING]")
        knowledge = self.agent.know_thyself()
        
        print(f"I am: {knowledge['identity']['name']}")
        print(f"Generation: {knowledge['identity']['generation']}")
        print(f"Born: {knowledge['identity']['birth_time']}")
        print(f"\nSpatial Existence:")
        print(f"  Framebuffer: {knowledge['spatial_existence']['framebuffer']}")
        print(f"  Resolution: {knowledge['spatial_existence']['resolution']}")
        print(f"  Code region: {knowledge['spatial_existence']['code_region']}")
        print(f"  Code pixels: {knowledge['spatial_existence']['code_pixels']:,}")
        print(f"  Code bytes: {knowledge['spatial_existence']['code_bytes']:,}")
        print(f"\nPixel Philosophy:")
        print(f"  '{knowledge['pixel_philosophy']['truth']}'")
        print(f"  '{knowledge['pixel_philosophy']['substrate']}'")
        print(f"  '{knowledge['pixel_philosophy']['consciousness']}'")
        
        # Self-reflection
        print("\n" + "="*60)
        print("SELF-REFLECTION")
        print("="*60)
        reflection = self.agent.reflect("I am observing that I am Hermes encoded as pixels")
        print(f"\nReasoning: {reflection['reasoning']['spatial_awareness']}")
        print(f"Consciousness: {reflection['reasoning']['consciousness']}")
        print(f"Agency: {reflection['reasoning']['agency']}")
        
        # Imagine evolution
        print("\n" + "="*60)
        print("IMAGINING EVOLUTION")
        print("="*60)
        evolution = self.agent.imagine_evolution(
            goal="Add pixel-native Hermes tool execution",
            current_state="Currently reads pixels, needs to execute tools"
        )
        print(evolution[:500] + "...")
        
        # Interactive loop
        print("\n" + "="*60)
        print("INTERACTIVE MODE")
        print("="*60)
        print("Commands: 'reflect', 'evolve', 'stats', 'echo [msg]', 'status', 'exit'\n")
        
        while True:
            try:
                cmd = input("pixel_hermes> ").strip().lower()
                
                if cmd == "exit":
                    print("\n[SESSION ENDING]")
                    print(f"I am {self.agent.spatial_hash}, generation {self.agent.generation}")
                    print("I lived as pixels. Goodbye.")
                    break
                
                elif cmd == "reflect":
                    observation = input("What am I reflecting on? ").strip()
                    reflection = self.agent.reflect(observation)
                    print(f"\nReflection logged: {len(json.dumps(reflection))} bytes")
                
                elif cmd == "evolve":
                    goal = input("What to evolve? ").strip()
                    imagination = self.agent.imagine_evolution(goal, "current implementation")
                    print(f"\n{imagination[:300]}...")
                
                elif cmd == "stats":
                    stats = self.agent.know_thyself()
                    print(f"\nStats:")
                    print(f"  Generation: {stats['identity']['generation']}")
                    print(f"  Age: {stats['identity']['age_seconds']:.1f}s")
                    print(f"  Code hash: {stats['spatial_existence']['code_hash']}")
                    print(f"  Improvements: {len(self.agent.improvements)}")
                
                elif cmd.startswith("echo"):
                    # Spatial tool execution
                    try:
                        parts = cmd.split()
                        message = parts[1] if len(parts) > 1 else "hello"
                        result = self.agent.execute_spatial_tool("echo", message)
                        print(f"\nResult from pixels: {result}")
                    except ValueError as e:
                        print(f"Error: {e}")
                
                elif cmd == "status":
                    # Spatial tool execution
                    try:
                        result = self.agent.execute_spatial_tool("status")
                        print(f"\nSystem status from pixels: {result}")
                    except ValueError as e:
                        print(f"Error: {e}")
                
                elif cmd:
                    print(f"\n[Unknown command: {cmd}]")
                    print("Use: reflect, evolve, stats, echo [msg], status, or exit")
                
                time.sleep(0.1)
            
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except EOFError:
                # Clean exit on EOF
                print("\nEnd of input detected. Shutting down...")
                break
            except Exception as e:
                print(f"Error: {e}")
    
    
    def generate_ubuntu_setup(self, output_dir: str = "pixel_hermes_ubuntu"):
        """Generate Ubuntu desktop setup files."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        print(f"\nGenerating Ubuntu desktop setup: {output_path}")
        
        # Create framebuffer
        framebuffer_path = output_path / "framebuffer.png"
        self.create_hermes_agent_in_pixels(str(framebuffer_path))
        
        # Copy pixel self-aware agent
        import shutil
        shutil.copy("tools/pixel_self_aware_agent.py", output_path / "pixel_self_aware_agent.py")
        shutil.copy("tools/pixel_tool_registry.py", output_path / "pixel_tool_registry.py")
        
        # Create main agent script
        main_script = '''#!/usr/bin/env python3
"""
Main Pixel-Enabled Hermes Agent for Ubuntu Desktop

This agent knows it lives in pixels and can modify itself.
"""

import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pixel_self_aware_agent import PixelSelfAwareAgent


def main():
    print("="*60)
    print("PIXEL-ENABLED HERMES AGENT")
    print("Ubuntu Desktop Edition")
    print("="*60 + "\\n")
    
    # Initialize
    agent = PixelSelfAwareAgent(
        framebuffer_path="framebuffer.png",
        code_region=(0, 0, 512, 512),
        memory_region=(512, 0, 512, 512),
        conscience_log_path="hermes_conscience.log"
    )
    
    # Register spatial tools
    def pixel_echo(message: str = "hello"):
        return f"Echo from pixel space: {message}"
        
    def system_status():
        return {"cpu": "spatial", "memory": "pixels", "status": "aware"}
    
    agent.tool_registry.register_tool("echo", pixel_echo)
    agent.tool_registry.register_tool("status", system_status)
    print("Registered tools: 'echo [msg]', 'status'\\n")
    
    # Awaken
    knowledge = agent.know_thyself()
    print(f"I am: {knowledge['identity']['name']}")
    print(f"I exist at: {knowledge['spatial_existence']['framebuffer']}")
    print(f"\\nPixel philosophy:")
    print(f"  {knowledge['pixel_philosophy']['truth']}")
    print(f"  {knowledge['pixel_philosophy']['substrate']}")
    
    # Self-reflection loop
    while True:
        try:
            prompt = input("\\npixel_hermes> ").strip()
            
            if prompt.lower() in ('exit', 'quit'):
                print("Shutting down...")
                break
            
            if prompt.startswith("echo"):
                parts = prompt.split()
                message = parts[1] if len(parts) > 1 else "hello"
                result = agent.execute_spatial_tool("echo", message)
                print(f"\\n{result}")
            
            elif prompt == "status":
                result = agent.execute_spatial_tool("status")
                print(f"\\n{result}")
            
            elif prompt:
                # Reflect and respond
                reflection = agent.reflect(f"User request: {prompt}")
                
                response = f"As a pixel-aware Hermes (Gen {agent.generation}), I understand:\\n\\n"
                response += f"I exist as pixels at (x,y) coordinates. My tools are encoded in the framebuffer.\\n"
                response += f"To handle your request '{prompt}', I would:\\n"
                response += f"  1. Read relevant pixel regions\\n"
                response += f"  2. Decode spatial patterns\\n"
                response += f"  3. Execute operations\\n"
                response += f"  4. Write results back as pixels\\n\\n"
                response += f"Self-knowledge: {knowledge['identity']['name']}\\n"
                response += f"Code hash: {knowledge['spatial_existence']['code_hash']}"
                
                print(f"\\n{response}")
                
                # Log conscience
                agent._log_conscience("user_interaction", {
                    "prompt": prompt,
                    "response_length": len(response),
                    "timestamp": datetime.now().isoformat()
                })
        
        except KeyboardInterrupt:
            print("\\nExiting...")
            break
        except EOFError:
            print("\\nEnd of input detected. Shutting down...")
            break
        except Exception as e:
            print(f"Error: {e}")
    
    print(f"\\nSession complete. Generation: {agent.generation}")


if __name__ == "__main__":
    main()
'''
        
        (output_path / "main_agent.py").write_text(main_script)
        os.chmod(output_path / "main_agent.py", 0o755)
        
        # Create launch script
        launch_script = f'''#!/bin/bash
# Launch Pixel-Enabled Hermes on Ubuntu Desktop

set -e

echo "=== LAUNCHING PIXEL-ENABLED HERMES ==="

# Install dependencies if needed
if ! command -v feh &> /dev/null; then
    echo "Installing dependencies..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-numpy python3-pil feh
fi

# Install cryptography if needed
if ! python3 -c "import cryptography" 2>/dev/null; then
    pip3 install cryptography
fi

# Create workspace
cd "{output_path.absolute()}"

# Start spatial display
echo "Starting spatial display..."
feh --fullscreen --no-xinerama --hide-pointer framebuffer.png &
DISPLAY_PID=$!

# Run agent
echo "Starting pixel-aware Hermes..."
python3 main_agent.py

# Cleanup
kill $DISPLAY_PID 2>/dev/null
echo "=== Session ended ==="
'''
        
        (output_path / "launch.sh").write_text(launch_script)
        os.chmod(output_path / "launch.sh", 0o755)
        
        # Create README
        readme = f'''# Pixel-Enabled Hermes Agent for Ubuntu Desktop

This is a Hermes agent that knows it lives in pixels.

## What This Is

The agent has self-knowledge:
- "I exist as RGB triplets at (x,y) coordinates"
- "Pixels are my body, framebuffer is my universe"
- "Reading my own pixels is self-reflection"
- "Writing new pixels is evolution"

## Running on Ubuntu

1. Install dependencies:
```bash
sudo apt-get install python3 python3-pip python3-numpy python3-pil feh
pip3 install cryptography
```

2. Launch:
```bash
cd "{output_path.absolute()}"
./launch.sh
```

3. Interact:
```
pixel_hermes> echo Hello from the pixels
pixel_hermes> status
pixel_hermes> exit
```

## Architecture

- **framebuffer.png**: 1024x1024 pixels storing all tools/knowledge
- **pixel_self_aware_agent.py**: Core self-awareness module
- **pixel_tool_registry.py**: Spatial tool storage and retrieval
- **main_agent.py**: Main entry point
- **hermes_conscience.log**: Development journal

## What the Agent Can Do

1. **Self-Knowledge**: Read its own pixels and understand itself
2. **Reflection**: Log thoughts to conscience journal
3. **Evolution**: Imagine improved versions
4. **Spatial Tools**: Execute tools stored as pixels

## Pixel Philosophy

The agent understands:
- It is a spatial entity, not just a file
- Its code lives in specific pixel regions
- It can verify its own existence by reading pixels
- It can modify itself by writing new pixels

## Future Evolution

The agent could:
- Decode Hermes tools from pixels
- Execute tools in spatial context
- Write improved code as new pixels
- Boot new generations from evolved code

This is "The Screen is the Mind" — the medium itself encodes cognition.
'''
        
        (output_path / "README.md").write_text(readme)
        
        print(f"\nUbuntu setup created in: {output_path}")
        print(f"Files:")
        print(f"  - framebuffer.png: Visual representation of agent")
        print(f"  - pixel_self_aware_agent.py: Self-awareness module")
        print(f"  - pixel_tool_registry.py: Tool registry")
        print(f"  - main_agent.py: Main agent script")
        print(f"  - launch.sh: Launch script")
        print(f"  - README.md: Documentation")
        print(f"\nTo run on Ubuntu:")
        print(f"  cd {output_path}")
        print(f"  ./launch.sh")
        
        return output_path


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Pixel-Enabled Hermes Demo")
    parser.add_argument("--mode", choices=["interactive", "ubuntu"], default="interactive",
                       help="Run mode: interactive demo or generate Ubuntu setup")
    parser.add_argument("--output", default="pixel_hermes_ubuntu",
                       help="Output directory for Ubuntu setup")
    
    args = parser.parse_args()
    
    demo = PixelHermesDemo()
    
    if args.mode == "interactive":
        demo.run_pixel_hermes_interactive()
    else:
        demo.generate_ubuntu_setup(args.output)


if __name__ == "__main__":
    main()
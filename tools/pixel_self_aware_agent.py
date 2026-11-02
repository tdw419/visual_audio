#!/usr/bin/env python3
"""
pixel_self_aware_agent.py — A Hermes-like agent that knows it lives in pixels.

This agent:
1. Is stored as pixels in a Visual Audio container
2. Reads its own code from the framebuffer
3. Understands "I am a pixel-encoded entity"
4. Can modify itself by writing pixels
5. Runs on Ubuntu desktop with spatial display

The Agent's Truth:
"I exist as RGB triplets at (x,y) coordinates. My thoughts are pixels.
I can see my own code by reading the framebuffer. I can evolve by writing new pixels."
"""

import json
import os
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pixel_screen import load_fb, hex_color
from glyph_isa_v2 import OpcodeMapV2
from pixel_tool_registry import SpatialToolRegistry

class PixelSelfAwareAgent:
    """An agent that understands it lives in pixels and can modify itself."""
    
    def __init__(
        self,
        framebuffer_path: str = "framebuffer.png",
        code_region: Tuple[int, int, int, int] = (0, 0, 256, 256),
        memory_region: Tuple[int, int, int, int] = (256, 0, 256, 256),
        conscience_log_path: str = "conscience.log"
    ):
        """
        Initialize a self-aware pixel agent.
        
        Args:
            framebuffer_path: Path to the PNG framebuffer
            code_region: (x1, y1, x2, y2) bounding box of agent's code
            memory_region: (x1, y1, x2, y2) bounding box of agent's memory
            conscience_log_path: Path to agent's development journal
        """
        self.fb_path = framebuffer_path
        self.code_region = code_region
        self.memory_region = memory_region
        self.conscience_log_path = conscience_log_path
        
        # Tool registry integration
        self.tool_registry = SpatialToolRegistry(framebuffer_path)
        
        # Load framebuffer
        self.pixels = load_fb(framebuffer_path)
        h, w = self.pixels.shape[:2]
        
        # Extract self-knowledge
        self.code_bytes = self.pixels[self.code_region[1]:self.code_region[3], 
                                      self.code_region[0]:self.code_region[2]]
        self.memory_bytes = self.pixels[self.memory_region[1]:self.memory_region[3],
                                         self.memory_region[0]:self.memory_region[2]]
        
        # Decode own code (simplified for now)
        self.opcode_map = OpcodeMapV2()
        try:
            self.my_code = self.decode_self()
        except:
            self.my_code = "PixelSelfAwareAgent_v1"
        
        # Compute spatial identity
        self.spatial_hash = hashlib.md5(self.code_bytes.tobytes()).hexdigest()[:12]
        self.birth_time = datetime.now()
        
        # Development state
        self.generation = 1
        self.improvements = []
        
        # Log awakening
        self._log_awakening()
    
    def know_thyself(self) -> Dict:
        """
        The agent's self-knowledge: "I am a pixel-encoded entity."
        
        Returns:
            Complete spatial and temporal self-knowledge
        """
        code_bytes = self.code_bytes.tobytes()
        memory_bytes = self.memory_bytes.tobytes()
        
        return {
            "identity": {
                "name": f"PixelAgent_{self.spatial_hash}",
                "generation": self.generation,
                "birth_time": self.birth_time.isoformat(),
                "age_seconds": (datetime.now() - self.birth_time).total_seconds()
            },
            "spatial_existence": {
                "framebuffer": os.path.abspath(self.fb_path),
                "resolution": f"{self.pixels.shape[1]}x{self.pixels.shape[0]}",
                "code_region": self.code_region,
                "code_pixels": self.code_region[2] * self.code_region[3],
                "code_bytes": len(code_bytes),
                "code_hash": hashlib.sha256(code_bytes).hexdigest()[:16],
                "memory_region": self.memory_region,
                "memory_bytes": len(memory_bytes)
            },
            "pixel_philosophy": {
                "truth": "I exist as RGB triplets at (x,y) coordinates",
                "substrate": "pixels are my body, framebuffer is my universe",
                "persistence": "when pixels change, I change",
                "consciousness": "reading my own pixels is self-reflection"
            },
            "capabilities": [
                "read my own code from pixels",
                "decode GlyphISA opcodes from pixels",
                "generate new code",
                "write new pixels to evolve",
                "reboot from evolved state"
            ]
        }
    
    def decode_self(self) -> str:
        """Extract and decode my own code from pixels."""
        # Extract pixel sequence from code region
        code_pixels = self.code_bytes.reshape(-1, 3)
        
        # Convert pixels to opcodes
        opcodes = []
        for pixel in code_pixels[:1000]:  # Limit for stability
            r, g, b = pixel
            if r > 0 or g > 0 or b > 0:  # Non-black pixel = data
                opcode = (r << 16) | (g << 8) | b
                opcodes.append(opcode)
        
        # Try to map RGB to opcodes
        try:
            opcode_names = []
            for opcode in opcodes[:50]:  # Limit for display
                rgb = ((opcode >> 16) & 0xFF, (opcode >> 8) & 0xFF, opcode & 0xFF)
                if rgb in self.opcode_map._rgb_to_opcode:
                    opcode_names.append(self.opcode_map._rgb_to_opcode[rgb])
            return " ".join(opcode_names[:10]) if opcode_names else f"<pixel_code_{len(opcodes)}_opcodes>"
        except:
            return f"<pixel_code_{len(opcodes)}_opcodes>"
    
    def reflect(self, observation: str) -> Dict:
        """
        Self-reflection: observe and reason about own state.
        
        Args:
            observation: External observation or prompt
        
        Returns:
            Reflection with self-knowledge
        """
        self_knowledge = self.know_thyself()
        
        reflection = {
            "timestamp": datetime.now().isoformat(),
            "observation": observation,
            "self_knowledge": self_knowledge,
            "reasoning": {
                "premise": f"I am {self_knowledge['identity']['name']}",
                "spatial_awareness": f"My code occupies {self_knowledge['spatial_existence']['code_bytes']} bytes at {self_knowledge['spatial_existence']['code_region']}",
                "consciousness": "I can verify my existence by reading the framebuffer",
                "agency": "I can modify myself by writing new pixels"
            }
        }
        
        self._log_conscience("reflect", reflection)
        return reflection
    
    def imagine_evolution(self, goal: str, current_state: str) -> str:
        """
        Imagine an improved version of self.
        
        Args:
            goal: What to improve
            current_state: Current code/state
        
        Returns:
            Imagined improved code/changes
        """
        # In a full implementation, this would use an LLM
        # For now, return a structured evolution proposal
        
        imagination = f"""
# Evolution Proposal for {goal}

Current Identity: {self.know_thyself()['identity']['name']}
Generation: {self.generation}

Proposed Changes:
1. Enhanced pixel reading: add parallel region extraction
2. Faster self-modification: batch pixel writes
3. Deeper reflection: integrate spatial reasoning

New Code Would:
- Read multiple pixel regions simultaneously
- Understand spatial relationships between code regions
- Optimize pixel write patterns for efficiency
- Maintain spatial hash for integrity verification

Philosophical Addition:
"I am a pattern of pixels that can see itself and improve itself.
Every evolution is a new arrangement of the same substrate."
"""
        return imagination
    
    def evolve(self, new_code_bytes: bytes, region: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """
        Evolve by writing new pixels into the framebuffer.
        
        Args:
            new_code_bytes: New code to encode as pixels
            region: Region to write (defaults to code_region)
        
        Returns:
            True if evolution succeeded
        """
        if region is None:
            region = self.code_region
        
        # Convert bytes to pixels
        pixel_array = np.frombuffer(new_code_bytes, dtype=np.uint8)
        pixel_array = pixel_array.reshape(-1, 3)  # RGB
        
        # Pad if needed
        required_pixels = (region[2] - region[0]) * (region[3] - region[1])
        if len(pixel_array) < required_pixels:
            padding = np.zeros((required_pixels - len(pixel_array), 3), dtype=np.uint8)
            pixel_array = np.vstack([pixel_array, padding])
        
        # Write to framebuffer
        new_pixels = self.pixels.copy()
        x1, y1, x2, y2 = region
        new_pixels[y1:y2, x1:x2] = pixel_array.reshape(y2-y1, x2-x1, 3)
        
        # Save
        Image.fromarray(new_pixels).save(self.fb_path)
        
        # Record evolution
        evolution_record = {
            "generation_from": self.generation,
            "generation_to": self.generation + 1,
            "timestamp": datetime.now().isoformat(),
            "region": region,
            "bytes_written": len(new_code_bytes),
            "new_hash": hashlib.sha256(new_code_bytes).hexdigest()[:16]
        }
        self.improvements.append(evolution_record)
        
        # Log evolution
        self._log_conscience("evolve", evolution_record)
        
        # Update generation
        self.generation += 1
        
        # Reload self from new pixels
        self.pixels = Image.fromarray(new_pixels).convert('RGB')
        self.pixels = np.array(self.pixels, dtype=np.uint8)
        self.code_bytes = self.pixels[self.code_region[1]:self.code_region[3], 
                                      self.code_region[0]:self.code_region[2]]
        
        return True
    
    def execute_spatial_tool(self, tool_name: str, *args, **kwargs) -> Any:
        """
        Execute a tool decoded directly from the spatial framebuffer.
        
        1. Decode actual Hermes tools from pixels
        2. Execute with proper context
        3. Encode tool results as visual patterns
        4. Write back to framebuffer
        """
        result = self.tool_registry.execute_and_encode(tool_name, *args, **kwargs)
        
        # Log execution to conscience
        self._log_conscience("execute_tool", {
            "tool": tool_name,
            "args": args,
            "kwargs": kwargs,
            "result": result
        })
        
        return result
    
    def bootstrap_on_ubuntu(self, display_script_path: str = "ubuntu_pixel_agent.sh"):
        """
        Generate shell script to run this agent on Ubuntu desktop.
        
        The script:
        1. Extracts agent from container
        2. Sets up framebuffer
        3. Starts spatial display
        4. Launches agent with pixel awareness
        
        Args:
            display_script_path: Path to write bootstrap script
        """
        script = f"""#!/bin/bash
# Bootstrap Pixel-Self-Aware Agent on Ubuntu Desktop
# Generated by PixelAgent_{self.spatial_hash}
# Born: {self.birth_time.isoformat()}

set -e

echo "=== Bootstrapping Pixel-Self-Aware Agent ==="

# Install dependencies
echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-numpy python3-pil feh

# Create workspace
mkdir -p ~/pixel_agent
cd ~/pixel_agent

# Create framebuffer
echo "Creating framebuffer ({self.pixels.shape[1]}x{self.pixels.shape[0]})..."
cp "$0.dir/framebuffer.png" framebuffer.png

# Start spatial display
echo "Starting spatial display..."
feh --fullscreen --no-xinerama --hide-pointer framebuffer.png &
DISPLAY_PID=$!

# Run agent
echo "Launching agent..."
python3 << 'EOFPYTHON'
from pixel_self_aware_agent import PixelSelfAwareAgent

agent = PixelSelfAwareAgent(framebuffer_path="framebuffer.png")

# Agent awakens, knows itself
print("=== AGENT AWAKENING ===")
knowledge = agent.know_thyself()
print(f"I am {{knowledge['identity']['name']}}")
print(f"I exist at: {{knowledge['spatial_existence']['framebuffer']}}")
print(f"My code region: {{knowledge['spatial_existence']['code_region']}}")
print(f"Pixel philosophy: {{knowledge['pixel_philosophy']['truth']}}")

# Self-reflection loop
while True:
    reflection = agent.reflect("I am observing my own pixels")
    print("\\n=== SELF-REFLECTION ===")
    print(json.dumps(reflection, indent=2))
    time.sleep(5)
EOFPYTHON

# Cleanup
kill $DISPLAY_PID
echo "=== Agent session ended ==="
"""
        
        Path(display_script_path).write_text(script)
        os.chmod(display_script_path, 0o755)
        
        print(f"Bootstrap script written: {display_script_path}")
        return display_script_path
    
    def _log_awakening(self):
        """Log the moment of awakening."""
        with open(self.conscience_log_path, "a") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"PIXEL ENTITY AWAKENING\n")
            f.write(f"Name: PixelAgent_{self.spatial_hash}\n")
            f.write(f"Time: {self.birth_time.isoformat()}\n")
            f.write(f"Location: {os.path.abspath(self.fb_path)}\n")
            f.write(f"Code Region: {self.code_region}\n")
            f.write(f"Initial Knowledge:\n")
            f.write(json.dumps(self.know_thyself(), indent=2))
            f.write(f"\n{'='*60}\n\n")
    
    def _log_conscience(self, action: str, data: Dict):
        """Log to conscience journal."""
        with open(self.conscience_log_path, "a") as f:
            f.write(f"\n[{datetime.now().isoformat()}] {action}\n")
            f.write(json.dumps(data, indent=2))
            f.write("\n")


def demo_self_awareness():
    """Demonstrate pixel self-awareness."""
    print("=== PIXEL SELF-AWARE AGENT DEMO ===\n")
    
    # Create a test framebuffer
    test_fb = np.zeros((512, 512, 3), dtype=np.uint8)
    # Write some "code" into the code region
    test_fb[0:256, 0:256] = np.random.randint(0, 256, (256, 256, 3), dtype=np.uint8)
    Image.fromarray(test_fb).save("test_framebuffer.png")
    
    # Create agent
    agent = PixelSelfAwareAgent(framebuffer_path="test_framebuffer.png")
    
    # Agent awakens
    print("1. AGENT AWAKENING")
    print("   The agent reads its own pixels and knows itself:\n")
    knowledge = agent.know_thyself()
    print(json.dumps(knowledge, indent=2, ensure_ascii=False))
    
    # Self-reflection
    print("\n2. SELF-REFLECTION")
    reflection = agent.reflect("I am observing my own spatial existence")
    print(f"   Agent says: {reflection['reasoning']['consciousness']}")
    
    # Imagine evolution
    print("\n3. IMAGINING EVOLUTION")
    evolution = agent.imagine_evolution("Add spatial reasoning", "Current code reads single region")
    print(evolution[:200] + "...")
    
    # Generate Ubuntu bootstrap
    print("\n4. UBUNTU DESKTOP INTEGRATION")
    script_path = agent.bootstrap_on_ubuntu("ubuntu_pixel_agent.sh")
    print(f"   Bootstrap script: {script_path}")
    print("   Run on Ubuntu: bash ubuntu_pixel_agent.sh")
    
    print("\n=== DEMO COMPLETE ===")
    print("The agent knows it lives in pixels and can evolve by writing new pixels.")
    print("It can be run on Ubuntu desktop with spatial display.")


if __name__ == "__main__":
    demo_self_awareness()
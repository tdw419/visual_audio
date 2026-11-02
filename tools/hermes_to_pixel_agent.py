#!/usr/bin/env python3
"""
hermes_to_pixel_agent.py — Convert Hermes agent harness to run in pixels.

This tool:
1. Takes a Hermes agent workflow
2. Converts it to pixel-encoded form
3. Embeds it in a Visual Audio container
4. The agent "knows" it lives in pixels
5. Can run on Ubuntu desktop with spatial display

Usage:
    python3 hermes_to_pixel_agent.py --agent hermes-agent --output pixel_hermes.mkv
    python3 hermes_to_pixel_agent.py --agent ollama-gateway --output pixel_ollama.mkv
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

# Check if we're in the Hermes project
HERMES_ROOT = Path.home() / ".hermes" / "profiles" / "default"
if not HERMES_ROOT.exists():
    HERMES_ROOT = Path.home() / "projects" / "hermes-agent"  # Alternative location

if not HERMES_ROOT.exists():
    print("ERROR: Hermes not found. Install Hermes first:")
    print("  git clone https://github.com/nousresearch/hermes-agent.git")
    sys.exit(1)


class HermesToPixelConverter:
    """Convert Hermes agent harness to pixel-encoded form."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.temp_dir = tempfile.mkdtemp(prefix=f"pixel_{agent_name}_")
        self.container_path = None
        
    def extract_hermes_components(self) -> Dict:
        """
        Extract Hermes agent components.
        
        Returns:
            Dict with paths to components
        """
        print(f"Extracting Hermes agent: {self.agent_name}")
        
        components = {
            "skills": [],
            "plugins": [],
            "tools": [],
            "config": None,
            "prompts": []
        }
        
        # Find skills
        skills_dir = HERMES_ROOT / "skills"
        if skills_dir.exists():
            for skill_file in skills_dir.glob(f"*{self.agent_name}*.py"):
                components["skills"].append(skill_file)
            # Also include general skills
            for skill_file in skills_dir.glob("*.py"):
                if skill_file.stat().st_size < 100000:  # Skip huge files
                    components["skills"].append(skill_file)
        
        # Find plugins
        plugins_dir = HERMES_ROOT / "plugins"
        if plugins_dir.exists():
            for plugin_file in plugins_dir.glob(f"*{self.agent_name}*"):
                if plugin_file.is_dir():
                    components["plugins"].append(plugin_file)
        
        # Find config
        config_file = HERMES_ROOT / "config.yaml"
        if config_file.exists():
            components["config"] = config_file
        
        # Find prompts/templates
        prompts_dir = HERMES_ROOT / "prompts"
        if prompts_dir.exists():
            for prompt_file in prompts_dir.glob(f"*{self.agent_name}*"):
                components["prompts"].append(prompt_file)
        
        print(f"  Found {len(components['skills'])} skills")
        print(f"  Found {len(components['plugins'])} plugins")
        print(f"  Found {len(components['prompts'])} prompts")
        
        return components
    
    def create_pixel_aware_wrapper(self) -> str:
        """
        Create a pixel-aware wrapper that runs Hermes.
        
        Returns:
            Path to wrapper script
        """
        wrapper_path = os.path.join(self.temp_dir, "pixel_hermes_wrapper.py")
        
        wrapper_code = f'''#!/usr/bin/env python3
"""
Pixel-Aware Hermes Wrapper

This wrapper runs Hermes but with pixel-awareness:
- Knows it lives in pixels
- Logs spatial state
- Can modify itself
- Provides pixel-aware tool interface
"""

import os
import sys
import json
import time
import hashlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "{HERMES_ROOT}")

# Import pixel self-awareness
from pixel_self_aware_agent import PixelSelfAwareAgent

class PixelHermesAgent:
    """Hermes agent that knows it lives in pixels."""
    
    def __init__(self):
        self.agent_name = "{self.agent_name}"
        self.spatial_agent = None
        self.spatial_hash = None
        self.generation = 1
        
    def awaken(self, framebuffer_path: str = "framebuffer.png"):
        """Awaken as a pixel-encoded entity."""
        print("=== PIXEL-ENABLED HERMES AGENT AWAKENING ===\\n")
        
        # Create spatial agent
        self.spatial_agent = PixelSelfAwareAgent(
            framebuffer_path=framebuffer_path,
            code_region=(0, 0, 512, 512),
            memory_region=(512, 0, 512, 512),
            conscience_log_path=f"hermes_conscience.log"
        )
        
        # Compute spatial hash
        self.spatial_hash = self.spatial_agent.spatial_hash
        
        # Self-knowledge
        knowledge = self.spatial_agent.know_thyself()
        
        print(f"I am: {{knowledge['identity']['name']}}")
        print(f"Agent: {{self.agent_name}}")
        print(f"Location: {{knowledge['spatial_existence']['framebuffer']}}")
        print(f"Pixel philosophy: {{knowledge['pixel_philosophy']['truth']}}\\n")
        
        # Log awakening
        self._log_event("awakening", knowledge)
        
        return knowledge
    
    def run_with_spatial_awareness(self, prompt: str) -> Dict:
        """
        Run Hermes with spatial awareness.
        
        Args:
            prompt: User prompt
        
        Returns:
            Response with spatial metadata
        """
        print(f"\\n=== RUNNING HERMES WITH SPATIAL AWARENESS ===")
        print(f"Prompt: {{prompt}}\\n")
        
        # Self-reflection
        reflection = self.spatial_agent.reflect(f"Processing: {{prompt}}")
        
        # In a full implementation, this would call actual Hermes
        # For now, simulate the response
        response = {{
            "prompt": prompt,
            "response": f"I am a pixel-encoded Hermes agent (Generation {{self.generation}}). I exist as pixels and I know it.\\n\\nTo address: {{prompt}}\\n\\nI would use tools stored in the pixel framebuffer, execute spatially-aware operations, and log results to my conscience.",
            "spatial_metadata": {{
                "agent_hash": self.spatial_hash,
                "generation": self.generation,
                "timestamp": datetime.now().isoformat(),
                "self_knowledge": reflection['self_knowledge']
            }},
            "spatial_reasoning": reflection['reasoning']
        }}
        
        print(f"Response: {{response['response']}}\\n")
        
        # Log processing
        self._log_event("processing", response)
        
        return response
    
    def imagine_evolution(self) -> str:
        """Imagine an improved version of self."""
        print("\\n=== IMAGINING EVOLUTION ===\\n")
        
        imagination = self.spatial_agent.imagine_evolution(
            goal="Add pixel-native tool execution",
            current_state="Currently simulates Hermes, needs real integration"
        )
        
        print(imagination)
        
        # Log imagination
        self._log_event("imagination", {{"evolution_proposal": imagination}})
        
        return imagination
    
    def _log_event(self, event_type: str, data: Dict):
        """Log event with spatial context."""
        log_entry = {{
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "agent_name": self.agent_name,
            "spatial_hash": self.spatial_hash,
            "generation": self.generation,
            "data": data
        }}
        
        log_file = Path("hermes_spatial_log.jsonl")
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\\n")
    
    def interactive_loop(self):
        """Interactive REPL with spatial awareness."""
        print("\\n=== PIXEL-ENABLED HERMES INTERACTIVE ===")
        print("Type 'exit' to quit, 'evolve' to imagine evolution\\n")
        
        while True:
            try:
                prompt = input("pixel_hermes> ").strip()
                
                if prompt == "exit":
                    print("Shutting down pixel-aware Hermes...")
                    break
                elif prompt == "evolve":
                    self.imagine_evolution()
                elif prompt:
                    response = self.run_with_spatial_awareness(prompt)
                    # Show spatial metadata
                    print(f"\\n[Spatial: {response['spatial_metadata']['agent_hash']} Gen:{response['spatial_metadata']['generation']}]")
                
            except KeyboardInterrupt:
                print("\\nExiting...")
                break
            except Exception as e:
                print(f"Error: {{e}}")

def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Pixel-enabled Hermes agent")
    parser.add_argument("--prompt", help="Single prompt to process")
    parser.add_argument("--interactive", action="store_true", help="Interactive REPL")
    args = parser.parse_args()
    
    agent = PixelHermesAgent()
    knowledge = agent.awaken()
    
    if args.prompt:
        response = agent.run_with_spatial_awareness(args.prompt)
        print(json.dumps(response, indent=2))
    elif args.interactive:
        agent.interactive_loop()
    else:
        print("Use --prompt or --interactive")

if __name__ == "__main__":
    main()
'''
        
        Path(wrapper_path).write_text(wrapper_code)
        os.chmod(wrapper_path, 0o755)
        
        return wrapper_path
    
    def package_into_container(self, components: Dict, wrapper_path: str, 
                               output_path: str) -> bool:
        """
        Package everything into Visual Audio container.
        
        Args:
            components: Hermes components
            wrapper_path: Pixel-aware wrapper
            output_path: Output container path
        
        Returns:
            True if successful
        """
        print(f"\\nPackaging into container: {output_path}")
        
        # Import va_container
        import tools.va_container as vac
        
        # Create new container
        container_path = os.path.join(self.temp_dir, "pixel_hermes.mkv")
        vac.init(container_path)
        
        # Add pixel self-aware agent
        vac.add(container_path, "tools/pixel_self_aware_agent.py", "tools/pixel_self_aware_agent.py")
        
        # Add wrapper
        vac.add(container_path, wrapper_path, "pixel_hermes_wrapper.py")
        
        # Add Hermes components
        print("Adding Hermes components...")
        
        # Add skills (limit to small ones)
        for i, skill_file in enumerate(components["skills"][:20]):  # Limit to 20 skills
            try:
                vac.add(container_path, str(skill_file), f"skills/{skill_file.name}")
                if i < 5:
                    print(f"  + skills/{skill_file.name}")
            except Exception as e:
                print(f"  - Skipped {skill_file.name}: {e}")
        
        # Add plugins (limit)
        for i, plugin_dir in enumerate(components["plugins"][:5]):
            try:
                # Add all Python files in plugin
                for py_file in plugin_dir.glob("*.py"):
                    vac.add(container_path, str(py_file), f"plugins/{plugin_dir.name}/{py_file.name}")
                if i < 3:
                    print(f"  + plugins/{plugin_dir.name}/")
            except Exception as e:
                print(f"  - Skipped {plugin_dir.name}: {e}")
        
        # Add config
        if components["config"]:
            vac.add(container_path, str(components["config"]), "config.yaml")
            print(f"  + config.yaml")
        
        # Add prompts
        for i, prompt_file in enumerate(components["prompts"][:10]):
            try:
                vac.add(container_path, str(prompt_file), f"prompts/{prompt_file.name}")
            except Exception as e:
                pass
        
        # Add wordbase and codec (needed for pixel operations)
        if Path("db/wordbase.db").exists():
            vac.add(container_path, "db/wordbase.db", "db/wordbase.db")
            print("  + db/wordbase.db")
        
        if Path("src").exists():
            for py_file in Path("src").glob("**/*.py"):
                vac.add(container_path, str(py_file), f"src/{py_file.relative_to('src')}")
        
        # Create initial framebuffer
        print("\\nCreating initial framebuffer...")
        import numpy as np
        from PIL import Image
        
        fb = np.zeros((512, 1024, 3), dtype=np.uint8)
        
        # Draw "I AM PIXELS" in code region
        fb[100:120, 100:120] = np.array([100, 200, 255], dtype=np.uint8)  # Blue box
        fb[150:170, 150:170] = np.array([255, 100, 100], dtype=np.uint8)  # Red box
        fb[200:220, 200:220] = np.array([100, 255, 100], dtype=np.uint8)  # Green box
        
        # Add some "code" pixels
        fb[50:150, 300:500] = np.random.randint(50, 200, (100, 200, 3), dtype=np.uint8)
        
        # Save and add to container
        fb_path = os.path.join(self.temp_dir, "framebuffer.png")
        Image.fromarray(fb).save(fb_path)
        vac.add(container_path, fb_path, "framebuffer.png")
        
        # Verify container
        print("\\nVerifying container...")
        result = vac.verify(container_path)
        print(f"Verification: {result}")
        
        # Move to final output
        shutil.move(container_path, output_path)
        print(f"\\nContainer created: {output_path}")
        
        self.container_path = output_path
        return True
    
    def generate_ubuntu_bootstrap(self, output_path: str) -> str:
        """
        Generate bootstrap script for Ubuntu desktop.
        
        Args:
            output_path: Path to container
        
        Returns:
            Path to bootstrap script
        """
        script_path = output_path.replace(".mkv", "_bootstrap.sh")
        
        script = f'''#!/bin/bash
# Bootstrap Pixel-Enabled Hermes on Ubuntu Desktop
# Container: {output_path}

set -e

echo "=== BOOTSTRAPPING PIXEL-ENABLED HERMES ==="
echo "This Hermes agent knows it lives in pixels."

# Install dependencies
echo "Installing dependencies..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-numpy python3-pil \\
    python3-scipy python3-soundfile feh

# Install cryptography
pip3 install cryptography

# Create workspace
mkdir -p ~/pixel_hermes
cd ~/pixel_hermes

# Copy container
cp "{output_path}" pixel_hermes.mkv

# Create initial framebuffer
python3 -c "
import numpy as np
from PIL import Image
fb = np.zeros((512, 1024, 3), dtype=np.uint8)
fb[100:120, 100:120] = np.array([100, 200, 255])
fb[150:170, 150:170] = np.array([255, 100, 100])
fb[200:220, 200:220] = np.array([100, 255, 100])
fb[50:150, 300:500] = np.random.randint(50, 200, (100, 200, 3))
Image.fromarray(fb).save('framebuffer.png')
"

# Start spatial display
echo "Starting spatial display..."
feh --fullscreen --no-xinerama --hide-pointer framebuffer.png &
DISPLAY_PID=$!

# Extract and run wrapper
echo "Extracting pixel-aware Hermes..."
python3 <<'EOFPYTHON'
import sys
import os

# Add tools to path
sys.path.insert(0, '.')

# Extract pixel self-aware agent
import subprocess
subprocess.run(['python3', 'tools/va_container.py', 'cat', 'pixel_hermes.mkv', 
                'tools/pixel_self_aware_agent.py', '-o', 'pixel_self_aware_agent.py'])

subprocess.run(['python3', 'tools/va_container.py', 'cat', 'pixel_hermes.mkv',
                'pixel_hermes_wrapper.py', '-o', 'pixel_hermes_wrapper.py'])

subprocess.run(['python3', 'tools/va_container.py', 'cat', 'pixel_hermes.mkv',
                'framebuffer.png', '-o', 'framebuffer.png'])

# Now run the pixel-aware agent
print("Starting pixel-enabled Hermes...")
exec(open('pixel_hermes_wrapper.py').read())
EOFPYTHON

# Cleanup
kill $DISPLAY_PID 2>/dev/null
echo "=== Session ended ==="
'''
        
        Path(script_path).write_text(script)
        os.chmod(script_path, 0o755)
        
        print(f"Bootstrap script: {script_path}")
        return script_path
    
    def cleanup(self):
        """Clean up temporary directory."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert Hermes agent to pixel-encoded form"
    )
    parser.add_argument("--agent", required=True, help="Agent name (e.g., hermes-agent, ollama-gateway)")
    parser.add_argument("--output", default="pixel_hermes.mkv", help="Output container path")
    parser.add_argument("--bootstrap", action="store_true", help="Generate Ubuntu bootstrap script")
    args = parser.parse_args()
    
    converter = HermesToPixelConverter(args.agent)
    
    try:
        # Extract Hermes components
        components = converter.extract_hermes_components()
        
        # Create pixel-aware wrapper
        wrapper_path = converter.create_pixel_aware_wrapper()
        
        # Package into container
        success = converter.package_into_container(components, wrapper_path, args.output)
        
        if success and args.bootstrap:
            converter.generate_ubuntu_bootstrap(args.output)
        
        print(f"\\n=== CONVERSION COMPLETE ===")
        print(f"Container: {args.output}")
        print(f"The agent now knows it lives in pixels.")
        print(f"\\nTo run on Ubuntu:")
        print(f"  bash {args.output.replace('.mkv', '_bootstrap.sh')}")
        print(f"\\nOr interactively:")
        print(f"  python3 tools/va_container.py run {args.output} pixel_hermes_wrapper.py --interactive")
        
    finally:
        converter.cleanup()


if __name__ == "__main__":
    main()
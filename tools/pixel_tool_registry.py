import os
import inspect
import json
import hashlib
from typing import Dict, Any, Callable, Tuple
import numpy as np
from PIL import Image

from pixel_screen import load_fb

class SpatialToolRegistry:
    """Stores and retrieves Python tools from pixel regions."""
    
    def __init__(self, framebuffer_path: str, region: Tuple[int, int, int, int] = (256, 0, 512, 256)):
        self.fb_path = framebuffer_path
        self.region = region # x1, y1, x2, y2
        self.tools = {}
        self.results_region = (0, 768, 1024, 1024) # Bottom part for results
        
    def _encode_bytes_to_pixels(self, data: bytes, target_region: Tuple[int, int, int, int]) -> np.ndarray:
        """Encode bytes into RGB pixel array matching region shape."""
        x1, y1, x2, y2 = target_region
        w = x2 - x1
        h = y2 - y1
        max_bytes = w * h * 3
        
        if len(data) > max_bytes:
            raise ValueError(f"Data too large for region ({len(data)} > {max_bytes})")
            
        # Pad data
        padded_data = data + b'\x00' * (max_bytes - len(data))
        pixels = np.frombuffer(padded_data, dtype=np.uint8).reshape((h, w, 3))
        return pixels
        
    def _decode_pixels_to_bytes(self, pixels: np.ndarray) -> bytes:
        """Decode RGB pixel array back to bytes, stripping padding."""
        data = pixels.tobytes()
        return data.rstrip(b'\x00')

    def register_tool_from_source(self, name: str, source: str):
        """Register a tool from source string and save it as pixels in the framebuffer."""
        meta = {
            "name": name,
            "hash": hashlib.sha256(source.encode()).hexdigest(),
            "source": source
        }
        self.tools[name] = meta
        self._sync_to_pixels()
        print(f"Registered tool '{name}' as spatial pixels.")

    def register_tool(self, name: str, func: Callable):
        """Register a tool and save it as pixels in the framebuffer."""
        try:
            source = inspect.getsource(func)
            self.register_tool_from_source(name, source)
        except OSError:
            # inspect.getsource() fails for dynamically created functions
            # Fall back to registering from source string
            raise ValueError(f"Cannot get source for '{name}'. Use register_tool_from_source() with explicit source string.")

    def _sync_to_pixels(self):
        """Write all registered tools to the framebuffer region."""
        fb = load_fb(self.fb_path)
        data_json = json.dumps(self.tools).encode('utf-8')
        tool_pixels = self._encode_bytes_to_pixels(data_json, self.region)
        
        x1, y1, x2, y2 = self.region
        fb[y1:y2, x1:x2] = tool_pixels
        Image.fromarray(fb).save(self.fb_path)

    def _sync_from_pixels(self):
        """Read tools from the framebuffer region."""
        fb = load_fb(self.fb_path)
        x1, y1, x2, y2 = self.region
        tool_pixels = fb[y1:y2, x1:x2]
        data_bytes = self._decode_pixels_to_bytes(tool_pixels)
        
        if data_bytes:
            try:
                self.tools = json.loads(data_bytes.decode('utf-8'))
            except json.JSONDecodeError:
                pass

    def get_tool(self, name: str) -> Callable:
        """Retrieve and compile a tool from pixels."""
        self._sync_from_pixels()
        if name not in self.tools:
            raise ValueError(f"Tool {name} not found in spatial registry")
            
        source = self.tools[name]["source"]
        
        # Create a clean namespace for exec
        tool_namespace = {}
        
        # Execute the source code
        try:
            exec(source, tool_namespace, tool_namespace)
        except Exception as e:
            raise RuntimeError(f"Failed to compile tool '{name}': {e}")
        
        # Extract the function - the source defines specific function names
        # For 'echo', we look for 'pixel_echo', for 'status', we look for 'system_status'
        tool_name_mapping = {
            "echo": "pixel_echo",
            "status": "system_status"
        }
        
        actual_name = tool_name_mapping.get(name, name)
        
        if actual_name in tool_namespace and callable(tool_namespace[actual_name]):
            return tool_namespace[actual_name]
        
        # Fallback to any callable
        for item in tool_namespace.values():
            if callable(item) and not item.__name__.startswith('_'):
                return item
                
        raise ValueError(f"Function '{actual_name}' not found in decoded source. Available: {list(tool_namespace.keys())}")

    def execute_and_encode(self, tool_name: str, *args, **kwargs) -> Any:
        """Execute a tool retrieved from pixels, and write result to pixels."""
        func = self.get_tool(tool_name)
        print(f"[Spatial Execution] Running tool '{tool_name}'...")
        result = func(*args, **kwargs)
        
        # Encode result
        result_json = json.dumps({"tool": tool_name, "result": result}).encode('utf-8')
        fb = load_fb(self.fb_path)
        result_pixels = self._encode_bytes_to_pixels(result_json, self.results_region)
        
        x1, y1, x2, y2 = self.results_region
        fb[y1:y2, x1:x2] = result_pixels
        Image.fromarray(fb).save(self.fb_path)
        
        print(f"[Spatial Execution] Result of '{tool_name}' written to results region.")
        
        return result

    def list_tools(self) -> list:
        """List all registered tools."""
        self._sync_from_pixels()
        return list(self.tools.keys())
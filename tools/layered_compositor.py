#!/usr/bin/env python3
"""
Layered Frame Compositor — Photoshop-style frame composition

Enables AI vision to scope to individual layers within a shared pixel space.
Layers can be composed with various blend modes, alpha blending, and masking.

Architecture:
  Layer → named buffer with blend mode, opacity, mask
  Composition → Z-ordered layers merged to output frame
  Read → extract individual layer for vision analysis
  Blend modes → normal, multiply, screen, overlay, difference, etc.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class BlendMode(Enum):
    """Photoshop-style blend modes."""
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    HARD_LIGHT = "hard_light"
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"
    DARKEN = "darken"
    LIGHTEN = "lighten"
    ADD = "add"
    SUBTRACT = "subtract"


@dataclass
class Layer:
    """
    A single compositing layer.
    
    Args:
        name: Layer identifier
        data: Layer pixel data (height, width, 3) RGB or (height, width, 4) RGBA
        blend_mode: How to blend with layers below
        opacity: Layer opacity (0.0–1.0)
        visible: Layer visibility toggle
        mask: Optional alpha mask (0.0–1.0)
        z_order: Stacking order (lower = closer to background)
    """
    name: str
    data: np.ndarray
    blend_mode: BlendMode = BlendMode.NORMAL
    opacity: float = 1.0
    visible: bool = True
    mask: Optional[np.ndarray] = None
    z_order: int = 0
    
    def __post_init__(self):
        """Validate and normalize layer data."""
        if not isinstance(self.data, np.ndarray):
            raise ValueError(f"Layer data must be numpy array, got {type(self.data)}")
        
        if self.data.ndim not in (2, 3):
            raise ValueError(f"Layer data must be 2D (grayscale) or 3D (RGB/RGBA), got shape {self.data.shape}")
        
        # Convert grayscale to RGB
        if self.data.ndim == 2:
            self.data = np.stack([self.data] * 3, axis=-1)
        
        # Ensure RGB or RGBA
        if self.data.shape[2] not in (3, 4):
            raise ValueError(f"Layer must be RGB or RGBA, got {self.data.shape[2]} channels")
        
        # Normalize to uint8
        if self.data.dtype != np.uint8:
            self.data = (np.clip(self.data, 0, 1) * 255).astype(np.uint8)
        
        # Validate opacity
        self.opacity = np.clip(self.opacity, 0.0, 1.0)
        
        # Validate mask if provided
        if self.mask is not None:
            if self.mask.shape[:2] != self.data.shape[:2]:
                raise ValueError(f"Mask shape {self.mask.shape} doesn't match layer {self.data.shape[:2]}")
            self.mask = np.clip(self.mask, 0.0, 1.0)


class LayeredFrameCompositor:
    """
    Photoshop-style layered frame compositor.
    
    Manages multiple layers with blend modes, alpha blending, and masking.
    Enables AI vision to extract individual layers or composited output.
    """
    
    def __init__(self, width: int, height: int):
        """
        Initialize compositor with output dimensions.
        
        Args:
            width: Output frame width
            height: Output frame height
        """
        self.width = width
        self.height = height
        self.layers: Dict[str, Layer] = {}
        self.background_color = np.array([0, 0, 0], dtype=np.uint8)
        
    def add_layer(self, layer: Layer, resize: bool = True):
        """
        Add a layer to the compositor.
        
        Args:
            layer: Layer to add
            resize: If True, resize layer to match compositor dimensions
        """
        if layer.name in self.layers:
            raise ValueError(f"Layer '{layer.name}' already exists")
        
        # Resize if needed
        if resize and layer.data.shape[:2] != (self.height, self.width):
            from PIL import Image
            layer.data = np.array(Image.fromarray(layer.data).resize(
                (self.width, self.height), Image.LANCZOS
            ))
            if layer.mask is not None:
                layer.mask = np.array(Image.fromarray((layer.mask * 255).astype(np.uint8)).resize(
                    (self.width, self.height), Image.LANCZOS
                )) / 255.0
        
        # Validate dimensions
        if layer.data.shape[:2] != (self.height, self.width):
            raise ValueError(f"Layer {layer.name} dimensions {layer.data.shape[:2]} "
                           f"don't match compositor ({self.height}, {self.width})")
        
        self.layers[layer.name] = layer
        
    def remove_layer(self, name: str):
        """Remove a layer by name."""
        if name in self.layers:
            del self.layers[name]
    
    def get_layer(self, name: str) -> Optional[Layer]:
        """Get a layer by name."""
        return self.layers.get(name)
    
    def set_layer_visibility(self, name: str, visible: bool):
        """Toggle layer visibility."""
        if name in self.layers:
            self.layers[name].visible = visible
    
    def set_layer_opacity(self, name: str, opacity: float):
        """Set layer opacity."""
        if name in self.layers:
            self.layers[name].opacity = np.clip(opacity, 0.0, 1.0)
    
    def set_layer_blend_mode(self, name: str, mode: BlendMode):
        """Set layer blend mode."""
        if name in self.layers:
            self.layers[name].blend_mode = mode
    
    def reorder_layers(self, layer_order: List[str]):
        """
        Reorder layers by name list.
        
        Args:
            layer_order: List of layer names from bottom to top
        """
        for i, name in enumerate(layer_order):
            if name in self.layers:
                self.layers[name].z_order = i
    
    def _blend_normal(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Normal blend: alpha compositing."""
        return overlay
    
    def _blend_multiply(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Multiply blend: darkens image."""
        return (base.astype(np.float32) * overlay.astype(np.float32) / 255.0).astype(np.uint8)
    
    def _blend_screen(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Screen blend: lightens image."""
        return 255 - ((255 - base.astype(np.float32)) * 
                     (255 - overlay.astype(np.float32)) / 255.0).astype(np.uint8)
    
    def _blend_overlay(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Overlay blend: combines multiply and screen."""
        base_f = base.astype(np.float32) / 255.0
        overlay_f = overlay.astype(np.float32) / 255.0
        
        # Where base < 0.5: multiply; where base >= 0.5: screen
        mask = (base_f < 0.5).astype(np.float32)
        result = mask * (2.0 * base_f * overlay_f) + (1 - mask) * (1.0 - 2.0 * (1.0 - base_f) * (1.0 - overlay_f))
        
        return (np.clip(result, 0, 1) * 255).astype(np.uint8)
    
    def _blend_soft_light(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Soft light blend: subtle overlay."""
        base_f = base.astype(np.float32) / 255.0
        overlay_f = overlay.astype(np.float32) / 255.0
        
        # Simplified soft light
        result = base_f * (1 - overlay_f) + np.sqrt(base_f) * overlay_f
        
        return (np.clip(result, 0, 1) * 255).astype(np.uint8)
    
    def _blend_hard_light(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Hard light blend: strong overlay."""
        if overlay.ndim == 3 and overlay.shape[2] == 4:
            # Use luminance for RGBA
            luminance = np.dot(overlay[..., :3], [0.299, 0.587, 0.114]) / 255.0
        else:
            luminance = np.mean(overlay, axis=2) / 255.0 if overlay.ndim == 3 else overlay / 255.0
        
        mask = (luminance < 0.5)
        
        # Where overlay < 0.5: multiply; where >= 0.5: screen
        base_f = base.astype(np.float32)
        overlay_f = overlay.astype(np.float32)
        
        result = np.zeros_like(base_f)
        result[mask] = (2.0 * base_f[mask] * overlay_f[mask] / 255.0)
        result[~mask] = 255.0 - ((255.0 - base_f[~mask]) * (255.0 - overlay_f[~mask]) / 255.0)
        
        return np.clip(result, 0, 255).astype(np.uint8)
    
    def _blend_difference(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Difference blend: subtract darker from lighter."""
        return np.abs(base.astype(np.int16) - overlay.astype(np.int16)).astype(np.uint8)
    
    def _blend_exclusion(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Exclusion blend: softer difference."""
        base_f = base.astype(np.float32) / 255.0
        overlay_f = overlay.astype(np.float32) / 255.0
        
        result = base_f + overlay_f - 2.0 * base_f * overlay_f
        
        return (np.clip(result, 0, 1) * 255).astype(np.uint8)
    
    def _blend_darken(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Darken blend: use darker of each channel."""
        return np.minimum(base, overlay)
    
    def _blend_lighten(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Lighten blend: use lighter of each channel."""
        return np.maximum(base, overlay)
    
    def _blend_add(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Add blend: linear dodge."""
        return np.clip(base.astype(np.int16) + overlay.astype(np.int16), 0, 255).astype(np.uint8)
    
    def _blend_subtract(self, base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        """Subtract blend: linear burn."""
        return np.clip(base.astype(np.int16) - overlay.astype(np.int16), 0, 255).astype(np.uint8)
    
    def _apply_blend_mode(self, base: np.ndarray, overlay: np.ndarray, mode: BlendMode) -> np.ndarray:
        """Apply a blend mode to two layers."""
        blend_functions = {
            BlendMode.NORMAL: self._blend_normal,
            BlendMode.MULTIPLY: self._blend_multiply,
            BlendMode.SCREEN: self._blend_screen,
            BlendMode.OVERLAY: self._blend_overlay,
            BlendMode.SOFT_LIGHT: self._blend_soft_light,
            BlendMode.HARD_LIGHT: self._blend_hard_light,
            BlendMode.DIFFERENCE: self._blend_difference,
            BlendMode.EXCLUSION: self._blend_exclusion,
            BlendMode.DARKEN: self._blend_darken,
            BlendMode.LIGHTEN: self._blend_lighten,
            BlendMode.ADD: self._blend_add,
            BlendMode.SUBTRACT: self._blend_subtract,
        }
        
        if mode not in blend_functions:
            raise ValueError(f"Unknown blend mode: {mode}")
        
        return blend_functions[mode](base, overlay)
    
    def _extract_alpha(self, layer: Layer) -> np.ndarray:
        """Extract alpha channel from layer (with opacity and mask)."""
        h, w = layer.data.shape[:2]
        
        # Start with opacity
        alpha = np.full((h, w), layer.opacity, dtype=np.float32)
        
        # Add mask if present
        if layer.mask is not None:
            alpha *= layer.mask
        
        # Add layer alpha channel if RGBA
        if layer.data.shape[2] == 4:
            alpha *= layer.data[..., 3].astype(np.float32) / 255.0
        
        return alpha
    
    def composite(self) -> np.ndarray:
        """
        Composite all visible layers in Z-order.
        
        Returns:
            Composited frame (height, width, 3) RGB
        """
        # Start with background
        result = np.full((self.height, self.width, 3), self.background_color, dtype=np.uint8)
        
        # Get layers sorted by Z-order (bottom to top)
        sorted_layers = sorted(self.layers.values(), key=lambda l: l.z_order)
        
        for layer in sorted_layers:
            if not layer.visible:
                continue
            
            # Extract RGB channels
            layer_rgb = layer.data[..., :3]
            
            # Apply blend mode
            blended = self._apply_blend_mode(result, layer_rgb, layer.blend_mode)
            
            # Alpha blend
            alpha = self._extract_alpha(layer)
            alpha = alpha[:, :, np.newaxis]  # Add channel dimension
            
            # Normal alpha compositing
            result = (result * (1 - alpha) + blended * alpha).astype(np.uint8)
        
        return result
    
    def extract_layer(self, name: str, include_mask: bool = False) -> np.ndarray:
        """
        Extract a single layer's pixel data.
        
        Args:
            name: Layer name
            include_mask: If True, include mask as alpha channel
            
        Returns:
            Layer data (height, width, 3) or (height, width, 4)
        """
        if name not in self.layers:
            raise ValueError(f"Layer '{name}' not found")
        
        layer = self.layers[name]
        
        if include_mask and layer.mask is not None:
            # Combine RGB with mask as alpha
            alpha = layer.mask * 255
            if layer.data.shape[2] == 4:
                # Combine existing alpha with mask
                existing_alpha = layer.data[..., 3].astype(np.float32) / 255.0
                alpha = existing_alpha * layer.mask * 255
            
            # Add alpha channel
            result = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            result[..., :3] = layer.data[..., :3]
            result[..., 3] = alpha.astype(np.uint8)
            return result
        elif include_mask:
            # No mask, but RGBA requested
            if layer.data.shape[2] == 4:
                return layer.data
            else:
                result = np.zeros((self.height, self.width, 4), dtype=np.uint8)
                result[..., :3] = layer.data[..., :3]
                result[..., 3] = (layer.opacity * 255).astype(np.uint8)
                return result
        else:
            # RGB only
            return layer.data[..., :3]
    
    def get_layer_names(self) -> List[str]:
        """Get all layer names."""
        return list(self.layers.keys())
    
    def get_active_layers(self) -> List[str]:
        """Get visible layer names."""
        return [name for name, layer in self.layers.items() if layer.visible]


def main():
    """Demo layered compositor."""
    import argparse
    from PIL import Image
    
    parser = argparse.ArgumentParser(description="Layered Frame Compositor Demo")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--output", default="/tmp/layered_composite.png")
    args = parser.parse_args()
    
    print("="*60)
    print("Layered Frame Compositor Demo")
    print("="*60)
    
    # Create compositor
    comp = LayeredFrameCompositor(args.width, args.height)
    
    # Create background layer (gradient)
    print("\nCreating background layer...")
    bg = np.zeros((args.height, args.width, 3), dtype=np.uint8)
    for y in range(args.height):
        bg[y, :, 0] = int(y / args.height * 100)  # Red gradient
        bg[y, :, 1] = 50
        bg[y, :, 2] = int((1 - y / args.height) * 100)  # Blue gradient
    
    comp.add_layer(Layer("background", bg, z_order=0))
    
    # Create circle layer
    print("Creating circle layer...")
    circle = np.zeros((args.height, args.width, 3), dtype=np.uint8)
    y, x = np.ogrid[:args.height, :args.width]
    center_x, center_y = args.width // 2, args.height // 2
    radius = min(args.width, args.height) // 4
    
    mask = (x - center_x)**2 + (y - center_y)**2 <= radius**2
    circle[mask] = [255, 200, 50]  # Yellow circle
    
    comp.add_layer(Layer("circle", circle, z_order=1, opacity=0.9))
    
    # Create square layer with multiply blend
    print("Creating square layer...")
    square = np.zeros((args.height, args.width, 3), dtype=np.uint8)
    square_size = args.width // 6
    start_x = start_y = args.width // 2 - square_size // 2
    square[start_y:start_y+square_size, start_x:start_x+square_size] = [100, 150, 255]
    
    comp.add_layer(Layer("square", square, BlendMode.MULTIPLY, z_order=2))
    
    # Composite and save
    print("\nCompositing...")
    result = comp.composite()
    print(f"  Result shape: {result.shape}")
    print(f"  Result dtype: {result.dtype}")
    print(f"  Layers: {len(comp.layers)}")
    print(f"  Active layers: {len(comp.get_active_layers())}")
    
    # Save
    img = Image.fromarray(result)
    img.save(args.output)
    print(f"\nSaved to: {args.output}")
    
    # Extract individual layers
    print("\nExtracting individual layers...")
    for name in comp.get_layer_names():
        layer_data = comp.extract_layer(name)
        layer_path = f"/tmp/layer_{name}.png"
        Image.fromarray(layer_data).save(layer_path)
        print(f"  {name}: {layer_path}")
    
    print("\n✓ Demo complete")


if __name__ == "__main__":
    main()
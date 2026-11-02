#!/usr/bin/env python3
"""
Pixel Layer System — Non-Destructive Storage Overlays for Pixel Linux

Implements Photoshop-style non-destructive layer compositing on top of
Pixel Linux frame containers (PXC1 RGBA / VAC2 BGR).

Instead of destructively overwriting the 13GB base OS container, edits are
stored as lightweight sparse delta layers that can be stacked, toggled on/off,
inspected, or flattened into a new container without modifying the base.

Usage:
    python3 tools/pixel_layer.py init <base_container> [--stack-dir <dir>]
    python3 tools/pixel_layer.py create-layer <layer_name> [--desc "Description"]
    python3 tools/pixel_layer.py paint <layer_name> <frame_idx> string <text> <x> <y>
    python3 tools/pixel_layer.py paint <layer_name> <frame_idx> write <x> <y> <r> <g> <b> [a]
    python3 tools/pixel_layer.py toggle <layer_name> [on|off]
    python3 tools/pixel_layer.py read-composite <frame_idx> <x> <y>
    python3 tools/pixel_layer.py list
    python3 tools/pixel_layer.py flatten --output <new_container_dir>
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


FRAME_SIZE = 4096
DEFAULT_STACK_FILE = "layer_stack.json"


@dataclass
class LayerMeta:
    name: str
    description: str
    enabled: bool
    z_order: int
    patches_count: int = 0


class PixelLayerStack:
    def __init__(self, stack_dir: Path):
        self.stack_dir = Path(stack_dir)
        self.stack_file = self.stack_dir / DEFAULT_STACK_FILE
        self.base_container: Optional[Path] = None
        self.layers: List[LayerMeta] = []
        self._load()

    def _load(self):
        if self.stack_file.exists():
            with open(self.stack_file, "r") as f:
                data = json.load(f)
            self.base_container = Path(data.get("base_container", ""))
            self.layers = [LayerMeta(**item) for item in data.get("layers", [])]

    def save(self):
        self.stack_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "base_container": str(self.base_container) if self.base_container else "",
            "layers": [asdict(l) for l in self.layers],
        }
        with open(self.stack_file, "w") as f:
            json.dump(data, f, indent=2)

    def init_stack(self, base_container: Path):
        self.base_container = Path(base_container).resolve()
        if not self.base_container.exists():
            raise FileNotFoundError(f"Base container does not exist: {base_container}")
        self.layers = []
        self.save()
        print(f"✓ Initialized pixel layer stack at {self.stack_dir}")
        print(f"  Base container: {self.base_container}")

    def create_layer(self, name: str, description: str = "") -> LayerMeta:
        if any(l.name == name for l in self.layers):
            raise ValueError(f"Layer '{name}' already exists.")
        
        layer_dir = self.stack_dir / "layers" / name
        layer_dir.mkdir(parents=True, exist_ok=True)
        
        meta = LayerMeta(
            name=name,
            description=description,
            enabled=True,
            z_order=len(self.layers) + 1,
            patches_count=0,
        )
        self.layers.append(meta)
        self.save()
        print(f"✓ Created layer '{name}' (z-order: {meta.z_order})")
        return meta

    def get_layer_patch_file(self, layer_name: str, frame_idx: int) -> Path:
        layer_dir = self.stack_dir / "layers" / layer_name
        return layer_dir / f"frame_{frame_idx:05d}_patches.json"

    def load_layer_patches(self, layer_name: str, frame_idx: int) -> Dict[str, List[int]]:
        patch_file = self.get_layer_patch_file(layer_name, frame_idx)
        if patch_file.exists():
            with open(patch_file, "r") as f:
                return json.load(f)
        return {}

    def save_layer_patches(self, layer_name: str, frame_idx: int, patches: Dict[str, List[int]]):
        patch_file = self.get_layer_patch_file(layer_name, frame_idx)
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        with open(patch_file, "w") as f:
            json.dump(patches, f)

    def paint_pixel(self, layer_name: str, frame_idx: int, x: int, y: int, rgba: Tuple[int, int, int, int]):
        patches = self.load_layer_patches(layer_name, frame_idx)
        key = f"{x},{y}"
        patches[key] = list(rgba)
        self.save_layer_patches(layer_name, frame_idx, patches)
        
        for l in self.layers:
            if l.name == layer_name:
                l.patches_count = self._count_total_patches(layer_name)
                break
        self.save()

    def paint_string(self, layer_name: str, frame_idx: int, text: str, x: int, y: int):
        raw_bytes = text.encode("utf-8")
        patches = self.load_layer_patches(layer_name, frame_idx)
        
        if len(raw_bytes) % 4 != 0:
            raw_bytes += b"\x00" * (4 - (len(raw_bytes) % 4))
            
        num_pixels = len(raw_bytes) // 4
        for i in range(num_pixels):
            px = (x + i) % FRAME_SIZE
            py = y + ((x + i) // FRAME_SIZE)
            chunk = raw_bytes[i*4 : (i+1)*4]
            patches[f"{px},{py}"] = [chunk[0], chunk[1], chunk[2], chunk[3]]
            
        self.save_layer_patches(layer_name, frame_idx, patches)
        for l in self.layers:
            if l.name == layer_name:
                l.patches_count = self._count_total_patches(layer_name)
                break
        self.save()
        print(f"✓ Painted string '{text}' ({len(raw_bytes)} bytes / {num_pixels} px) into layer '{layer_name}'")

    def _count_total_patches(self, layer_name: str) -> int:
        layer_dir = self.stack_dir / "layers" / layer_name
        if not layer_dir.exists():
            return 0
        total = 0
        for pf in layer_dir.glob("frame_*_patches.json"):
            try:
                with open(pf, "r") as f:
                    patches = json.load(f)
                    total += len(patches)
            except Exception:
                pass
        return total

    def toggle_layer(self, name: str, state: Optional[bool] = None) -> bool:
        for l in self.layers:
            if l.name == name:
                l.enabled = not l.enabled if state is None else state
                self.save()
                status = "ENABLED" if l.enabled else "DISABLED"
                print(f"✓ Layer '{name}' is now {status}")
                return l.enabled
        raise ValueError(f"Layer '{name}' not found.")

    def read_composite_pixel(self, frame_idx: int, x: int, y: int) -> Tuple[int, int, int, int]:
        active_layers = sorted([l for l in self.layers if l.enabled], key=lambda l: l.z_order, reverse=True)
        key = f"{x},{y}"
        
        for layer in active_layers:
            patches = self.load_layer_patches(layer.name, frame_idx)
            if key in patches:
                r, g, b, a = patches[key]
                if a > 0:
                    return (r, g, b, a)

        if not self.base_container:
            return (0, 0, 0, 0)
            
        base_frame_path = self.base_container / f"frame_{frame_idx:05d}.png"
        if not base_frame_path.exists():
            return (0, 0, 0, 0)
            
        if not HAS_PIL:
            raise ImportError("PIL is required to read base container PNG frames.")
            
        img = Image.open(base_frame_path).convert("RGBA")
        return img.getpixel((x, y))

    def flatten_to_container(self, output_dir: Path):
        if not self.base_container or not self.base_container.exists():
            raise FileNotFoundError("Base container not configured or missing.")
        if not HAS_PIL:
            raise ImportError("PIL is required to flatten frames.")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        frame_files = sorted(self.base_container.glob("frame_*.png"))
        print(f"Flattening {len(frame_files)} frames with {len(self.layers)} layers to {output_dir}...")

        active_layers = sorted([l for l in self.layers if l.enabled], key=lambda l: l.z_order)

        for frame_path in frame_files:
            frame_name = frame_path.name
            frame_idx = int(frame_name.split("_")[1].split(".")[0])
            
            frame_patches: Dict[str, List[int]] = {}
            for layer in active_layers:
                layer_patches = self.load_layer_patches(layer.name, frame_idx)
                frame_patches.update(layer_patches)
                
            out_frame_path = output_dir / frame_name
            if not frame_patches:
                with open(frame_path, "rb") as f_in, open(out_frame_path, "wb") as f_out:
                    f_out.write(f_in.read())
            else:
                img = Image.open(frame_path).convert("RGBA")
                pixels = img.load()
                for coord_str, rgba in frame_patches.items():
                    px, py = map(int, coord_str.split(","))
                    pixels[px, py] = tuple(rgba)
                img.save(out_frame_path, format="PNG")
                print(f"  ✓ Baked {len(frame_patches)} patch(es) into {frame_name}")

        header_src = self.base_container / "header.json"
        if header_src.exists():
            with open(header_src, "rb") as f_in, open(output_dir / "header.json", "wb") as f_out:
                f_out.write(f_in.read())

        print(f"\n✓ Flatten complete! New container ready at: {output_dir}")


def main():
    common_p = argparse.ArgumentParser(add_help=False)
    common_p.add_argument("--stack-dir", default=".pixel_layers", help="Path to layer stack directory (default: .pixel_layers)")

    parser = argparse.ArgumentParser(description="Pixel Layer System — Non-Destructive Storage Overlays", parents=[common_p])
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    init_p = subparsers.add_parser("init", parents=[common_p], help="Initialize a layer stack with a base container")
    init_p.add_argument("base_container", help="Path to base PXC1 container directory")

    create_p = subparsers.add_parser("create-layer", parents=[common_p], help="Create a new non-destructive overlay layer")
    create_p.add_argument("name", help="Layer name")
    create_p.add_argument("--desc", default="", help="Layer description")

    paint_p = subparsers.add_parser("paint", parents=[common_p], help="Paint into a layer")
    paint_p.add_argument("layer_name", help="Target layer name")
    paint_p.add_argument("frame_idx", type=int, help="Frame index (0, 1, ...)")
    paint_sub = paint_p.add_subparsers(dest="paint_op", help="Paint operation")
    
    str_p = paint_sub.add_parser("string", parents=[common_p], help="Paint text string into layer")
    str_p.add_argument("text", help="Text to paint")
    str_p.add_argument("x", type=int, help="X coordinate")
    str_p.add_argument("y", type=int, help="Y coordinate")

    w_p = paint_sub.add_parser("write", parents=[common_p], help="Write RGBA pixel into layer")
    w_p.add_argument("x", type=int, help="X coordinate")
    w_p.add_argument("y", type=int, help="Y coordinate")
    w_p.add_argument("r", type=int, help="Red (0-255)")
    w_p.add_argument("g", type=int, help="Green (0-255)")
    w_p.add_argument("b", type=int, help="Blue (0-255)")
    w_p.add_argument("a", type=int, nargs="?", default=255, help="Alpha (0-255)")

    tog_p = subparsers.add_parser("toggle", parents=[common_p], help="Toggle layer visibility on/off")
    tog_p.add_argument("name", help="Layer name")
    tog_p.add_argument("state", nargs="?", choices=["on", "off"], help="State (on/off)")

    rc_p = subparsers.add_parser("read-composite", parents=[common_p], help="Read composited pixel across active layers")
    rc_p.add_argument("frame_idx", type=int, help="Frame index")
    rc_p.add_argument("x", type=int, help="X coordinate")
    rc_p.add_argument("y", type=int, help="Y coordinate")

    subparsers.add_parser("list", parents=[common_p], help="List all layers in the stack")

    flat_p = subparsers.add_parser("flatten", parents=[common_p], help="Bake active layers into a new standalone container")
    flat_p.add_argument("--output", "-o", required=True, help="Output container directory")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    stack = PixelLayerStack(Path(args.stack_dir))

    if args.command == "init":
        stack.init_stack(Path(args.base_container))
    elif args.command == "create-layer":
        stack.create_layer(args.name, args.desc)
    elif args.command == "paint":
        if args.paint_op == "string":
            stack.paint_string(args.layer_name, args.frame_idx, args.text, args.x, args.y)
        elif args.paint_op == "write":
            stack.paint_pixel(args.layer_name, args.frame_idx, args.x, args.y, (args.r, args.g, args.b, args.a))
    elif args.command == "toggle":
        st = True if args.state == "on" else (False if args.state == "off" else None)
        stack.toggle_layer(args.name, st)
    elif args.command == "read-composite":
        val = stack.read_composite_pixel(args.frame_idx, args.x, args.y)
        print(f"Composited Pixel at frame {args.frame_idx} ({args.x}, {args.y}): RGBA={val} Hex=#{val[0]:02x}{val[1]:02x}{val[2]:02x}{val[3]:02x}")
    elif args.command == "list":
        print("\n" + "=" * 60)
        print(f"PIXEL LAYER STACK: {stack.stack_dir}")
        print(f"Base Container:   {stack.base_container}")
        print("=" * 60)
        if not stack.layers:
            print("  (No layers created yet)")
        for l in sorted(stack.layers, key=lambda x: x.z_order):
            st = "[VISIBLE]" if l.enabled else "[HIDDEN] "
            print(f"  {st} Layer #{l.z_order}: '{l.name}' ({l.patches_count} modified pixels)")
            if l.description:
                print(f"             Description: {l.description}")
        print("=" * 60 + "\n")
    elif args.command == "flatten":
        stack.flatten_to_container(Path(args.output))


if __name__ == "__main__":
    main()

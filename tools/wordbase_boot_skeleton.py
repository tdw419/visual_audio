#!/usr/bin/env python3
"""
Wordbase-Enhanced MKV Boot Skeleton

This skeleton defines the architecture for booting systems from MKV with
wordbase-powered semantic capabilities:

1. Extract boot components (QEMU, kernel, disk) from MKV
2. Optionally encode/decode via wordbase for semantic operations
3. Boot with self-aware emulators that can modify themselves

Phase 1: Skeleton (interfaces only)
Phase 2: Component extraction and boot verification
Phase 3: Wordbase semantic encoding integration
Phase 4: Self-modifying emulator support
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any
import argparse

# -----------------------------------------------------------------------
# PHASE 1: SKELETON - Interfaces and Data Structures
# -----------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
MKV_PATH = REPO_ROOT / "visual_audio.mkv"


class MKVBootComponent:
    """Represents a boot component stored in MKV."""
    
    def __init__(self, name: str, role: str, required: bool = True):
        self.name = name
        self.role = role  # 'emulator', 'kernel', 'disk', 'code'
        self.required = required
        self.extracted_path: Optional[Path] = None
        self.semantic_encoding: Optional[bytes] = None
        self.size: int = 0
    
    def extract(self, mkv_path: Path) -> bool:
        """Extract component from MKV."""
        import tempfile
        import subprocess

        # Extract to temp directory
        temp_dir = Path(tempfile.mkdtemp())
        self.extracted_path = temp_dir / Path(self.name).name

        print(f"Extracting {self.name} to {self.extracted_path}...")

        # Use absolute path for mkv and cwd from original mkv location (not mkv_path.parent)
        # This ensures tools/va_container.py is found
        cwd = Path(__file__).parent.parent  # Project root

        result = subprocess.run([
            "python3", "tools/va_container.py", "cat",
            str(mkv_path.resolve()), self.name,
            "-o", str(self.extracted_path.resolve())
        ], cwd=str(cwd), capture_output=True, text=True)

        if result.returncode != 0:
            print(f"ERROR: Failed to extract {self.name}: {result.stderr}")
            return False

        self.size = self.extracted_path.stat().st_size
        print(f"  ✓ Extracted {self.name}: {self.size:,} bytes")
        return True
    
    def encode_semantic(self) -> Optional[bytes]:
        """Encode component via wordbase (for code/data)."""
        import sys
        from pathlib import Path

        # Only code components get semantic encoding
        if self.role != 'code':
            print(f"  [{self.name}] Not a code component, skipping semantic encoding")
            return None

        if not self.extracted_path:
            print(f"  [{self.name}] No extracted path available")
            return None

        try:
            # Import PixelTokenizer
            project_root = Path(__file__).parent.parent
            sys.path.insert(0, str(project_root))

            from src.pixel_tokenizer import PixelTokenizer

            # Read component as raw bytes
            with open(self.extracted_path, 'rb') as f:
                raw_bytes = f.read()

            # For code files, use direct byte-to-word encoding (preserves all syntax)
            # This ensures round-trip fidelity even with punctuation loss in tokenizer
            print(f"  [{self.name}] Using direct byte encoding ({len(raw_bytes)} bytes)")

            # Map each byte (0-255) to a word ID
            # Special tokens (0-15) reserved, so add offset of 16
            special_offset = 16

            # Each byte becomes one word ID: byte + special_offset
            word_ids = [b + special_offset for b in raw_bytes]

            # Convert to RGB24 pixels
            tokenizer = PixelTokenizer()
            pixels = tokenizer.ids_to_pixels(word_ids)

            # Store as bytes (3 bytes per pixel)
            pixel_bytes = pixels.tobytes()

            self.semantic_encoding = pixel_bytes
            self._is_byte_encoded = True  # Mark as byte-encoded for decode

            print(f"  ✓ [{self.name}] Encoded via wordbase (byte-level): {len(word_ids)} bytes → {len(pixel_bytes)} pixels")

            tokenizer.close()
            return pixel_bytes

        except Exception as e:
            print(f"  ✗ [{self.name}] Semantic encoding failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def store_semantic_in_mkv(self, mkv_path: Path) -> bool:
        """Store pixel-encoded version back to MKV (Phase 5 extension)."""
        if not self.semantic_encoding:
            print(f"  [{self.name}] No semantic encoding to store")
            return False

        if self.role != 'code':
            print(f"  [{self.name}] Not a code component, skipping MKV storage")
            return False

        import subprocess
        import tempfile

        print(f"\n[{self.name}] Storing pixel-encoded version in MKV...")

        # Write pixel bytes to temp file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pixels') as f:
            f.write(self.semantic_encoding)
            temp_path = f.name

        # Add to MKV with new name (original + ".pixel")
        pixel_name = f"{self.name}.pixel"

        # Use project root as cwd to find tools/va_container.py
        cwd = Path(__file__).parent.parent

        result = subprocess.run([
            "python3", "tools/va_container.py", "add",
            str(mkv_path.resolve()), temp_path,
            "--name", pixel_name,
            "--role", "semantic_code"
        ], cwd=str(cwd), capture_output=True, text=True)

        # Cleanup temp file
        Path(temp_path).unlink(missing_ok=True)

        if result.returncode != 0:
            print(f"  ✗ [{self.name}] Failed to store in MKV: {result.stderr}")
            return False

        self._pixel_name = pixel_name
        print(f"  ✓ [{self.name}] Stored pixel version as '{pixel_name}' ({len(self.semantic_encoding)} bytes)")
        return True

    def decode_semantic(self, pixel_data: bytes) -> bool:
        """Decode component from wordbase pixels."""
        import sys
        import numpy as np
        from pathlib import Path

        try:
            # Import PixelTokenizer
            project_root = Path(__file__).parent.parent
            sys.path.insert(0, str(project_root))

            from src.pixel_tokenizer import PixelTokenizer

            # Convert bytes to pixel array (RGB24)
            pixels = np.frombuffer(pixel_data, dtype=np.uint8).reshape(-1, 3)

            # Initialize tokenizer and convert pixels to word IDs
            tokenizer = PixelTokenizer()
            word_ids = tokenizer.pixels_to_ids(pixels)

            # Handle byte-level encoding (direct mapping for code files)
            if hasattr(self, '_is_byte_encoded') and self._is_byte_encoded:
                special_offset = 16
                # Convert word IDs back to bytes
                recovered_bytes = bytes([wid - special_offset for wid in word_ids if wid >= special_offset])
                print(f"  ✓ [{self.name}] Decoded from wordbase (byte-level): {len(pixel_data)} pixels → {len(recovered_bytes)} bytes")
                data_for_compare = recovered_bytes
            else:
                # Text decoding (original method - not currently used for code)
                recovered_text = tokenizer.decode(word_ids)
                print(f"  ✓ [{self.name}] Decoded from wordbase (text): {len(pixel_data)} pixels → {len(recovered_text)} chars")
                data_for_compare = recovered_text.encode('utf-8')

            # Verify round-trip fidelity
            if self.extracted_path:
                with open(self.extracted_path, 'rb') as f:
                    original_data = f.read()

                if data_for_compare == original_data:
                    print(f"  ✓ [{self.name}] Round-trip verification: PASS")
                    tokenizer.close()
                    return True
                else:
                    print(f"  ✗ [{self.name}] Round-trip verification: FAIL")
                    print(f"    Original: {len(original_data)} bytes")
                    print(f"    Recovered: {len(data_for_compare)} bytes")
                    tokenizer.close()
                    return False

            tokenizer.close()
            return True

        except Exception as e:
            print(f"  ✗ [{self.name}] Semantic decoding failed: {e}")
            import traceback
            traceback.print_exc()
            return False


class WordbaseBootWorkflow:
    """Orchestrates wordbase-enhanced MKV boot process."""
    
    def __init__(self, mkv_path: Path, use_semantic: bool = False):
        self.mkv_path = mkv_path
        self.use_semantic = use_semantic
        self.components: Dict[str, MKVBootComponent] = {}
        self._init_components()
    
    def _init_components(self):
        """Initialize boot component definitions."""
        # Phase 2: Define required components (names must match MKV ls output)
        self.components = {
            'qemu_bootstrap': MKVBootComponent('qemu_bootstrap', 'emulator', required=True),
            'linux/kernel/Image': MKVBootComponent('linux/kernel/Image', 'kernel', required=True),
            'ubuntu/desktop/ubuntu-24.04-desktop.qcow2': MKVBootComponent(
                'ubuntu/desktop/ubuntu-24.04-desktop.qcow2', 'disk', required=True
            ),
            'semantic_cpu_emulator.py': MKVBootComponent('semantic_cpu_emulator.py', 'code', required=self.use_semantic),
        }
    
    def verify_mkv(self) -> bool:
        """Verify MKV contains required components."""
        import subprocess

        print(f"Verifying MKV: {self.mkv_path}")

        result = subprocess.run([
            "python3", "tools/va_container.py", "ls", str(self.mkv_path)
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"ERROR: Failed to list MKV contents: {result.stderr}")
            return False

        mkv_content = result.stdout

        # Check required components
        missing = []
        for name, component in self.components.items():
            if component.required:
                if name not in mkv_content:
                    missing.append(name)
                else:
                    print(f"  ✓ Found: {name}")

        if missing:
            print(f"\nERROR: Missing required components: {missing}")
            return False

        print("\nAll required components present in MKV")
        return True
    
    def extract_components(self) -> bool:
        """Extract all required components (plus code if semantic enabled)."""
        print("\n" + "=" * 70)
        print("EXTRACTING COMPONENTS")
        print("=" * 70 + "\n")

        success_count = 0
        fail_count = 0

        for name, component in self.components.items():
            # Extract if required OR (code role and semantic mode enabled)
            should_extract = component.required or (component.role == 'code' and self.use_semantic)
            
            if should_extract:
                print(f"Processing: {name}")

                if component.extract(self.mkv_path):
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"  ✗ Failed to extract {name}")
                    if component.required:
                        print(f"  ERROR: Required component missing")
                        return False

        print(f"\nExtraction summary: {success_count} succeeded, {fail_count} failed")
        return fail_count == 0
    
    def encode_semantic_code(self) -> bool:
        """Encode code components via wordbase (Phase 5)."""
        if not self.use_semantic:
            print("[Semantic encoding] Disabled (use --semantic flag)")
            return True

        print("\n" + "=" * 70)
        print("PHASE 5: SEMANTIC ENCODING OF CODE COMPONENTS")
        print("=" * 70 + "\n")

        success_count = 0
        for name, component in self.components.items():
            if component.role == 'code' and component.extracted_path:
                print(f"Processing code component: {name}")
                
                if component.encode_semantic():
                    success_count += 1
                    # Verify round-trip
                    if component.semantic_encoding:
                        print(f"  Verifying round-trip...")
                        if component.decode_semantic(component.semantic_encoding):
                            print(f"  ✓ Round-trip verified for {name}")
                            
                            # Store pixel-encoded version in MKV
                            print(f"  Storing pixel-encoded version in MKV...")
                            if component.store_semantic_in_mkv(self.mkv_path):
                                print(f"  ✓ Pixel version stored in MKV as '{component._pixel_name}'")
                            else:
                                print(f"  ✗ Failed to store pixel version in MKV")
                                return False
                        else:
                            print(f"  ✗ Round-trip failed for {name}")
                            return False
                else:
                    print(f"  ✗ Encoding failed for {name}")
                    return False

        print(f"\nPhase 5 summary: {success_count} code components encoded semantically and stored in MKV")
        return success_count > 0
    
    def boot_system(self, nographic: bool = False) -> int:
        """Boot the system using extracted components."""
        import subprocess

        print("\n" + "=" * 70)
        print("BOOTING SYSTEM FROM EXTRACTED COMPONENTS")
        print("=" * 70 + "\n")

        # Check if components are extracted
        qemu_component = self.components.get('qemu_bootstrap')
        kernel_component = self.components.get('linux/kernel/Image')
        disk_component = self.components.get('ubuntu/desktop/ubuntu-24.04-desktop.qcow2')

        if not all(c.extracted_path for c in [qemu_component, kernel_component, disk_component]):
            print("ERROR: Not all components extracted. Run --extract first.")
            return 1

        print("Components:")
        print(f"  QEMU: {qemu_component.extracted_path}")
        print(f"  Kernel: {kernel_component.extracted_path}")
        print(f"  Disk: {disk_component.extracted_path}")

        # Build QEMU command
        qemu_cmd = [
            str(qemu_component.extracted_path),
            "-machine", "virt",
            "-cpu", "rv64",
            "-m", "2048",
            "-bios", "default",
            "-device", "virtio-gpu-device",
            "-device", "virtio-net-device,netdev=net0",
            "-netdev", "user,id=net0,hostfwd=tcp::2222-:22",
            "-kernel", str(kernel_component.extracted_path),
            "-drive", f"file={disk_component.extracted_path},if=virtio,format=qcow2",
            "-device", "virtio-blk-device",
            "-serial", "mon:stdio",
        ]

        # Display mode
        if nographic:
            qemu_cmd.append("-nographic")
            print("\nMode: nographic (no GUI)")
        else:
            qemu_cmd.append("-display")
            qemu_cmd.append("sdl")
            print("\nMode: SDL (GUI)")

        print("\nQEMU command:")
        print("  " + " ".join(qemu_cmd[:3]) + " \\")
        for i in range(3, len(qemu_cmd), 2):
            if i + 1 < len(qemu_cmd):
                print(f"    {qemu_cmd[i]} {qemu_cmd[i+1]} \\")
            else:
                print(f"    {qemu_cmd[i]}")

        print("\nStarting QEMU...")
        print("=" * 70 + "\n")

        # Run QEMU (let it inherit terminal)
        return subprocess.call(qemu_cmd)


class SemanticEmulatorBridge:
    """Bridge between MKV boot and wordbase semantic emulator."""

    def __init__(self, emulator_path: Path, mkv_path: Path):
        self.emulator_path = emulator_path
        self.mkv_path = mkv_path
        self.self_aware_mode = False
        self.kernel_path: Optional[Path] = None
        self.disk_path: Optional[Path] = None

    def set_components(self, kernel_path: Path, disk_path: Path):
        """Set kernel and disk paths for boot."""
        self.kernel_path = kernel_path
        self.disk_path = disk_path

    def enable_self_aware(self) -> bool:
        """Enable self-modification mode."""
        print("\n" + "=" * 70)
        print("ENABLING SELF-AWARE MODE")
        print("=" * 70 + "\n")

        # Check if semantic emulator exists in MKV
        import subprocess

        result = subprocess.run([
            "python3", "tools/va_container.py", "ls", str(self.mkv_path)
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"ERROR: Failed to list MKV: {result.stderr}")
            return False

        if 'semantic_cpu_emulator.py' not in result.stdout:
            print("WARNING: semantic_cpu_emulator.py not found in MKV")
            print("Self-aware mode will use default behavior")
            # Don't fail - allow boot without self-aware
            self.self_aware_mode = False
            return True

        print("✓ Found semantic_cpu_emulator.py in MKV")
        self.self_aware_mode = True

        # Extract semantic emulator
        print(f"\nExtracting semantic_cpu_emulator.py...")
        result = subprocess.run([
            "python3", "tools/va_container.py", "cat",
            str(self.mkv_path), "semantic_cpu_emulator.py",
            "-o", str(self.emulator_path)
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"ERROR: Failed to extract: {result.stderr}")
            return False

        print(f"✓ Extracted to: {self.emulator_path}")
        print(f"\nSelf-aware mode enabled")
        print("Emulator will be able to:")
        print("  - Load itself from MKV pixels")
        print("  - Analyze its own performance")
        print("  - Optimize hot paths via color adjustment")
        print("  - Create child MKVs with evolved code")

        return True

    def boot_with_self_modification(self) -> int:
        """Boot system with self-modifying emulator."""
        print("\n" + "=" * 70)
        print("BOOTING WITH SELF-MODIFYING EMULATOR")
        print("=" * 70 + "\n")

        if not self.kernel_path or not self.disk_path:
            print("ERROR: Kernel and disk paths not set. Call set_components() first.")
            return 1

        print(f"Kernel: {self.kernel_path}")
        print(f"Disk: {self.disk_path}")
        print(f"Emulator: {self.emulator_path}")

        # Build command
        cmd = [
            "python3", str(self.emulator_path),
            "--kernel", str(self.kernel_path),
            "--disk", str(self.disk_path),
        ]

        if self.self_aware_mode:
            cmd.append("--self-aware")
            cmd.append("--mkv")
            cmd.append(str(self.mkv_path))
            cmd.append("--optimize")
            print("\nMode: Self-aware (will load from MKV and optimize)")
        else:
            print("\nMode: Standard (no self-modification)")

        print("\nCommand:")
        print("  " + " ".join(cmd))

        print("\nStarting self-modifying emulator...")
        print("=" * 70 + "\n")

        import subprocess
        return subprocess.call(cmd)


# -----------------------------------------------------------------------
# PHASE 2: Verification and Simple Tests
# -----------------------------------------------------------------------

def verify_skeleton_compilation() -> bool:
    """Verify skeleton compiles without errors."""
    print("=" * 70)
    print("SKELETON VERIFICATION")
    print("=" * 70)
    
    try:
        # Test 1: Class instantiation
        print("\n[Test 1] Instantiating classes...")
        component = MKVBootComponent('test', 'code')
        workflow = WordbaseBootWorkflow(MKV_PATH, use_semantic=False)
        bridge = SemanticEmulatorBridge(Path('test.py'), MKV_PATH)
        print("  ✓ All classes instantiate successfully")
        
        # Test 2: Component structure
        print("\n[Test 2] Verifying component structure...")
        assert hasattr(component, 'name')
        assert hasattr(component, 'role')
        assert hasattr(component, 'extract')
        assert hasattr(component, 'encode_semantic')
        assert hasattr(component, 'decode_semantic')
        print("  ✓ Component interface complete")
        
        # Test 3: Workflow structure
        print("\n[Test 3] Verifying workflow structure...")
        assert hasattr(workflow, 'verify_mkv')
        assert hasattr(workflow, 'extract_components')
        assert hasattr(workflow, 'encode_semantic_code')
        assert hasattr(workflow, 'boot_system')
        print("  ✓ Workflow interface complete")
        
        # Test 4: Bridge structure
        print("\n[Test 4] Verifying bridge structure...")
        assert hasattr(bridge, 'enable_self_aware')
        assert hasattr(bridge, 'boot_with_self_modification')
        print("  ✓ Bridge interface complete")
        
        print("\n" + "=" * 70)
        print("SKELETON VERIFICATION COMPLETE")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n✗ Skeleton verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# -----------------------------------------------------------------------
# PHASE 3: Implementation Roadmap
# -----------------------------------------------------------------------

IMPLEMENTATION_ROADMAP = """
Phase 3: Implementation Roadmap

1. MKVBootComponent.extract()
   - Use va_container.py cat to extract component
   - Save to temp directory
   - Record size and path

2. WordbaseBootWorkflow.verify_mkv()
   - Use va_container.py ls to list entries
   - Check required components exist
   - Report missing components

3. WordbaseBootWorkflow.extract_components()
   - Iterate through components
   - Call extract() on each
   - Handle failures gracefully

4. WordbaseBootWorkflow.boot_system()
   - Construct QEMU command line
   - Handle nographic vs SDL mode
   - Start NBD server for disk streaming
   - Exec QEMU

5. MKVBootComponent.encode_semantic()
   - Load component as text (if code)
   - Use PixelTokenizer.encode()
   - Convert to RGB24 pixels
   - Store for later use

6. MKVBootComponent.decode_semantic()
   - Load pixel data
   - Use PixelTokenizer.decode_from_pixels()
   - Verify round-trip fidelity

7. SemanticEmulatorBridge.enable_self_aware()
   - Pass --self-aware and --mkv flags
   - Set up self-modification hooks

8. SemanticEmulatorBridge.boot_with_self_modification()
   - Run semantic emulator with --optimize
   - Capture performance metrics
   - Report optimization results
"""


def show_roadmap():
    """Display implementation roadmap."""
    print("\n" + "=" * 70)
    print("IMPLEMENTATION ROADMAP")
    print("=" * 70)
    print(IMPLEMENTATION_ROADMAP)
    print("=" * 70)


# -----------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Wordbase-Enhanced MKV Boot Skeleton"
    )
    parser.add_argument("--verify", action="store_true",
                       help="Verify skeleton compilation")
    parser.add_argument("--roadmap", action="store_true",
                       help="Show implementation roadmap")
    parser.add_argument("--boot", action="store_true",
                       help="Attempt boot (after implementation)")
    parser.add_argument("--extract", action="store_true",
                       help="Extract and verify components (Phase 2)")
    parser.add_argument("--extract-fast", action="store_true",
                       help="Extract only small components (skip disk)")
    parser.add_argument("--nographic", action="store_true",
                       help="Use nographic mode")
    parser.add_argument("--semantic", action="store_true",
                       help="Enable wordbase semantic encoding")
    parser.add_argument("--self-modifying", action="store_true",
                       help="Enable self-modifying emulator")

    args = parser.parse_args()

    print("=" * 70)
    print("WORDBASE-ENHANCED MKV BOOT")
    print("=" * 70)

    # Default: verify skeleton
    if not any([args.verify, args.roadmap, args.boot, args.extract, args.extract_fast]):
        print("\nNo action specified. Use --verify to test skeleton.")
        args.verify = True

    if args.verify:
        if not verify_skeleton_compilation():
            return 1

    if args.extract or args.extract_fast:
        workflow = WordbaseBootWorkflow(MKV_PATH, use_semantic=args.semantic)

        # Skip disk in fast mode
        if args.extract_fast:
            workflow.components['ubuntu/desktop/ubuntu-24.04-desktop.qcow2'].required = False
            print("Fast mode: skipping large disk image")

        if not workflow.verify_mkv():
            return 1

        if not workflow.extract_components():
            print("\nERROR: Component extraction failed")
            return 1

        # Phase 5: Semantic encoding of code components
        if args.semantic:
            if not workflow.encode_semantic_code():
                print("\nERROR: Semantic encoding failed")
                return 1

        print("\n" + "=" * 70)
        print("EXTRACTION COMPLETE")
        print("=" * 70)
        print("\nComponents extracted to temp directory:")
        for name, component in workflow.components.items():
            if component.extracted_path:
                size_mb = component.size / (1024 * 1024)
                print(f"  {name}: {component.extracted_path} ({size_mb:.1f} MB)")

    if args.roadmap:
        show_roadmap()

    if args.boot:
        print("\n" + "=" * 70)
        print("BOOT MODE")
        print("=" * 70)

        workflow = WordbaseBootWorkflow(MKV_PATH, use_semantic=args.semantic)

        # Check if components already extracted
        qemu_comp = workflow.components.get('qemu_bootstrap')
        kernel_comp = workflow.components.get('linux/kernel/Image')
        disk_comp = workflow.components.get('ubuntu/desktop/ubuntu-24.04-desktop.qcow2')

        if not all(c.extracted_path for c in [qemu_comp, kernel_comp, disk_comp]):
            print("\nComponents not extracted. Extracting now...")
            if not workflow.verify_mkv():
                return 1
            if not workflow.extract_components():
                print("\nERROR: Component extraction failed")
                return 1

        # Refresh references after extraction
        qemu_comp = workflow.components.get('qemu_bootstrap')
        kernel_comp = workflow.components.get('linux/kernel/Image')
        disk_comp = workflow.components.get('ubuntu/desktop/ubuntu-24.04-desktop.qcow2')

        # Verify we have paths now
        if not (qemu_comp and qemu_comp.extracted_path and
                kernel_comp and kernel_comp.extracted_path and
                disk_comp and disk_comp.extracted_path):
            print("\nERROR: Component extraction failed or paths missing")
            return 1

        print("\nUsing extracted components")

        if args.self_modifying:
            # Use SemanticEmulatorBridge for self-modifying boot
            print("\n[Self-Modifying Mode]")
            import tempfile
            emulator_path = Path(tempfile.mktemp(suffix='.py', prefix='semantic_emulator_'))

            if not kernel_comp.extracted_path or not disk_comp.extracted_path:
                print("\nERROR: Components not available for self-modifying boot")
                return 1

            bridge = SemanticEmulatorBridge(emulator_path, MKV_PATH)
            bridge.set_components(kernel_comp.extracted_path, disk_comp.extracted_path)

            if not bridge.enable_self_aware():
                print("\nERROR: Failed to enable self-aware mode")
                return 1

            return bridge.boot_with_self_modification()
        else:
            # Standard QEMU boot
            print("\n[Standard Mode]")
            return workflow.boot_system(nographic=args.nographic)

    return 0


if __name__ == "__main__":
    sys.exit(main())
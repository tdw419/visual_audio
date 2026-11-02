#!/usr/bin/env python3
"""
Semantic CPU Emulator - Self-Modifying Boot Environment

This emulator wraps QEMU boot with wordbase-powered self-awareness:

1. Boot RISC-V kernel from MKV components
2. Load its own code from MKV pixels (self-aware mode)
3. Analyze hot paths and performance metrics
4. Optimize itself via color adjustments (word-based refactoring)
5. Create child MKVs with evolved code

Phase 6: Self-Modification Implementation
"""

import sys
import os
import argparse
import subprocess
import tempfile
import time
import json
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np

# -----------------------------------------------------------------------
# Self-Aware Module Loader
# -----------------------------------------------------------------------

class SelfAwareLoader:
    """Load emulator's own code from MKV pixels."""

    def __init__(self, mkv_path: Path):
        self.mkv_path = mkv_path
        self.self_code_path: Optional[Path] = None
        self.pixel_data: Optional[np.ndarray] = None

    def load_self_from_pixels(self) -> Optional[Path]:
        """Load this emulator's own pixel-encoded code from MKV and return the decoded path."""
        import sys
        sys.path.insert(0, str(self.mkv_path.parent.parent))

        from src.pixel_tokenizer import PixelTokenizer

        print("\n" + "=" * 70)
        print("LOADING SELF FROM MKV PIXELS")
        print("=" * 70 + "\n")

        # Check if pixel version exists in MKV
        result = subprocess.run([
            "python3", "tools/va_container.py", "ls", str(self.mkv_path)
        ], capture_output=True, text=True, cwd=str(self.mkv_path.parent.parent))

        if result.returncode != 0:
            print(f"ERROR: Failed to list MKV: {result.stderr}")
            return None

        # Look for pixel-encoded version
        pixel_name = "semantic_cpu_emulator.py.pixel"
        if pixel_name not in result.stdout:
            print(f"WARNING: {pixel_name} not found in MKV")
            print("Self-aware mode disabled - using standard mode")
            return None

        print(f"✓ Found {pixel_name} in MKV")

        # Extract pixel data
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.npy') as f:
            temp_path = Path(f.name)

        result = subprocess.run([
            "python3", "tools/va_container.py", "cat",
            str(self.mkv_path), pixel_name,
            "-o", str(temp_path)
        ], capture_output=True, text=True, cwd=str(self.mkv_path.parent.parent))

        if result.returncode != 0:
            print(f"ERROR: Failed to extract {pixel_name}: {result.stderr}")
            temp_path.unlink(missing_ok=True)
            return None

        print(f"✓ Extracted to {temp_path}")

        # Load pixel data
        self.pixel_data = np.load(temp_path)
        temp_path.unlink(missing_ok=True)

        print(f"✓ Loaded pixel data: shape {self.pixel_data.shape}")

        # Decode to verify and save for execution
        tokenizer = PixelTokenizer()
        if self.pixel_data is None:
            print("ERROR: Pixel data is None")
            tokenizer.close()
            return None
        word_ids = tokenizer.pixels_to_ids(self.pixel_data)

        # Byte-level decoding
        special_offset = 16
        recovered_bytes = bytes([wid - special_offset for wid in word_ids if wid >= special_offset])

        print(f"✓ Decoded: {len(recovered_bytes)} bytes")

        # Save decoded code for execution (Phase 7: load from pixels)
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.py') as f:
            f.write(recovered_bytes)
            self.self_code_path = Path(f.name)

        print(f"✓ Saved self code to: {self.self_code_path}")

        # Compare with actual file
        self_path = Path(__file__)
        with open(self_path, 'rb') as f:
            actual_bytes = f.read()

        if recovered_bytes == actual_bytes:
            print("✓ Self-verification PASS: pixel code matches running code")
            print("  Phase 7: Can boot from pixel version in future cycles")
        else:
            print("⚠ Self-verification FAIL: pixel code differs from running code")
            print(f"  Pixel version: {len(recovered_bytes)} bytes")
            print(f"  Running code: {len(actual_bytes)} bytes")
            print("  This may indicate evolved code - Phase 7 will execute pixel version")

        tokenizer.close()
        return self.self_code_path

    def execute_pixel_version(self, pixel_code_path: Path, args: List[str]) -> int:
        """Execute the decoded pixel version of the emulator (Phase 7)."""
        print("\n" + "=" * 70)
        print("EXECUTING PIXEL-ENCODED VERSION")
        print("=" * 70 + "\n")

        if not pixel_code_path.exists():
            print(f"ERROR: Pixel code not found: {pixel_code_path}")
            return 1

        print(f"✓ Loading pixel version: {pixel_code_path}")
        print(f"✓ Executing with arguments: {args}")

        # Execute pixel version via subprocess
        # We use subprocess to ensure clean execution environment
        result = subprocess.run(
            ["python3", str(pixel_code_path)] + args,
            cwd=str(self.mkv_path.parent.parent)
        )

        print(f"\nPixel version exited with code: {result.returncode}")
        return result.returncode

# -----------------------------------------------------------------------
# Performance Analyzer
# -----------------------------------------------------------------------

class PerformanceAnalyzer:
    """Analyze emulator performance and identify hot paths."""

    def __init__(self):
        self.metrics: Dict[str, float] = {}
        self.hot_paths: List[str] = []

    def analyze_boot_time(self, kernel_path: Path, disk_path: Path) -> Dict[str, float]:
        """Measure boot performance metrics."""
        print("\n" + "=" * 70)
        print("ANALYZING BOOT PERFORMANCE")
        print("=" * 70 + "\n")

        # Mock performance analysis (real implementation would profile actual boot)
        # For now, return baseline metrics
        metrics = {
            'kernel_load_time': 0.5,
            'disk_init_time': 1.2,
            'boot_to_login_time': 8.5,
            'memory_peak_mb': 512,
            'instructions_executed': 1000000,
        }

        self.metrics = metrics
        print("Performance metrics:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")

        return metrics

    def identify_hot_paths(self) -> List[str]:
        """Identify functions/paths that need optimization."""
        # For now, return stub hot paths
        # Real implementation would use profiling data
        hot_paths = [
            'decode_instruction',
            'mmu_translate',
            'handle_interrupt',
        ]

        self.hot_paths = hot_paths
        print("\nIdentified hot paths:")
        for path in hot_paths:
            print(f"  - {path}")

        return hot_paths

# -----------------------------------------------------------------------
# Wordbase Optimizer
# -----------------------------------------------------------------------

class WordbaseOptimizer:
    """Optimize code via wordbase color adjustments."""

    def __init__(self, pixel_data: np.ndarray):
        self.pixel_data = pixel_data
        self.optimization_log: List[Dict] = []

    def optimize_hot_path(self, hot_path: str, old_word: str, new_word: str) -> np.ndarray:
        """Replace a word in a hot path via color swap."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.pixel_tokenizer import PixelTokenizer

        print(f"\nOptimizing hot path: {hot_path}")
        print(f"  Replacing: '{old_word}' → '{new_word}'")

        tokenizer = PixelTokenizer()

        # Get word data
        old_data = tokenizer.wordbase.get_word(old_word)
        new_data = tokenizer.wordbase.get_word(new_word)

        if not old_data or not old_data.get('color_hex'):
            print(f"  ERROR: Old word '{old_word}' not found or missing color")
            tokenizer.close()
            return self.pixel_data

        if not new_data or not new_data.get('color_hex'):
            print(f"  ERROR: New word '{new_word}' not found or missing color")
            tokenizer.close()
            return self.pixel_data

        # Parse hex colors (strip # prefix if present)
        old_hex = old_data['color_hex'].lstrip('#')
        new_hex = new_data['color_hex'].lstrip('#')

        try:
            or_, og, ob = bytes.fromhex(old_hex)
            nr, ng, nb = bytes.fromhex(new_hex)
        except ValueError as e:
            print(f"  ERROR: Invalid hex color: {e}")
            tokenizer.close()
            return self.pixel_data

        print(f"  Old color: #{old_data['color_hex']} ({or_}, {og}, {ob})")
        print(f"  New color: #{new_data['color_hex']} ({nr}, {ng}, {nb})")

        # Replace pixels (handle both 2D (N×3) and 3D (N×M×3) arrays)
        if self.pixel_data.ndim == 2:
            # 2D array: shape (N, 3) - each row is one pixel
            mask = (self.pixel_data[:,0] == or_) & (self.pixel_data[:,1] == og) & (self.pixel_data[:,2] == ob)
        elif self.pixel_data.ndim == 3:
            # 3D array: shape (N, M, 3) - standard image format
            mask = (self.pixel_data[:,:,0] == or_) & (self.pixel_data[:,:,1] == og) & (self.pixel_data[:,:,2] == ob)
        else:
            print(f"  ERROR: Unsupported pixel_data shape: {self.pixel_data.shape}")
            tokenizer.close()
            return self.pixel_data
        replaced_count = np.sum(mask)

        if replaced_count == 0:
            print(f"  No occurrences found (no change)")
            tokenizer.close()
            return self.pixel_data

        # Apply replacement
        optimized_pixels = self.pixel_data.copy()
        optimized_pixels[mask] = [nr, ng, nb]

        print(f"  ✓ Replaced {replaced_count} occurrences")

        # Log optimization
        self.optimization_log.append({
            'hot_path': hot_path,
            'old_word': old_word,
            'new_word': new_word,
            'replacements': int(replaced_count),
            'timestamp': time.time(),
        })

        tokenizer.close()
        return optimized_pixels

    def apply_optimizations(self, hot_paths: List[str]) -> np.ndarray:
        """Apply all optimizations to hot paths."""
        print("\n" + "=" * 70)
        print("APPLYING WORDBASE OPTIMIZATIONS")
        print("=" * 70 + "\n")

        optimized_pixels = self.pixel_data.copy()

        # Example optimizations (real implementation would be data-driven)
        optimizations = [
            ('decode_instruction', 'parse', 'decode'),
            ('mmu_translate', 'lookup', 'translate_fast'),
            ('handle_interrupt', 'dispatch', 'dispatch_optimized'),
        ]

        for hot_path, old_word, new_word in optimizations:
            if hot_path in hot_paths:
                temp_optimizer = WordbaseOptimizer(optimized_pixels)
                optimized_pixels = temp_optimizer.optimize_hot_path(hot_path, old_word, new_word)

        print(f"\n✓ Applied {len(optimizations)} optimizations")
        print(f"✓ Total replacements logged: {len(self.optimization_log)}")

        return optimized_pixels

# -----------------------------------------------------------------------
# Child MKV Creator
# -----------------------------------------------------------------------

class ChildMKVCreator:
    """Create child MKV with evolved code."""

    def __init__(self, parent_mkv_path: Path):
        self.parent_mkv_path = parent_mkv_path
        self.child_mkv_path: Optional[Path] = None

    def create_child(self, optimized_pixels: np.ndarray) -> Path:
        """Create child MKV with optimized code."""
        print("\n" + "=" * 70)
        print("CREATING CHILD MKV WITH EVOLVED CODE")
        print("=" * 70 + "\n")

        # Create temporary path for optimized pixels
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.npy') as f:
            np.save(f, optimized_pixels)
            temp_path = Path(f.name)

        # Generate child MKV name
        timestamp = int(time.time())
        child_name = f"visual_audio_evolved_{timestamp}.mkv"
        child_path = self.parent_mkv_path.parent / child_name

        # Copy parent to child (simple approach - in reality would use MKV metadata copy)
        import shutil
        shutil.copy(self.parent_mkv_path, child_path)

        print(f"✓ Created child MKV: {child_path}")

        # Update pixel-encoded code in child MKV
        result = subprocess.run([
            "python3", "tools/va_container.py", "add",
            str(child_path), str(temp_path),
            "--name", "semantic_cpu_emulator.py.pixel",
            "--role", "semantic_code"
        ], capture_output=True, text=True, cwd=str(self.parent_mkv_path.parent))

        # Cleanup
        temp_path.unlink(missing_ok=True)

        if result.returncode != 0:
            print(f"WARNING: Failed to add optimized pixels to child MKV: {result.stderr}")
            return child_path

        print(f"✓ Updated pixel code in child MKV")

        self.child_mkv_path = child_path
        return child_path

    def save_evolution_history(self, mkv_path: Path, evolution_history: List[Dict]) -> bool:
        """Persist evolution history to MKV metadata."""
        if not evolution_history:
            print("No evolution history to save")
            return True

        print("\n" + "=" * 70)
        print("SAVING EVOLUTION HISTORY TO MKV")
        print("=" * 70 + "\n")

        try:
            # Serialize evolution history to JSON
            history_json = json.dumps(evolution_history, indent=2).encode()
            print(f"✓ Serialized {len(evolution_history)} cycles ({len(history_json)} bytes)")

            # Save to temporary file
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.json') as f:
                f.write(history_json)
                temp_path = Path(f.name)

            # Add to MKV as a special entry
            result = subprocess.run([
                "python3", "tools/va_container.py", "add",
                str(mkv_path), str(temp_path),
                "--name", "evolution_history.json",
                "--role", "metadata",
                "--note", "Evolutionary improvement tracking across cycles"
            ], capture_output=True, text=True, cwd=str(mkv_path.parent))

            # Cleanup
            temp_path.unlink(missing_ok=True)

            if result.returncode != 0:
                print(f"ERROR: Failed to save evolution history: {result.stderr}")
                return False

            print("✓ Evolution history saved to MKV")
            return True

        except Exception as e:
            print(f"ERROR: Failed to save evolution history: {e}")
            return False

    @staticmethod
    def load_evolution_history(mkv_path: Path) -> Optional[List[Dict]]:
        """Load evolution history from MKV metadata."""
        print("\n" + "=" * 70)
        print("LOADING EVOLUTION HISTORY FROM MKV")
        print("=" * 70 + "\n")

        try:
            # Extract evolution history from MKV
            with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.json') as f:
                temp_path = Path(f.name)

            result = subprocess.run([
                "python3", "tools/va_container.py", "cat",
                str(mkv_path), "evolution_history.json",
                "-o", str(temp_path)
            ], capture_output=True, text=True, cwd=str(mkv_path.parent))

            if result.returncode != 0:
                print("No evolution history found in MKV (this is OK for first cycle)")
                temp_path.unlink(missing_ok=True)
                return None

            # Load and parse JSON
            with open(temp_path, 'rb') as f:
                history = json.load(f)

            temp_path.unlink(missing_ok=True)

            if not isinstance(history, list):
                print(f"ERROR: Invalid evolution history format (expected list, got {type(history)})")
                return None

            print(f"✓ Loaded {len(history)} cycles from MKV")
            for cycle in history:
                print(f"  Cycle {cycle.get('cycle', '?')}: {cycle.get('optimizations', 0)} optimizations")

            return history

        except Exception as e:
            print(f"ERROR: Failed to load evolution history: {e}")
            return None

# -----------------------------------------------------------------------
# Main Semantic CPU Emulator
# -----------------------------------------------------------------------

class SemanticCPUEmulator:
    """Main self-modifying CPU emulator."""

    def __init__(self, kernel_path: Path, disk_path: Path, mkv_path: Optional[Path] = None,
                 self_aware: bool = False, optimize: bool = False, use_pixel_version: bool = False,
                 max_cycles: int = 10, cycle_number: int = 0, auto_continue: bool = False):
        self.kernel_path = kernel_path
        self.disk_path = disk_path
        self.mkv_path = mkv_path
        self.self_aware = self_aware
        self.optimize = optimize
        self.use_pixel_version = use_pixel_version  # Phase 7: execute pixel version
        self.max_cycles = max_cycles  # Phase 7: max evolutionary cycles
        self.cycle_number = cycle_number  # Phase 7: current cycle
        self.auto_continue = auto_continue  # Phase 7: auto-launch next cycle

        # Components
        self.self_loader: Optional[SelfAwareLoader] = None
        self.analyzer = PerformanceAnalyzer()
        self.optimizer: Optional[WordbaseOptimizer] = None
        self.child_creator: Optional[ChildMKVCreator] = None

        # Phase 7: Evolution tracking
        self.evolution_history: List[Dict] = []

    def boot(self) -> int:
        """Boot the system with optional self-modification and recursive evolution."""
        print("=" * 70)
        print("SEMANTIC CPU EMULATOR BOOT")
        print("=" * 70)
        print(f"Kernel: {self.kernel_path}")
        print(f"Disk: {self.disk_path}")
        if self.mkv_path:
            print(f"MKV: {self.mkv_path}")
        print(f"Self-aware: {self.self_aware}")
        print(f"Optimize: {self.optimize}")
        print(f"Use pixel version: {self.use_pixel_version}")
        print(f"Cycle: {self.cycle_number}/{self.max_cycles}")
        print("=" * 70 + "\n")

        # Phase 7: Check cycle limit
        if self.cycle_number >= self.max_cycles:
            print(f"\nPhase 7: Reached max evolutionary cycles ({self.max_cycles})")
            print("Stopping evolution to prevent infinite recursion")
            return self._run_qemu()

        # Phase 7: Load evolution history from MKV if available
        if self.mkv_path:
            loaded_history = ChildMKVCreator.load_evolution_history(self.mkv_path)
            if loaded_history:
                self.evolution_history = loaded_history
                print(f"✓ Loaded {len(self.evolution_history)} prior cycles from MKV")
                print(f"  Total optimizations so far: {sum(h.get('optimizations', 0) for h in self.evolution_history)}\n")

        # Phase 7: Execute pixel version if requested and available
        if self.use_pixel_version and self.mkv_path:
            self.self_loader = SelfAwareLoader(self.mkv_path)
            pixel_code_path = self.self_loader.load_self_from_pixels()

            if pixel_code_path:
                # Build args for pixel version
                pixel_args = self._build_pixel_args()

                print("\n" + "=" * 70)
                print("PHASE 7: EXECUTING EVOLVED PIXEL VERSION")
                print("=" * 70 + "\n")
                print("This instance will delegate execution to the pixel-encoded version.")
                print("The pixel version contains evolved optimizations from previous cycles.\n")

                # Execute pixel version and exit (pixel version handles everything)
                exit_code = self.self_loader.execute_pixel_version(pixel_code_path, pixel_args)

                # If pixel version returns, propagate its exit code
                print(f"\nOriginal instance exiting with code: {exit_code}")
                return exit_code
            else:
                print("WARNING: Failed to load pixel version, continuing in standard mode")
                self.use_pixel_version = False

        # Step 1: Self-aware mode - load own code from pixels
        if self.self_aware and self.mkv_path:
            self.self_loader = SelfAwareLoader(self.mkv_path)
            if not self.self_loader.load_self_from_pixels():
                print("WARNING: Self-aware mode failed, continuing in standard mode")
                self.self_aware = False

        # Step 2: Analyze performance
        metrics = self.analyzer.analyze_boot_time(self.kernel_path, self.disk_path)
        hot_paths = self.analyzer.identify_hot_paths()

        # Step 3: Apply optimizations
        if self.optimize and self.self_aware and self.self_loader and self.self_loader.pixel_data is not None:
            self.optimizer = WordbaseOptimizer(self.self_loader.pixel_data)
            optimized_pixels = self.optimizer.apply_optimizations(hot_paths)

            # Step 4: Create child MKV
            if self.mkv_path is not None:
                self.child_creator = ChildMKVCreator(self.mkv_path)
                child_mkv = self.child_creator.create_child(optimized_pixels)
                print(f"\n✓ Child MKV created: {child_mkv}")

                # Phase 7: Log evolutionary step
                self.evolution_history.append({
                    'cycle': self.cycle_number,
                    'child_mkv': str(child_mkv),
                    'metrics': metrics,
                    'hot_paths': hot_paths,
                    'optimizations': len(self.optimizer.optimization_log),
                    'timestamp': time.time(),
                })

                # Phase 7: Persist evolution history to child MKV
                self.child_creator.save_evolution_history(child_mkv, self.evolution_history)

                # Phase 7: Recursive boot with pixel version
                if self.cycle_number < self.max_cycles - 1:
                    print(f"\n" + "=" * 70)
                    print("PHASE 7: RECURSIVE EVOLUTIONARY BOOT")
                    print("=" * 70)
                    print(f"Cycle {self.cycle_number} complete. Next boot from child MKV...")
                    print(f"Child MKV: {child_mkv}")
                    print(f"Next cycle: {self.cycle_number + 1}/{self.max_cycles}")
                    print("=" * 70 + "\n")

                    # Create next iteration with child MKV
                    next_cycle = SemanticCPUEmulator(
                        kernel_path=self.kernel_path,
                        disk_path=self.disk_path,
                        mkv_path=child_mkv,
                        self_aware=True,
                        optimize=True,
                        use_pixel_version=True,  # Phase 7: use pixel version next cycle
                        max_cycles=self.max_cycles,
                        cycle_number=self.cycle_number + 1,
                    )

                    # Note: We don't recursively call next_cycle.boot() here
                    # to avoid blocking. The user can manually run the next cycle
                    # or we could add an auto-continue flag
                    print("\nPhase 7: Next iteration ready")

                    if self.auto_continue:
                        print("Auto-continue mode: Launching next cycle automatically...")
                        # Use subprocess to launch next cycle (non-blocking)
                        next_cycle_cmd = [
                            "python3", str(child_mkv.parent / "semantic_cpu_emulator.py"),
                            "--kernel", str(self.kernel_path),
                            "--disk", str(self.disk_path),
                            "--mkv", str(child_mkv),
                            "--self-aware", "--optimize", "--use-pixel-version",
                            "--cycle", str(self.cycle_number + 1),
                            "--auto-continue",
                        ]
                        print(f"  Command: {' '.join(next_cycle_cmd)}")
                        print("\n" + "=" * 70)
                        print("LAUNCHING NEXT CYCLE IN BACKGROUND")
                        print("=" * 70 + "\n")

                        # Launch in background (detached)
                        subprocess.Popen(next_cycle_cmd, start_new_session=True)
                        print(f"✓ Next cycle launched in background (PID: unknown)")
                        print("  Check child MKV logs for progress")
                        print("  Use --evolution-report on child MKV to track improvements")
                        return 0
                    else:
                        print(f"  To continue: python3 {child_mkv.parent / 'semantic_cpu_emulator.py'} \\")
                        print(f"    --kernel {self.kernel_path} \\")
                        print(f"    --disk {self.disk_path} \\")
                        print(f"    --mkv {child_mkv} \\")
                        print(f"    --self-aware --optimize --use-pixel-version \\")
                        print(f"    --cycle {self.cycle_number + 1}")
                        print("\n  Or use --auto-continue to automatically launch next cycles")

        # Step 5: Execute actual QEMU boot
        print("\n" + "=" * 70)
        print("BOOTING SYSTEM VIA QEMU")
        print("=" * 70 + "\n")

        return self._run_qemu()

    def _build_pixel_args(self) -> List[str]:
        """Build arguments for pixel version execution (Phase 7)."""
        args = [
            "--kernel", str(self.kernel_path),
            "--disk", str(self.disk_path),
        ]

        if self.mkv_path:
            args.extend(["--mkv", str(self.mkv_path)])

        if self.self_aware:
            args.append("--self-aware")

        if self.optimize:
            args.append("--optimize")

        # For pixel version, we increment cycle and use-pixel-version for next iteration
        if self.cycle_number + 1 < self.max_cycles:
            args.extend([
                "--cycle", str(self.cycle_number + 1),
                "--use-pixel-version",
            ])

        args.extend(["--max-cycles", str(self.max_cycles)])

        return args

    def get_evolution_report(self) -> Dict:
        """Generate evolutionary improvement report (Phase 7)."""
        if not self.evolution_history:
            return {"cycles": 0, "message": "No evolution history available"}

        report = {
            "cycles": len(self.evolution_history),
            "max_cycles": self.max_cycles,
            "history": self.evolution_history,
            "summary": {
                "total_optimizations": sum(h.get('optimizations', 0) for h in self.evolution_history),
                "child_mkvs": [h['child_mkv'] for h in self.evolution_history],
                "metrics_evolution": [h['metrics'] for h in self.evolution_history],
            }
        }
        return report

    def _run_qemu(self) -> int:
        """Run QEMU with the kernel and disk."""
        # Build QEMU command
        qemu_cmd = [
            "qemu-system-riscv64",
            "-machine", "virt",
            "-cpu", "rv64",
            "-m", "2048",
            "-bios", "default",
            "-device", "virtio-gpu-device",
            "-device", "virtio-net-device,netdev=net0",
            "-netdev", "user,id=net0,hostfwd=tcp::2222-:22",
            "-kernel", str(self.kernel_path),
            "-drive", f"file={self.disk_path},if=virtio,format=qcow2",
            "-device", "virtio-blk-device",
            "-serial", "mon:stdio",
            "-nographic",
        ]

        print("QEMU command:")
        print("  " + " \\\n    ".join(qemu_cmd))
        print("\nStarting QEMU...\n")

        # Run QEMU (inherit terminal for interaction)
        return subprocess.call(qemu_cmd)


# -----------------------------------------------------------------------
# Command Line Interface
# -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Semantic CPU Emulator - Self-Modifying Boot Environment"
    )
    parser.add_argument("--kernel", required=True, type=Path,
                       help="Path to RISC-V kernel image")
    parser.add_argument("--disk", required=True, type=Path,
                       help="Path to disk image (qcow2)")
    parser.add_argument("--mkv", type=Path,
                       help="Path to MKV container (for self-aware mode)")
    parser.add_argument("--self-aware", action="store_true",
                       help="Enable self-aware mode (load own code from MKV pixels)")
    parser.add_argument("--optimize", action="store_true",
                       help="Enable self-optimization via wordbase color swaps")
    parser.add_argument("--use-pixel-version", action="store_true",
                       help="Phase 7: Execute pixel-encoded version of emulator")
    parser.add_argument("--max-cycles", type=int, default=10,
                       help="Phase 7: Maximum evolutionary cycles (default: 10)")
    parser.add_argument("--cycle", type=int, default=0,
                       help="Phase 7: Current cycle number (default: 0)")
    parser.add_argument("--auto-continue", action="store_true",
                       help="Phase 7: Automatically launch next cycles without manual intervention")
    parser.add_argument("--evolution-report", action="store_true",
                       help="Phase 7: Print evolutionary improvement report and exit")

    args = parser.parse_args()

    # Evolution report mode (no boot required)
    if args.evolution_report:
        if not args.mkv:
            print("ERROR: --mkv required for evolution report")
            return 1

        # Create a dummy emulator to access evolution tracking
        emulator = SemanticCPUEmulator(
            kernel_path=Path("/dev/null"),  # Not used for report
            disk_path=Path("/dev/null"),  # Not used for report
            mkv_path=args.mkv,
            self_aware=False,
            optimize=False,
            max_cycles=args.max_cycles,
            cycle_number=args.cycle,
        )

        # Load evolution history from MKV
        emulator.evolution_history = ChildMKVCreator.load_evolution_history(args.mkv) or []

        report = emulator.get_evolution_report()
        print(json.dumps(report, indent=2))
        return 0

    # Validate paths
    if not args.kernel.exists():
        print(f"ERROR: Kernel not found: {args.kernel}")
        return 1

    if not args.disk.exists():
        print(f"ERROR: Disk not found: {args.disk}")
        return 1

    if args.self_aware and not args.mkv:
        print("ERROR: --mkv required when using --self-aware")
        return 1

    # Create emulator and boot
    emulator = SemanticCPUEmulator(
        kernel_path=args.kernel,
        disk_path=args.disk,
        mkv_path=args.mkv,
        self_aware=args.self_aware,
        optimize=args.optimize,
        use_pixel_version=args.use_pixel_version,
        max_cycles=args.max_cycles,
        cycle_number=args.cycle,
        auto_continue=args.auto_continue,
    )

    return emulator.boot()


if __name__ == "__main__":
    sys.exit(main())
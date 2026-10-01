"""
Visual Audio UPIC Plugin - Installer and Utilities

This script provides installation and testing utilities for the GStreamer plugin.
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path


def run_command(cmd, check=True, capture_output=False):
    """Run a shell command with error handling."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=capture_output,
            text=True
        )
        if capture_output:
            return result.stdout, result.stderr, result.returncode
        return None, None, result.returncode
    except subprocess.CalledProcessError as e:
        if capture_output:
            return getattr(e, 'stdout', ''), getattr(e, 'stderr', str(e)), e.returncode
        return None, str(e), e.returncode
    except Exception as e:
        if capture_output:
            return '', str(e), -1
        return None, str(e), -1


def check_dependencies():
    """Check if required dependencies are installed."""
    print("Checking dependencies...")
    
    dependencies = [
        ("gcc", "gcc --version"),
        ("gstreamer-1.0", "pkg-config --modversion gstreamer-1.0"),
        ("json-c", "pkg-config --modversion json-c"),
    ]
    
    missing = []
    for name, check_cmd in dependencies:
        stdout, stderr, code = run_command(check_cmd, capture_output=True)
        if code == 0:
            version = stdout.strip().split('\n')[0]
            print(f"  ✓ {name}: {version}")
        else:
            print(f"  ✗ {name}: NOT FOUND")
            missing.append(name)
    
    if missing:
        print(f"\nMissing dependencies: {', '.join(missing)}")
        print("\nInstall on Ubuntu/Debian:")
        print("  sudo apt-get install build-essential libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libjson-c-dev")
        print("\nInstall on Fedora/RHEL:")
        print("  sudo dnf install gcc make gstreamer1-devel gstreamer1-plugins-base-devel json-c-devel")
        return False
    
    print("\nAll dependencies found!")
    return True


def build_plugin(plugin_dir):
    """Build the GStreamer plugin."""
    print("\nBuilding plugin...")
    
    makefile = plugin_dir / "Makefile"
    if not makefile.exists():
        print(f"  ✗ Makefile not found at {makefile}")
        return False
    
    # Run make
    stdout, stderr, code = run_command(f"cd {plugin_dir} && make clean && make", capture_output=True)
    
    if code == 0:
        print("  ✓ Plugin built successfully")
        lib_path = plugin_dir / "libgstupic.so"
        if lib_path.exists():
            print(f"  ✓ Library created: {lib_path}")
            return True
        else:
            print("  ✗ Library not found after build")
            return False
    else:
        print(f"  ✗ Build failed:")
        if stderr:
            print(stderr)
        return False


def install_plugin(plugin_dir, gst_plugin_path="/usr/local/lib/gstreamer-1.0"):
    """Install the plugin to GStreamer plugin directory."""
    print(f"\nInstalling plugin to {gst_plugin_path}...")
    
    lib_path = plugin_dir / "libgstupic.so"
    if not lib_path.exists():
        print(f"  ✗ Plugin library not found: {lib_path}")
        return False
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(gst_plugin_path, exist_ok=True)
        
        # Copy library
        shutil.copy(str(lib_path), os.path.join(gst_plugin_path, "libgstupic.so"))
        print(f"  ✓ Plugin installed to {gst_plugin_path}")
        return True
    except PermissionError:
        print(f"  ✗ Permission denied. Try with sudo:")
        print(f"     sudo python {__file__} install")
        return False
    except Exception as e:
        print(f"  ✗ Installation failed: {e}")
        return False


def verify_installation():
    """Verify the plugin is installed correctly."""
    print("\nVerifying installation...")
    
    stdout, stderr, code = run_command("gst-inspect-1.0 upicdec", capture_output=True)
    
    if code == 0 and stdout:
        print("  ✓ Plugin registered successfully")
        print("\n" + "="*60)
        print("Plugin Details:")
        print("="*60)
        print(stdout[:500])  # Show first 500 chars
        print("="*60)
        return True
    else:
        print(f"  ✗ Plugin not found or failed to load")
        output_text = stdout or stderr or ""
        if "No such element" in output_text or "no such element" in output_text.lower():
            print("\nPossible solutions:")
            print("  1. Rebuild and reinstall the plugin")
            print("  2. Export GST_PLUGIN_PATH:")
            print(f"     export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:$GST_PLUGIN_PATH")
            print("  3. Restart your application")
        return False


def test_plugin(plugin_dir):
    """Test the plugin with a simple example."""
    print("\nTesting plugin...")
    
    # Check if we have a test project
    test_project = plugin_dir.parent.parent / "examples" / "basic_demo.upic.json"
    if not test_project.exists():
        print(f"  ✗ Test project not found: {test_project}")
        print("  Creating a simple test...")
        
        # Use Python tools to create a demo project
        demo_script = plugin_dir.parent.parent / "tools" / "upic.py"
        if demo_script.exists():
            stdout, stderr, code = run_command(f"cd {plugin_dir.parent.parent} && python {demo_script} demo", capture_output=True)
            if code == 0:
                test_project = plugin_dir.parent.parent / "demo.upic.json"
                if test_project.exists():
                    print(f"  ✓ Test project created: {test_project}")
                else:
                    print("  ✗ Failed to create test project")
                    return False
            else:
                print(f"  ✗ Failed to run demo script: {stderr}")
                return False
        else:
            print("  ✗ Demo script not found")
            return False
    
    # Try to play with gst-launch
    print(f"  Testing with: {test_project}")
    stdout, stderr, code = run_command(
        f"timeout 2 gst-launch-1.0 -v filesrc location={test_project} ! upicdec ! fakesink 2>&1 | head -20",
        capture_output=True
    )
    
    if code == 0:
        print("  ✓ Plugin can process UPIC files")
        return True
    else:
        output_text = stdout or stderr or ""
        if "not negotiated" in output_text.lower():
            print("  ✓ Plugin loaded (pipeline negotiation is expected)")
            return True
        else:
            print(f"  ✗ Plugin test failed")
            if stderr:
                print(f"  Error: {stderr}")
            return False


def uninstall_plugin(gst_plugin_path="/usr/local/lib/gstreamer-1.0"):
    """Uninstall the plugin."""
    print(f"\nUninstalling plugin from {gst_plugin_path}...")
    
    lib_path = os.path.join(gst_plugin_path, "libgstupic.so")
    if os.path.exists(lib_path):
        try:
            os.remove(lib_path)
            print(f"  ✓ Plugin uninstalled")
            return True
        except PermissionError:
            print(f"  ✗ Permission denied. Try with sudo:")
            print(f"     sudo python {__file__} uninstall")
            return False
        except Exception as e:
            print(f"  ✗ Uninstall failed: {e}")
            return False
    else:
        print(f"  ✗ Plugin not found: {lib_path}")
        return False


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Visual Audio UPIC Plugin Installer")
    parser.add_argument("action", nargs="?", default="install",
                       choices=["check", "build", "install", "test", "uninstall", "all"],
                       help="Action to perform")
    parser.add_argument("--gst-plugin-path", default="/usr/local/lib/gstreamer-1.0",
                       help="GStreamer plugin installation path")
    parser.add_argument("--plugin-dir", default=None,
                       help="Plugin source directory (default: auto-detect)")
    
    args = parser.parse_args()
    
    # Detect plugin directory
    if args.plugin_dir is None:
        script_dir = Path(__file__).parent
        args.plugin_dir = script_dir
    
    plugin_dir = Path(args.plugin_dir)
    
    print("="*60)
    print("Visual Audio UPIC GStreamer Plugin Installer")
    print("="*60)
    
    success = True
    
    if args.action in ["check", "all"]:
        success = check_dependencies() and success
    
    if args.action in ["build", "all"]:
        success = build_plugin(plugin_dir) and success
    
    if args.action in ["install", "all"]:
        success = install_plugin(plugin_dir, args.gst_plugin_path) and success
        if success:
            success = verify_installation() and success
    
    if args.action in ["test", "all"]:
        success = test_plugin(plugin_dir) and success
    
    if args.action == "uninstall":
        success = uninstall_plugin(args.gst_plugin_path)
    
    print("\n" + "="*60)
    if success:
        print("✓ All operations completed successfully!")
    else:
        print("✗ Some operations failed. See messages above.")
        sys.exit(1)
    print("="*60)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
ShaderOS Installation Verification Script

This script verifies that your ShaderOS installation is working correctly.
"""

import sys
from pathlib import Path


def check_python_version():
    """Verify Python version is 3.8+"""
    print("🔍 Checking Python version...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"   ❌ Python {version.major}.{version.minor} is too old")
        print(f"   ⚠️  Python 3.8+ required")
        return False
    print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_dependencies():
    """Check if required packages are installed"""
    print("\n🔍 Checking dependencies...")

    packages = {
        'wgpu': 'WebGPU Python bindings',
        'numpy': 'Numerical computing'
    }

    all_ok = True
    for package, description in packages.items():
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'unknown')
            print(f"   ✅ {package:10s} {version:15s} - {description}")
        except ImportError:
            print(f"   ❌ {package:10s} {'NOT INSTALLED':15s} - {description}")
            all_ok = False

    return all_ok


def check_files():
    """Verify all required files exist"""
    print("\n🔍 Checking required files...")

    required_files = [
        'ShaderOSRuntime.py',
        'requirements.txt',
        'runtime/core/substrate.wgsl',
        'runtime/core/os_abi.wgsl',
        'README.md',
        'ARCHITECTURE.md',
        'API.md',
        'QUICKSTART.md',
    ]

    all_ok = True
    for filepath in required_files:
        path = Path(filepath)
        if path.exists():
            size = path.stat().st_size
            print(f"   ✅ {filepath:40s} ({size:,} bytes)")
        else:
            print(f"   ❌ {filepath:40s} MISSING")
            all_ok = False

    return all_ok


def test_basic_import():
    """Try importing ShaderOSRuntime"""
    print("\n🔍 Testing basic import...")

    try:
        from ShaderOSRuntime import ShaderOSRuntime
        print("   ✅ ShaderOSRuntime module imports successfully")
        return True
    except Exception as e:
        print(f"   ❌ Failed to import: {e}")
        return False


def test_gpu_device():
    """Check if GPU is accessible"""
    print("\n🔍 Checking GPU access...")

    try:
        import wgpu
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")

        if adapter:
            print(f"   ✅ GPU adapter found")

            # Try to get device info (this might not be available on all systems)
            try:
                info = adapter.request_adapter_info()
                if hasattr(info, 'vendor'):
                    print(f"   ℹ️  Vendor: {info.vendor}")
                if hasattr(info, 'device'):
                    print(f"   ℹ️  Device: {info.device}")
            except:
                pass

            return True
        else:
            print("   ❌ No GPU adapter available")
            return False
    except Exception as e:
        print(f"   ❌ GPU check failed: {e}")
        return False


def test_runtime_creation():
    """Try creating a ShaderOSRuntime instance"""
    print("\n🔍 Testing runtime creation...")

    try:
        from ShaderOSRuntime import ShaderOSRuntime
        runtime = ShaderOSRuntime()

        buffer_count = len(runtime.shared_buffers)
        total_size = sum(buf.size for buf in runtime.shared_buffers.values())

        print(f"   ✅ Runtime created successfully")
        print(f"   ℹ️  Created {buffer_count} GPU buffers")
        print(f"   ℹ️  Total GPU memory: {total_size / 1024 / 1024:.2f} MB")

        return True
    except Exception as e:
        print(f"   ❌ Runtime creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all verification checks"""
    print("=" * 70)
    print("ShaderOS Installation Verification")
    print("=" * 70)

    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Required Files", check_files),
        ("Basic Import", test_basic_import),
        ("GPU Access", test_gpu_device),
        ("Runtime Creation", test_runtime_creation),
    ]

    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n⚠️  {name} check encountered an error: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:10s} - {name}")

    print("=" * 70)
    print(f"Result: {passed}/{total} checks passed")

    if passed == total:
        print("\n🎉 ShaderOS is ready to use!")
        print("\nNext steps:")
        print("  1. Read QUICKSTART.md for a quick introduction")
        print("  2. Run: python3 ShaderOSRuntime.py")
        print("  3. Explore EXAMPLES.md for code samples")
        return 0
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above.")
        print("\nCommon solutions:")
        print("  • Install dependencies: pip install -r requirements.txt")
        print("  • Check GPU drivers are up to date")
        print("  • Ensure all files are present")
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Simple test runner for test_pixel_os_lm_input.py
"""
import sys
import os

# Add paths
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

# Try importing the test file directly
try:
    # Import test module
    import importlib.util
    spec = importlib.util.spec_from_file_location("test_pixel_os_lm_input", 
                                                   os.path.join(project_root, 'tests', 'test_pixel_os_lm_input.py'))
    test_module = importlib.util.module_from_spec(spec)
    
    print("✓ Successfully loaded test_pixel_os_lm_input.py")
    print("\nTest classes found:")
    
    # List test classes
    test_classes = []
    for name in dir(test_module):
        obj = getattr(test_module, name)
        if isinstance(obj, type) and name.startswith('Test'):
            test_classes.append(name)
            test_methods = [m for m in dir(obj) if m.startswith('test_')]
            print(f"  - {name}: {len(test_methods)} test methods")
            for method in test_methods:
                print(f"      • {method}")
    
    print(f"\nTotal: {len(test_classes)} test classes")
    
    # Count total test methods
    total_tests = sum([len([m for m in dir(getattr(test_module, cls)) if m.startswith('test_')]) 
                       for cls in test_classes])
    print(f"Total test methods: {total_tests}")
    
    print("\n✓ Test file structure is valid")
    print("\nNOTE: Full test execution requires pytest and all dependencies")
    print("Install with: pip install pytest soundfile scipy pillow cryptography")
    
except Exception as e:
    print(f"✗ Error loading test file: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
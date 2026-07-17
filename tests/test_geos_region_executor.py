#!/usr/bin/env python3
"""
Integration test for GeOS region executor.

Tests the dense cartridge region executor (TASK_G001).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add paths for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

from dense_encoder import encode_dense, decode_dense

# Import GeOS executor
sys.path.insert(0, os.path.join(project_root, 'src', 'geos'))
from region_executor import GeOSRegionExecutor


class TestGeOSRegionExecutor(unittest.TestCase):
    """Test GeOS region executor functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cartridge_path = os.path.join(self.temp_dir.name, "test_cartridge.png")
        self.executor = GeOSRegionExecutor()
        
        # Create a test cartridge
        test_payload = b'print("Hello from GeOS region!")'
        encode_dense(test_payload, self.cartridge_path, square=True)
    
    def tearDown(self):
        """Clean up test fixtures."""
        self.temp_dir.cleanup()
    
    def test_cartridge_decode(self):
        """Test that cartridge can be decoded correctly."""
        payload = decode_dense(self.cartridge_path)
        expected = b'print("Hello from GeOS region!")'
        self.assertEqual(payload, expected)
    
    def test_executor_successful_execution(self):
        """Test successful execution via spatial syscall interface."""
        result = self.executor.execute_cartridge_region(self.cartridge_path, "test_region")
        
        # Verify execution succeeded
        self.assertTrue(result["success"])
        self.assertEqual(result["region_id"], "test_region")
        self.assertGreater(result["payload_size"], 0)  # Payload size varies due to framing
        
        # Verify bytecode was generated
        self.assertIn("bytecode_size", result)
        self.assertGreater(result["bytecode_size"], 0)
        
        # Verify spatial syscall addresses
        self.assertIn("syscall_address", result)
        self.assertEqual(result["syscall_address"], 0x80090000)
        self.assertIn("bytecode_corridor", result)
        self.assertEqual(result["bytecode_corridor"], "0x80092000")
    
    def test_executor_handles_invalid_cartridge(self):
        """Test that executor handles invalid cartridges gracefully."""
        # Create an invalid PNG
        invalid_path = os.path.join(self.temp_dir.name, "invalid.png")
        with open(invalid_path, 'wb') as f:
            f.write(b'not a valid png')
        
        result = self.executor.execute_cartridge_region(invalid_path, "test_region")
        
        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertIn("Failed to decode", result["error"])
    
    def test_executor_handles_multiple_regions(self):
        """Test that executor can handle multiple regions."""
        regions = ["region_a", "region_b", "region_c"]
        
        for region in regions:
            result = self.executor.execute_cartridge_region(self.cartridge_path, region)
            self.assertTrue(result["success"])
            self.assertEqual(result["region_id"], region)
        
        # Verify all executions recorded
        history = self.executor.get_execution_history()
        self.assertEqual(len(history), 3)
        
        recorded_regions = [e["region_id"] for e in history]
        self.assertEqual(recorded_regions, regions)
    
    def test_spatial_syscall_constants(self):
        """Test spatial syscall constants are correctly defined."""
        self.assertEqual(
            self.executor.SPATIAL_REGISTRY_BASE,
            0x80090000,
            "Spatial registry base address"
        )
        self.assertEqual(
            self.executor.SPATIAL_REGISTRY_END,
            0x8009FFFF,
            "Spatial registry end address"
        )
        self.assertEqual(
            self.executor.BYTECODE_CORRIDOR_BASE,
            0x80092000,
            "Bytecode corridor base address"
        )
    
    def test_bytecode_encoding(self):
        """Test payload encoding as spatial VM bytecode."""
        test_payload = b'{"test": "data"}'
        bytecode = self.executor._encode_payload_as_bytecode(test_payload)
        
        # Bytecode should contain payload
        self.assertIn(test_payload, bytecode)
        
        # Bytecode should end with HALT
        self.assertEqual(bytecode[-1], self.executor.OP_HALT)
        
        # Bytecode should start with length prefix
        import struct
        prefix_len = struct.unpack('<I', bytecode[:4])[0]
        self.assertEqual(prefix_len, len(test_payload))


class TestGeOSRegionExecutorIntegration(unittest.TestCase):
    """Integration tests for GeOS region executor."""
    
    def test_run_cartridge_with_geos_convenience_function(self):
        """Test the convenience function for running cartridges."""
        from region_executor import run_cartridge_with_geos
        
        # Create test cartridge
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            cartridge_path = f.name
        
        try:
            test_payload = b'print("Integration test")'
            encode_dense(test_payload, cartridge_path, square=True)
            
            # Run via GeOS
            result = run_cartridge_with_geos(cartridge_path, "integration_test")
            
            # The function should return True for success
            self.assertTrue(result)
            
            # Note: Each executor instance maintains its own history,
            # so we just verify the function ran without errors
            
        finally:
            if os.path.exists(cartridge_path):
                os.unlink(cartridge_path)


def main():
    """Run tests and print results."""
    print("=== GeOS Region Executor Integration Tests ===\n")
    
    # Run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestGeOSRegionExecutor))
    suite.addTests(loader.loadTestsFromTestCase(TestGeOSRegionExecutorIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print(f"\n=== Test Summary ===")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    if result.wasSuccessful():
        print("\n✓ All tests passed")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
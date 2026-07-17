#!/usr/bin/env python3
"""
Integration test with GeOS hypervisor for TASK_G001.

This script tests the dense cartridge region executor with real GeOS hypervisor
when available. When GeOS is not running, it validates the interface implementation.
"""

import os
import sys
import socket
import json
import struct
import tempfile
from pathlib import Path

# Add paths for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'tools'))

from dense_encoder import encode_dense, decode_dense
sys.path.insert(0, os.path.join(project_root, 'src', 'geos'))
from region_executor import GeOSRegionExecutor


class GeOSHypervisorTest:
    """Test GeOS hypervisor integration."""
    
    GEOS_SOCKET_PATH = "/tmp/geo_cmd.sock"
    
    def __init__(self):
        self.geos_available = self._check_geos_available()
        self.test_results = []
    
    def _check_geos_available(self) -> bool:
        """Check if GeOS hypervisor is available via socket."""
        try:
            if not os.path.exists(self.GEOS_SOCKET_PATH):
                return False
            
            # Try to connect
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.connect(self.GEOS_SOCKET_PATH)
            sock.close()
            return True
        except (socket.timeout, ConnectionRefusedError, FileNotFoundError):
            return False
    
    def test_decode_cartridge(self) -> bool:
        """Test decoding a dense cartridge."""
        try:
            # Create test cartridge
            test_payload = b'print("Hello from GeOS!")'
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                cartridge_path = f.name
            
            try:
                encode_dense(test_payload, cartridge_path, square=True)
                decoded = decode_dense(cartridge_path)
                
                if decoded == test_payload:
                    print("✓ Cartridge decode: PASSED")
                    return True
                else:
                    print("✗ Cartridge decode: FAILED (payload mismatch)")
                    return False
            finally:
                if os.path.exists(cartridge_path):
                    os.unlink(cartridge_path)
        except Exception as e:
            print(f"✗ Cartridge decode: FAILED ({e})")
            return False
    
    def test_bytecode_generation(self) -> bool:
        """Test spatial VM bytecode generation."""
        try:
            executor = GeOSRegionExecutor()
            test_payload = b'{"test": "data"}'
            
            bytecode = executor._encode_payload_as_bytecode(test_payload)
            
            # Verify bytecode structure
            if len(bytecode) == 0:
                print("✗ Bytecode generation: FAILED (empty bytecode)")
                return False
            
            # Verify payload is in bytecode
            if test_payload not in bytecode:
                print("✗ Bytecode generation: FAILED (payload not in bytecode)")
                return False
            
            # Verify HALT instruction at end
            if bytecode[-1] != executor.OP_HALT:
                print("✗ Bytecode generation: FAILED (missing HALT)")
                return False
            
            # Verify length prefix
            prefix_len = struct.unpack('<I', bytecode[:4])[0]
            if prefix_len != len(test_payload):
                print("✗ Bytecode generation: FAILED (wrong length prefix)")
                return False
            
            print("✓ Bytecode generation: PASSED")
            return True
        except Exception as e:
            print(f"✗ Bytecode generation: FAILED ({e})")
            return False
    
    def test_spatial_syscall_request(self) -> bool:
        """Test spatial syscall request creation."""
        try:
            executor = GeOSRegionExecutor()
            test_payload = b'print("test")'
            bytecode = executor._encode_payload_as_bytecode(test_payload)
            
            request = executor._create_spatial_syscall_request(
                executor.OP_HOSTCALL,
                "test_region",
                bytecode
            )
            
            # Verify request structure
            if len(request) < 1 + 16 + 4:  # opcode + region_id + length_prefix
                print("✗ Spatial syscall request: FAILED (request too short)")
                return False
            
            # Verify opcode
            opcode = request[0]
            if opcode != executor.OP_HOSTCALL:
                print("✗ Spatial syscall request: FAILED (wrong opcode)")
                return False
            
            # Verify region_id encoding
            region_id = request[1:17].rstrip(b'\x00').decode('utf-8')
            if region_id != "test_region":
                print("✗ Spatial syscall request: FAILED (wrong region_id)")
                return False
            
            # Verify bytecode is in request
            if bytecode not in request:
                print("✗ Spatial syscall request: FAILED (bytecode not in request)")
                return False
            
            print("✓ Spatial syscall request: PASSED")
            return True
        except Exception as e:
            print(f"✗ Spatial syscall request: FAILED ({e})")
            return False
    
    def test_full_execution_pipeline(self) -> bool:
        """Test full execution pipeline from cartridge to spatial syscall."""
        try:
            executor = GeOSRegionExecutor()
            
            # Create test cartridge
            test_payload = b'print("Full pipeline test")'
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                cartridge_path = f.name
            
            try:
                encode_dense(test_payload, cartridge_path, square=True)
                
                # Execute via GeOS
                result = executor.execute_cartridge_region(cartridge_path, "pipeline_test")
                
                # Verify result structure
                if not result.get("success"):
                    print("✗ Full execution pipeline: FAILED (execution failed)")
                    return False
                
                required_keys = ["success", "region_id", "payload_size", "bytecode_size",
                               "syscall_address", "bytecode_corridor"]
                for key in required_keys:
                    if key not in result:
                        print(f"✗ Full execution pipeline: FAILED (missing key: {key})")
                        return False
                
                # Verify addresses
                if result["syscall_address"] != 0x80090000:
                    print("✗ Full execution pipeline: FAILED (wrong syscall address)")
                    return False
                
                if result["bytecode_corridor"] != "0x80092000":
                    print("✗ Full execution pipeline: FAILED (wrong bytecode corridor)")
                    return False
                
                # Verify sizes are reasonable
                if result["payload_size"] == 0:
                    print("✗ Full execution pipeline: FAILED (zero payload size)")
                    return False
                
                if result["bytecode_size"] == 0:
                    print("✗ Full execution pipeline: FAILED (zero bytecode size)")
                    return False
                
                print("✓ Full execution pipeline: PASSED")
                return True
            finally:
                if os.path.exists(cartridge_path):
                    os.unlink(cartridge_path)
        except Exception as e:
            print(f"✗ Full execution pipeline: FAILED ({e})")
            return False
    
    def test_multiple_regions(self) -> bool:
        """Test execution in multiple regions."""
        try:
            executor = GeOSRegionExecutor()
            
            # Create test cartridge
            test_payload = b'print("Multi-region test")'
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                cartridge_path = f.name
            
            try:
                encode_dense(test_payload, cartridge_path, square=True)
                
                # Execute in multiple regions
                regions = ["region_a", "region_b", "region_c"]
                for region in regions:
                    result = executor.execute_cartridge_region(cartridge_path, region)
                    if not result.get("success"):
                        print(f"✗ Multiple regions: FAILED (region {region})")
                        return False
                
                # Verify execution history
                history = executor.get_execution_history()
                if len(history) != len(regions):
                    print("✗ Multiple regions: FAILED (wrong history size)")
                    return False
                
                recorded_regions = [e["region_id"] for e in history]
                if recorded_regions != regions:
                    print("✗ Multiple regions: FAILED (wrong region order)")
                    return False
                
                print("✓ Multiple regions: PASSED")
                return True
            finally:
                if os.path.exists(cartridge_path):
                    os.unlink(cartridge_path)
        except Exception as e:
            print(f"✗ Multiple regions: FAILED ({e})")
            return False
    
    def test_geos_socket_connection(self) -> bool:
        """Test connection to GeOS hypervisor socket (if available)."""
        if not self.geos_available:
            print("⚠ GeOS socket connection: SKIPPED (GeOS not available)")
            return True  # Not a failure if GeOS is not running
        
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect(self.GEOS_SOCKET_PATH)
            
            # Send a simple ping command
            cmd = {"opcode": "ping"}
            sock.sendall((json.dumps(cmd) + "\n").encode('utf-8'))
            
            # Receive response
            response = sock.recv(4096).decode('utf-8').strip()
            sock.close()
            
            print(f"✓ GeOS socket connection: PASSED (response: {response})")
            return True
        except Exception as e:
            print(f"✗ GeOS socket connection: FAILED ({e})")
            return False
    
    def run_all_tests(self) -> int:
        """Run all integration tests."""
        print("=== GeOS Hypervisor Integration Tests ===\n")
        print(f"GeOS Available: {self.geos_available}")
        print(f"Socket Path: {self.GEOS_SOCKET_PATH}\n")
        
        # Run tests
        tests = [
            ("Cartridge Decode", self.test_decode_cartridge),
            ("Bytecode Generation", self.test_bytecode_generation),
            ("Spatial Syscall Request", self.test_spatial_syscall_request),
            ("Full Execution Pipeline", self.test_full_execution_pipeline),
            ("Multiple Regions", self.test_multiple_regions),
            ("GeOS Socket Connection", self.test_geos_socket_connection),
        ]
        
        for test_name, test_func in tests:
            print(f"\n{test_name}:")
            result = test_func()
            self.test_results.append((test_name, result))
        
        # Print summary
        print("\n" + "="*60)
        print("=== Test Summary ===")
        
        passed = sum(1 for _, result in self.test_results if result)
        total = len(self.test_results)
        skipped = sum(1 for _, result in self.test_results if result and "SKIPPED" in str(result))
        
        for test_name, result in self.test_results:
            status = "PASS" if result else "FAIL"
            print(f"  {test_name}: {status}")
        
        print(f"\nTotal: {passed}/{total} passed")
        if skipped > 0:
            print(f"Skipped: {skipped} (GeOS not available)")
        
        # Exit code
        if passed == total:
            print("\n✓ All tests passed")
            return 0
        else:
            print("\n✗ Some tests failed")
            return 1


def main():
    """Run integration tests."""
    tester = GeOSHypervisorTest()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
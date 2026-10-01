#!/usr/bin/env python3
"""
Payload Testing Suite: Validate Visual Audio pipeline with real production payloads.

This tests the complete workflow with diverse payload types:
1. Complex Python modules (imports, subprocess, real logic)
2. Large text data (50KB+ files)
3. Binary data (exact byte preservation)
4. Batch directory operations (all tools/*.py)
5. Mixed content types

Output: Test vectors and metrics for GeOS integration baseline.

Usage:
    python3 tools/test_payload_suite.py
    python3 tools/test_payload_suite.py --verbose
    python3 tools/test_payload_suite.py --category python
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple
import time


class PayloadTester:
    """Test visual_audio.mkv with diverse payload types."""

    def __init__(self, container_path: str = "visual_audio.mkv", verbose: bool = False):
        self.container_path = container_path
        self.verbose = verbose
        self.results = {
            "passed": [],
            "failed": [],
            "metrics": {},
            "payloads_tested": []
        }

    def log(self, message: str):
        """Print message if verbose."""
        if self.verbose:
            print(f"  {message}")

    def calculate_hash(self, data: bytes) -> str:
        """Calculate SHA256 hash of data."""
        return hashlib.sha256(data).hexdigest()

    def add_to_container(self, source_path: Path, name: str, role: str = "content") -> bool:
        """Add file to container."""
        result = subprocess.run([
            "python3", "tools/va_container.py", "add",
            self.container_path, str(source_path),
            "--name", name,
            "--role", role
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            self.log(f"Added: {name}")
            return True
        else:
            print(f"✗ Failed to add {name}: {result.stderr}")
            return False

    def extract_from_container(self, name: str) -> bytes:
        """Extract file from container."""
        result = subprocess.run([
            "python3", "tools/va_container.py", "cat",
            self.container_path, name
        ], capture_output=True)
        
        if result.returncode == 0:
            return result.stdout
        else:
            error_msg = result.stderr.decode() if result.stderr else "Unknown error"
            raise RuntimeError(f"Failed to extract {name}: {error_msg}")

    def verify_round_trip(self, name: str, original_data: bytes) -> Dict:
        """Verify byte-perfect round-trip."""
        start_time = time.time()
        
        try:
            extracted_data = self.extract_from_container(name)
            extract_time = time.time() - start_time
            
            original_hash = self.calculate_hash(original_data)
            extracted_hash = self.calculate_hash(extracted_data)
            
            is_byte_perfect = original_data == extracted_data
            hashes_match = original_hash == extracted_hash
            
            metrics = {
                "name": name,
                "original_size": len(original_data),
                "extracted_size": len(extracted_data),
                "extract_time_ms": round(extract_time * 1000, 2),
                "original_hash": original_hash,
                "extracted_hash": extracted_hash,
                "byte_perfect": is_byte_perfect,
                "hash_match": hashes_match,
                "size_match": len(original_data) == len(extracted_data)
            }
            
            if is_byte_perfect and hashes_match and metrics["size_match"]:
                self.results["passed"].append(name)
                self.log(f"✓ Byte-perfect round-trip: {name}")
            else:
                self.results["failed"].append({
                    "name": name,
                    "metrics": metrics,
                    "reason": "Mismatch detected"
                })
                print(f"✗ Round-trip failed: {name}")
                if not metrics["size_match"]:
                    print(f"  Size mismatch: {len(original_data)} vs {len(extracted_data)}")
                if not hashes_match:
                    print(f"  Hash mismatch")
            
            return metrics
            
        except Exception as e:
            self.results["failed"].append({
                "name": name,
                "metrics": {},
                "reason": str(e)
            })
            print(f"✗ Exception during round-trip: {name}")
            print(f"  {e}")
            return None

    def test_complex_python_module(self) -> Dict:
        """Test 1: Complex Python module with imports and subprocess."""
        print("\n" + "=" * 70)
        print("TEST 1: Complex Python Module")
        print("=" * 70)
        
        source_path = Path("tools/speak.py")
        if not source_path.exists():
            print(f"✗ Source not found: {source_path}")
            return {}
        
        original_data = source_path.read_bytes()
        name = "test_complex_python/speak.py"
        
        print(f"Source: {source_path}")
        print(f"Size: {len(original_data)} bytes")
        
        # Add to container
        if not self.add_to_container(source_path, name):
            return {}
        
        # Verify round-trip
        metrics = self.verify_round_trip(name, original_data)
        if metrics:
            self.results["payloads_tested"].append({
                "category": "complex_python",
                "name": name,
                "metrics": metrics
            })
        
        return metrics or {}

    def test_large_text_data(self) -> Dict:
        """Test 2: Large text data (50KB+)."""
        print("\n" + "=" * 70)
        print("TEST 2: Large Text Data")
        print("=" * 70)
        
        # Read ROADMAP.md section
        source_path = Path("ROADMAP.md")
        if not source_path.exists():
            print(f"✗ Source not found: {source_path}")
            return {}
        
        # Read first 1000 lines (~50KB)
        lines = source_path.read_text().split('\n')[:1000]
        original_data = '\n'.join(lines).encode('utf-8')
        
        if len(original_data) < 50000:
            print(f"⚠ Warning: Payload size {len(original_data)} < 50KB target")
        
        name = "test_large_text/roadmap_section.md"
        
        print(f"Source: ROADMAP.md (first 1000 lines)")
        print(f"Size: {len(original_data)} bytes")
        
        # Write temp file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.md') as tmp:
            tmp.write(original_data)
            tmp_path = Path(tmp.name)
        
        try:
            # Add to container
            if not self.add_to_container(tmp_path, name):
                return {}
            
            # Verify round-trip
            metrics = self.verify_round_trip(name, original_data)
            if metrics:
                self.results["payloads_tested"].append({
                    "category": "large_text",
                    "name": name,
                    "metrics": metrics
                })
            
            return metrics or {}
        finally:
            tmp_path.unlink()

    def test_binary_data(self) -> Dict:
        """Test 3: Binary data (exact byte preservation)."""
        print("\n" + "=" * 70)
        print("TEST 3: Binary Data")
        print("=" * 70)
        
        # Create test binary data (include all byte values 0-255)
        original_data = bytes(range(256)) * 100  # 25.6 KB
        
        name = "test_binary/all_bytes.bin"
        
        print(f"Source: Generated binary (all byte values 0-255)")
        print(f"Size: {len(original_data)} bytes")
        
        # Write temp file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.bin') as tmp:
            tmp.write(original_data)
            tmp_path = Path(tmp.name)
        
        try:
            # Add to container
            if not self.add_to_container(tmp_path, name):
                return {}
            
            # Verify round-trip
            metrics = self.verify_round_trip(name, original_data)
            if metrics:
                # Additional verification: all byte values present
                extracted_data = self.extract_from_container(name)
                byte_set = set(extracted_data)
                bytes_preserved = len(byte_set)
                
                metrics["binary_completeness"] = bytes_preserved == 256
                metrics["unique_bytes"] = bytes_preserved
                
                if bytes_preserved != 256:
                    print(f"⚠ Warning: Only {bytes_preserved}/256 unique bytes preserved")
                else:
                    self.log(f"✓ All 256 byte values preserved")
                
                self.results["payloads_tested"].append({
                    "category": "binary_data",
                    "name": name,
                    "metrics": metrics
                })
            
            return metrics or {}
        finally:
            tmp_path.unlink()

    def test_batch_directory(self) -> Dict:
        """Test 4: Batch directory (all tools/*.py files)."""
        print("\n" + "=" * 70)
        print("TEST 4: Batch Directory (tools/*.py)")
        print("=" * 70)
        
        tools_dir = Path("tools")
        if not tools_dir.exists():
            print(f"✗ Tools directory not found: {tools_dir}")
            return {}
        
        py_files = list(tools_dir.glob("*.py"))
        
        print(f"Found {len(py_files)} Python files in {tools_dir}")
        
        batch_results = []
        total_size = 0
        
        for py_file in py_files:
            original_data = py_file.read_bytes()
            name = f"test_batch_tools/{py_file.name}"
            
            total_size += len(original_data)
            
            # Add to container
            if not self.add_to_container(py_file, name):
                continue
            
            # Verify round-trip
            metrics = self.verify_round_trip(name, original_data)
            if metrics:
                batch_results.append({
                    "name": name,
                    "metrics": metrics
                })
                self.results["payloads_tested"].append({
                    "category": "batch_directory",
                    "name": name,
                    "metrics": metrics
                })
        
        print(f"\nBatch Summary:")
        print(f"  Files tested: {len(batch_results)}")
        print(f"  Total size: {total_size} bytes")
        print(f"  Passed: {len([r for r in batch_results if r['metrics']['byte_perfect']])}")
        print(f"  Failed: {len([r for r in batch_results if not r['metrics']['byte_perfect']])}")
        
        return {
            "total_files": len(batch_results),
            "total_size": total_size,
            "passed": len([r for r in batch_results if r['metrics']['byte_perfect']]),
            "failed": len([r for r in batch_results if not r['metrics']['byte_perfect']]),
            "results": batch_results
        }

    def test_mixed_content(self) -> Dict:
        """Test 5: Mixed content types."""
        print("\n" + "=" * 70)
        print("TEST 5: Mixed Content Types")
        print("=" * 70)
        
        mixed_files = [
            ("README.md", "markdown"),
            ("docs/CONTAINER_README.md", "markdown"),
            ("requirements.txt", "text"),
            (".gitignore", "text")
        ]
        
        print(f"Testing {len(mixed_files)} mixed content files")
        
        mixed_results = []
        
        for file_path, content_type in mixed_files:
            source = Path(file_path)
            if not source.exists():
                print(f"⚠ Skipping {file_path} (not found)")
                continue
            
            original_data = source.read_bytes()
            name = f"test_mixed/{content_type}/{source.name}"
            
            # Add to container
            if not self.add_to_container(source, name):
                continue
            
            # Verify round-trip
            metrics = self.verify_round_trip(name, original_data)
            if metrics:
                metrics["content_type"] = content_type
                mixed_results.append({
                    "name": name,
                    "content_type": content_type,
                    "metrics": metrics
                })
                self.results["payloads_tested"].append({
                    "category": "mixed_content",
                    "name": name,
                    "metrics": metrics
                })
        
        print(f"\nMixed Content Summary:")
        for result in mixed_results:
            status = "✓" if result["metrics"]["byte_perfect"] else "✗"
            print(f"  {status} {result['content_type']}: {result['name']}")
        
        return {
            "total_files": len(mixed_results),
            "results": mixed_results
        } or {}

    def get_container_metrics(self) -> Dict:
        """Get container growth metrics."""
        print("\n" + "=" * 70)
        print("CONTAINER METRICS")
        print("=" * 70)
        
        result = subprocess.run([
            "python3", "tools/va_container.py", "ls",
            self.container_path
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"✗ Failed to list container: {result.stderr}")
            return {}
        
        lines = result.stdout.strip().split('\n')
        
        # Parse entry count
        if lines:
            first_line = lines[0]
            entry_count = int(first_line.split(',')[1].split()[0])
            
            # Get file size
            container_path = Path(self.container_path)
            container_size = container_path.stat().st_size
            
            # Count by role
            role_counts = {}
            for line in lines[1:]:
                if '[' in line and ']' in line:
                    role = line.split('[')[1].split(']')[0]
                    role_counts[role] = role_counts.get(role, 0) + 1
            
            metrics = {
                "entry_count": entry_count,
                "container_size_bytes": container_size,
                "container_size_mb": round(container_size / (1024 * 1024), 2),
                "role_distribution": role_counts
            }
            
            print(f"Total entries: {entry_count}")
            print(f"Container size: {metrics['container_size_mb']} MB")
            print(f"Role distribution:")
            for role, count in sorted(role_counts.items()):
                print(f"  {role}: {count}")
            
            self.results["metrics"]["container"] = metrics
            return metrics
        
        return {}

    def generate_report(self) -> str:
        """Generate test report."""
        report = []
        
        report.append("=" * 70)
        report.append("PAYLOAD TESTING SUITE REPORT")
        report.append("=" * 70)
        
        # Summary
        passed = len(self.results["passed"])
        failed = len(self.results["failed"])
        total = passed + failed
        
        report.append(f"\nSUMMARY:")
        report.append(f"  Total payloads tested: {total}")
        report.append(f"  Passed: {passed}")
        report.append(f"  Failed: {failed}")
        report.append(f"  Success rate: {passed/total*100:.1f}%")
        
        # Failed tests
        if failed > 0:
            report.append(f"\nFAILED TESTS:")
            for failure in self.results["failed"]:
                report.append(f"  - {failure.get('name', 'unknown')}")
                report.append(f"    Reason: {failure.get('reason', 'unknown')}")
        
        # Performance metrics
        if self.results["payloads_tested"]:
            total_bytes = sum(p["metrics"]["original_size"] for p in self.results["payloads_tested"])
            total_extract_time = sum(p["metrics"]["extract_time_ms"] for p in self.results["payloads_tested"])
            
            avg_extract_time = total_extract_time / len(self.results["payloads_tested"])
            throughput = (total_bytes / 1024) / (total_extract_time / 1000)  # KB/s
            
            report.append(f"\nPERFORMANCE METRICS:")
            report.append(f"  Total data tested: {total_bytes / 1024:.2f} KB")
            report.append(f"  Average extract time: {avg_extract_time:.2f} ms")
            report.append(f"  Throughput: {throughput:.2f} KB/s")
        
        # Container metrics
        if "container" in self.results["metrics"]:
            cm = self.results["metrics"]["container"]
            report.append(f"\nCONTAINER METRICS:")
            report.append(f"  Entry count: {cm['entry_count']}")
            report.append(f"  Container size: {cm['container_size_mb']} MB")
            report.append(f"  Role distribution: {cm['role_distribution']}")
        
        # Categories tested
        categories = {}
        for payload in self.results["payloads_tested"]:
            cat = payload["category"]
            categories[cat] = categories.get(cat, 0) + 1
        
        report.append(f"\nCATEGORIES TESTED:")
        for cat, count in sorted(categories.items()):
            report.append(f"  {cat}: {count}")
        
        report.append("=" * 70)
        
        return "\n".join(report)

    def run_all_tests(self) -> bool:
        """Run all payload tests."""
        print("=" * 70)
        print("PAYLOAD TESTING SUITE")
        print(f"Container: {self.container_path}")
        print("=" * 70)
        
        start_time = time.time()
        
        # Run tests
        self.test_complex_python_module()
        self.test_large_text_data()
        self.test_binary_data()
        self.test_batch_directory()
        self.test_mixed_content()
        
        # Get container metrics
        self.get_container_metrics()
        
        total_time = time.time() - start_time
        self.results["metrics"]["total_test_time"] = total_time
        
        # Generate report
        report = self.generate_report()
        print(report)
        
        # Save report
        report_path = Path("payload_test_report.json")
        report_path.write_text(json.dumps(self.results, indent=2))
        print(f"\nFull report saved to: {report_path}")
        
        # Exit code
        return len(self.results["failed"]) == 0


def main():
    parser = argparse.ArgumentParser(description="Payload testing suite for visual_audio.mkv")
    
    parser.add_argument(
        "--container", "-c",
        default="visual_audio.mkv",
        help="Path to visual_audio.mkv container"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--category",
        choices=["python", "large_text", "binary", "batch", "mixed"],
        help="Run specific category test only"
    )
    
    args = parser.parse_args()
    
    tester = PayloadTester(container_path=args.container, verbose=args.verbose)
    
    if args.category:
        # Run specific test
        test_map = {
            "python": tester.test_complex_python_module,
            "large_text": tester.test_large_text_data,
            "binary": tester.test_binary_data,
            "batch": tester.test_batch_directory,
            "mixed": tester.test_mixed_content
        }
        
        test_map[args.category]()
        tester.get_container_metrics()
        print(tester.generate_report())
        return 0
    else:
        # Run all tests
        success = tester.run_all_tests()
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
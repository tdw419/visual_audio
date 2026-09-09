#!/usr/bin/env python3
"""
VM Pixel Flow Monitor - Inside the guest VM

Monitors virtio-blk block device I/O patterns to analyze pixel driver behavior
and provide insights for driver optimization.

Run inside the pixel-booted Ubuntu guest VM.

Usage:
    python3 tools/vm_pixel_monitor.py --duration 60 --output /tmp/pixel_analysis.json
    python3 tools/vm_pixel_monitor.py --realtime --trace /dev/vda
"""

import argparse
import json
import time
import os
import signal
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque
import threading


class PixelFlowMonitor:
    """Monitor pixel I/O patterns from inside the VM"""
    
    def __init__(self, device="/dev/vda", duration=60, realtime=False):
        self.device = device
        self.duration = duration
        self.realtime = realtime
        self.running = False
        
        # Monitoring metrics
        self.io_stats = {
            "total_reads": 0,
            "total_writes": 0,
            "total_bytes_read": 0,
            "total_bytes_written": 0,
            "read_operations": [],
            "write_operations": [],
            "sector_access_patterns": defaultdict(int),
            "temporal_patterns": defaultdict(list),
            "start_time": None,
            "end_time": None
        }
        
        # Analysis metrics
        self.analysis = {
            "sequential_reads": 0,
            "random_reads": 0,
            "sequential_writes": 0,
            "random_writes": 0,
            "hot_sectors": defaultdict(int),
            "cold_sectors": set(),
            "read_bursts": [],
            "write_bursts": [],
            "avg_read_size": 0,
            "avg_write_size": 0,
            "io_amplification": 1.0,
            "latency_samples": deque(maxlen=1000)
        }
        
        # Config
        self.sector_size = 512
        self.sequential_threshold = 8  # sectors considered sequential
        self.hot_sector_threshold = 10  # accesses to be considered "hot"
        self.start_timestamp = None  # For elapsed time calculation
        self.read_bursts_dict = {}  # For read burst tracking
        self.write_bursts_dict = {}  # For write burst tracking
        self.monitoring_method = "diskstats"  # Actual method used for this run

    def monitor_blocktrace(self):
        """Monitor block device using bpftrace, blktrace, or /proc/diskstats"""
        print(f"[Pixel Monitor] Starting monitoring of {self.device}")
        print(f"[Pixel Monitor] Duration: {self.duration}s, Realtime: {self.realtime}")
        print(f"[Pixel Monitor] {'='*60}")

        self.running = True
        self.start_timestamp = time.time()
        self.io_stats["start_time"] = datetime.now().isoformat()

        try:
            if self._try_bpftrace():
                # Preferred: per-request sector/size/latency via tracepoints, no root-owned CLI tool needed
                self.monitoring_method = "bpftrace"
                self._monitor_bpftrace()
            elif self._try_blktrace():
                self.monitoring_method = "blktrace"
                self._monitor_blktrace()
            else:
                # Fallback to /proc/diskstats monitoring (coarse: counts only, no per-request sector data)
                print("[Pixel Monitor] bpftrace/blktrace unavailable (bpftrace needs root), using /proc/diskstats")
                print("[Pixel Monitor] NOTE: pattern/hot-sector/burst/amplification analysis needs per-request data;")
                print("[Pixel Monitor]       re-run with 'sudo' to enable the bpftrace collector for real numbers.")
                self.monitoring_method = "diskstats"
                self._monitor_diskstats()

        except KeyboardInterrupt:
            print("\n[Pixel Monitor] Interrupted by user")
        finally:
            self.running = False
            self.io_stats["end_time"] = datetime.now().isoformat()

    def _try_blktrace(self):
        """Check if blktrace is available"""
        try:
            result = os.system("which blktrace > /dev/null 2>&1")
            return result == 0
        except:
            return False

    def _try_bpftrace(self):
        """Check if bpftrace is available and usable (it requires root)"""
        if os.geteuid() != 0:
            return False
        try:
            return os.system("which bpftrace > /dev/null 2>&1") == 0
        except:
            return False

    def _monitor_bpftrace(self):
        """Monitor using bpftrace tracepoints for real per-request sector/size/latency data"""
        bpf_script = (
            "tracepoint:block:block_rq_issue\n"
            "{\n"
            "    @start[args->sector] = nsecs;\n"
            '    printf("Q %lld %lld %s %d\\n", nsecs, args->sector, str(args->rwbs), args->nr_sector);\n'
            "}\n"
            "tracepoint:block:block_rq_complete\n"
            "{\n"
            "    $s = @start[args->sector];\n"
            "    if ($s) {\n"
            '        printf("C %lld %lld %d\\n", nsecs, args->sector, (nsecs - $s) / 1000);\n'
            "        delete(@start[args->sector]);\n"
            "    }\n"
            "}\n"
        )

        proc = subprocess.Popen(
            ["bpftrace", "-e", bpf_script],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1
        )

        def reader():
            for line in proc.stdout:
                self._process_bpftrace_line(line)

        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()

        try:
            last_print = self.start_timestamp
            while self.running and (time.time() - self.start_timestamp) < self.duration:
                time.sleep(0.5)
                now = time.time()
                if self.realtime and (now - last_print) >= 5:
                    self._print_realtime_stats()
                    last_print = now
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            reader_thread.join(timeout=2)

    def _process_bpftrace_line(self, line):
        """Parse one line of bpftrace collector output (Q=issue, C=complete)"""
        parts = line.split()
        if not parts:
            return
        try:
            if parts[0] == "Q" and len(parts) >= 5:
                ts_ns = int(parts[1])
                sector = int(parts[2])
                rwbs = parts[3]
                nr_sector = int(parts[4])
                timestamp_ms = ts_ns // 1_000_000
                op = {"timestamp": timestamp_ms, "sector": sector, "sectors": nr_sector}

                if "W" in rwbs:
                    self.io_stats["total_writes"] += 1
                    self.io_stats["total_bytes_written"] += nr_sector * self.sector_size
                    self.io_stats["write_operations"].append(op)
                    self._update_sector_access(sector, nr_sector, "write")
                else:
                    self.io_stats["total_reads"] += 1
                    self.io_stats["total_bytes_read"] += nr_sector * self.sector_size
                    self.io_stats["read_operations"].append(op)
                    self._update_sector_access(sector, nr_sector, "read")
            elif parts[0] == "C" and len(parts) >= 4:
                self.analysis["latency_samples"].append(int(parts[3]))
        except (ValueError, IndexError):
            pass

    def _monitor_blktrace(self):
        """Monitor using blktrace for detailed I/O tracing"""
        temp_dir = "/tmp/pixel_trace"
        os.makedirs(temp_dir, exist_ok=True)

        # Start blktrace
        trace_file = f"{temp_dir}/trace"
        cmd = ["blktrace", "-d", self.device, "-o", trace_file, "-a", "2,4,6,8"]  # Read all types
        print(f"[Pixel Monitor] Starting: {' '.join(cmd)}")

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        try:
            # Monitor for duration
            elapsed = 0
            last_print = self.start_timestamp

            while self.running and elapsed < self.duration:
                time.sleep(1)
                elapsed = time.time() - self.start_timestamp

                # Process accumulated traces
                self._process_blktrace_output(trace_file)

                if self.realtime and (time.time() - last_print) >= 5:
                    self._print_realtime_stats()
                    last_print = time.time()

        finally:
            # Cleanup
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            os.system(f"rm -rf {temp_dir}")
    
    def _monitor_diskstats(self):
        """Fallback monitoring using /proc/diskstats"""
        last_stats = self._read_diskstats()
        last_time = time.time()
        last_print = self.start_timestamp

        while self.running and (time.time() - self.start_timestamp) < self.duration:
            time.sleep(0.1)  # High-frequency polling
            
            current_stats = self._read_diskstats()
            current_time = time.time()
            elapsed = current_time - last_time
            
            if current_stats and last_stats:
                # Calculate deltas
                reads = current_stats["reads"] - last_stats["reads"]
                writes = current_stats["writes"] - last_stats["writes"]
                sectors_read = current_stats["sectors_read"] - last_stats["sectors_read"]
                sectors_written = current_stats["sectors_written"] - last_stats["sectors_written"]
                
                if reads > 0:
                    self.io_stats["total_reads"] += reads
                    self.io_stats["total_bytes_read"] += sectors_read * self.sector_size
                    
                if writes > 0:
                    self.io_stats["total_writes"] += writes
                    self.io_stats["total_bytes_written"] += sectors_written * self.sector_size
                    
                # Record temporal pattern
                timestamp = int(current_time * 1000)  # ms
                self.io_stats["temporal_patterns"][timestamp].append({
                    "reads": reads,
                    "writes": writes,
                    "sectors_read": sectors_read,
                    "sectors_written": sectors_written
                })
                
            last_stats = current_stats
            last_time = current_time

            if self.realtime and (current_time - last_print) >= 5:
                self._print_realtime_stats()
                last_print = current_time
    
    def _read_diskstats(self):
        """Read disk statistics from /proc/diskstats"""
        try:
            with open("/proc/diskstats", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 14 and self.device.split("/")[-1] in parts[2]:
                        return {
                            "reads": int(parts[3]),
                            "reads_merged": int(parts[4]),
                            "sectors_read": int(parts[5]),
                            "read_time_ms": int(parts[6]),
                            "writes": int(parts[7]),
                            "writes_merged": int(parts[8]),
                            "sectors_written": int(parts[9]),
                            "write_time_ms": int(parts[10])
                        }
        except:
            pass
        return None
    
    def _process_blktrace_output(self, trace_file):
        """Process blktrace output for detailed I/O patterns"""
        try:
            # Use blkparse to convert to readable format
            parse_cmd = f"blkparse -i {trace_file} -o - 2>/dev/null"
            result = os.popen(parse_cmd).read()
            
            for line in result.split('\n'):
                if not line.strip() or line.startswith('#'):
                    continue
                    
                # Parse blkparse output format
                parts = line.split()
                if len(parts) >= 8:
                    try:
                        # Extract I/O operation details
                        timestamp = float(parts[0])
                        io_type = parts[6]  # Q (queue), C (complete), M (merge), D (driver)
                        operation = parts[7]  # R (read), W (write)
                        
                        if operation in ['R', 'W'] and io_type in ['Q', 'C']:
                            sector = int(parts[8])
                            sectors = int(parts[9])
                            
                            timestamp_ms = int(timestamp * 1000)
                            
                            if operation == 'R':
                                self.io_stats["total_reads"] += 1
                                self.io_stats["total_bytes_read"] += sectors * self.sector_size
                                self.io_stats["read_operations"].append({
                                    "timestamp": timestamp_ms,
                                    "sector": sector,
                                    "sectors": sectors
                                })
                                self._update_sector_access(sector, sectors, "read")
                            else:  # 'W'
                                self.io_stats["total_writes"] += 1
                                self.io_stats["total_bytes_written"] += sectors * self.sector_size
                                self.io_stats["write_operations"].append({
                                    "timestamp": timestamp_ms,
                                    "sector": sector,
                                    "sectors": sectors
                                })
                                self._update_sector_access(sector, sectors, "write")
                                
                    except (ValueError, IndexError) as e:
                        continue
                        
        except Exception as e:
            pass
    
    def _update_sector_access(self, start_sector, num_sectors, io_type):
        """Track sector access patterns"""
        for offset in range(num_sectors):
            sector = start_sector + offset
            self.io_stats["sector_access_patterns"][sector] += 1
            
            # Track hot/cold sectors
            if self.io_stats["sector_access_patterns"][sector] >= self.hot_sector_threshold:
                self.analysis["hot_sectors"][sector] += 1
            else:
                self.analysis["cold_sectors"].add(sector)
    
    def _print_realtime_stats(self):
        """Print real-time monitoring statistics"""
        elapsed = time.time() - self.start_timestamp
        print(f"\n[Pixel Monitor] Real-time Stats (elapsed {elapsed:.1f}s):")
        print(f"  Reads: {self.io_stats['total_reads']}, Writes: {self.io_stats['total_writes']}")
        print(f"  Bytes Read: {self.io_stats['total_bytes_read'] / 1024 / 1024:.2f} MB")
        print(f"  Bytes Written: {self.io_stats['total_bytes_written'] / 1024 / 1024:.2f} MB")
        print(f"  Unique Sectors: {len(self.io_stats['sector_access_patterns'])}")
        print(f"  Hot Sectors: {len(self.analysis['hot_sectors'])}")
    
    def analyze_patterns(self):
        """Analyze collected I/O patterns for driver optimization insights"""
        print("\n[Pixel Monitor] Analyzing I/O patterns...")
        
        self._analyze_sequential_vs_random()
        self._analyze_burst_patterns()
        self._analyze_sector_hotness()
        self._calculate_average_sizes()
        self._analyze_io_amplification()
        
        return self.analysis
    
    def _analyze_sequential_vs_random(self):
        """Determine sequential vs random access patterns"""
        for op in self.io_stats["read_operations"]:
            if len(self.io_stats["read_operations"]) > 1:
                prev_op = self.io_stats["read_operations"][
                    self.io_stats["read_operations"].index(op) - 1
                ]
                if abs(op["sector"] - prev_op["sector"]) <= self.sequential_threshold:
                    self.analysis["sequential_reads"] += 1
                else:
                    self.analysis["random_reads"] += 1
        
        for op in self.io_stats["write_operations"]:
            if len(self.io_stats["write_operations"]) > 1:
                prev_op = self.io_stats["write_operations"][
                    self.io_stats["write_operations"].index(op) - 1
                ]
                if abs(op["sector"] - prev_op["sector"]) <= self.sequential_threshold:
                    self.analysis["sequential_writes"] += 1
                else:
                    self.analysis["random_writes"] += 1
    
    def _analyze_burst_patterns(self):
        """Identify I/O burst patterns (temporally clustered operations)"""
        # Group operations by time windows
        window_size = 100  # ms
        
        for op in self.io_stats["read_operations"]:
            window = (op["timestamp"] // window_size) * window_size
            if window not in self._get_burst_dict("read"):
                self._get_burst_dict("read")[window] = []
            self._get_burst_dict("read")[window].append(op)
        
        for op in self.io_stats["write_operations"]:
            window = (op["timestamp"] // window_size) * window_size
            if window not in self._get_burst_dict("write"):
                self._get_burst_dict("write")[window] = []
            self._get_burst_dict("write")[window].append(op)
        
        # Identify significant bursts
        self.analysis["read_bursts"] = [
            {"time": window, "count": len(ops)}
            for window, ops in self._get_burst_dict("read").items()
            if len(ops) > 5
        ]
        
        self.analysis["write_bursts"] = [
            {"time": window, "count": len(ops)}
            for window, ops in self._get_burst_dict("write").items()
            if len(ops) > 5
        ]
    
    def _get_burst_dict(self, io_type):
        """Helper for burst dictionary"""
        return self.read_bursts_dict if io_type == "read" else self.write_bursts_dict
    
    def _analyze_sector_hotness(self):
        """Analyze hot sector patterns for cache optimization"""
        # Group sectors by access frequency
        sector_ranges = []
        sorted_sectors = sorted(self.analysis["hot_sectors"].items(), 
                              key=lambda x: x[1], reverse=True)
        
        # Identify contiguous hot regions
        if sorted_sectors:
            current_range = {"start": sorted_sectors[0][0], "end": sorted_sectors[0][0], "accesses": sorted_sectors[0][1]}
            
            for sector, count in sorted_sectors[1:]:
                if sector == current_range["end"] + 1:
                    current_range["end"] = sector
                    current_range["accesses"] += count
                else:
                    sector_ranges.append(current_range)
                    current_range = {"start": sector, "end": sector, "accesses": count}
            
            sector_ranges.append(current_range)
        
        self.analysis["hot_sector_ranges"] = sector_ranges
    
    def _calculate_average_sizes(self):
        """Calculate average I/O sizes"""
        if self.io_stats["read_operations"]:
            total_sectors = sum(op["sectors"] for op in self.io_stats["read_operations"])
            self.analysis["avg_read_size"] = (total_sectors / len(self.io_stats["read_operations"])) * self.sector_size
        
        if self.io_stats["write_operations"]:
            total_sectors = sum(op["sectors"] for op in self.io_stats["write_operations"])
            self.analysis["avg_write_size"] = (total_sectors / len(self.io_stats["write_operations"])) * self.sector_size
    
    def _analyze_io_amplification(self):
        """Calculate I/O amplification factor (actual vs optimal)"""
        # This needs per-request sector data (bpftrace/blktrace); diskstats-only
        # monitoring has no read_operations/write_operations to burst-analyze,
        # so there is no valid "optimal" baseline to compare against.
        if self.monitoring_method == "diskstats":
            self.analysis["io_amplification"] = None
            return

        # Estimate optimal I/O for sequential patterns
        optimal_reads = len(self.analysis["read_bursts"]) if self.analysis["read_bursts"] else 1
        optimal_writes = len(self.analysis["write_bursts"]) if self.analysis["write_bursts"] else 1

        actual_reads = self.io_stats["total_reads"] if self.io_stats["total_reads"] > 0 else 1
        actual_writes = self.io_stats["total_writes"] if self.io_stats["total_writes"] > 0 else 1

        read_amplification = actual_reads / optimal_reads
        write_amplification = actual_writes / optimal_writes

        self.analysis["io_amplification"] = (read_amplification + write_amplification) / 2
    
    def generate_optimization_recommendations(self):
        """Generate recommendations for driver improvement"""
        recommendations = []
        
        # Sequential vs random analysis
        total_ops = (self.analysis["sequential_reads"] + self.analysis["random_reads"] + 
                    self.analysis["sequential_writes"] + self.analysis["random_writes"])
        
        if total_ops > 0:
            seq_ratio = (self.analysis["sequential_reads"] + self.analysis["sequential_writes"]) / total_ops
            
            if seq_ratio > 0.7:
                recommendations.append({
                    "type": "prefetch",
                    "priority": "high",
                    "description": f"High sequential access ratio ({seq_ratio:.1%}). Enable aggressive readahead and prefetch in virtio driver.",
                    "backend_changes": ["Increase READ_AHEAD sectors", "Implement sequential pattern detection"],
                    "impact": "Expected 2-3x sequential read performance improvement"
                })
            elif seq_ratio < 0.3:
                recommendations.append({
                    "type": "cache",
                    "priority": "medium",
                    "description": f"High random access ratio ({(1-seq_ratio):.1%}). Optimize cache policies for random access patterns.",
                    "backend_changes": ["Implement access-pattern-aware cache", "Add sector hotness tracking"],
                    "impact": "Expected 30-50% random access performance improvement"
                })
        
        # Hot sector analysis
        if len(self.analysis["hot_sectors"]) > 100:
            recommendations.append({
                "type": "cache",
                "priority": "high",
                "description": f"Detected {len(self.analysis['hot_sectors'])} hot sectors. Implement tiered caching.",
                "backend_changes": [
                    "Add hot sector LRU cache in backend.rs",
                    "Implement frame-level caching for hot regions",
                    "Cache frequently-accessed metadata frames"
                ],
                "impact": "Expected 5-10x performance for hot sectors"
            })
        
        # Burst analysis
        if len(self.analysis["read_bursts"]) > 10:
            recommendations.append({
                "type": "batch",
                "priority": "medium",
                "description": f"Detected {len(self.analysis['read_bursts'])} read bursts. Implement batch I/O optimization.",
                "backend_changes": [
                    "Add request coalescing in virtqueue polling",
                    "Implement burst-aware request scheduling",
                    "Optimize GPU texture loading for burst patterns"
                ],
                "impact": "Expected 40-60% burst I/O performance improvement"
            })
        
        # I/O amplification (only meaningful with per-request data from bpftrace/blktrace)
        if self.analysis["io_amplification"] is not None and self.analysis["io_amplification"] > 2.0:
            recommendations.append({
                "type": "amplification",
                "priority": "high",
                "description": f"High I/O amplification ({self.analysis['io_amplification']:.1f}x). Indicates suboptimal I/O patterns.",
                "backend_changes": [
                    "Implement request coalescing",
                    "Add sector-level write combining",
                    "Optimize Hilbert decoder for sequential access"
                ],
                "impact": "Expected 2-4x reduction in I/O amplification"
            })
        
        return recommendations
    
    def export_results(self, output_path):
        """Export monitoring results to JSON file"""
        results = {
            "metadata": {
                "device": self.device,
                "monitoring_duration": self.duration,
                "monitoring_start": self.io_stats["start_time"],
                "monitoring_end": self.io_stats["end_time"],
                "monitoring_method": self.monitoring_method
            },
            "io_statistics": {
                "total_reads": self.io_stats["total_reads"],
                "total_writes": self.io_stats["total_writes"],
                "total_bytes_read": self.io_stats["total_bytes_read"],
                "total_bytes_written": self.io_stats["total_bytes_written"],
                "unique_sectors_accessed": len(self.io_stats["sector_access_patterns"]),
                "read_throughput_mbps": (self.io_stats["total_bytes_read"] / 1024 / 1024) / self.duration,
                "write_throughput_mbps": (self.io_stats["total_bytes_written"] / 1024 / 1024) / self.duration
            },
            "pattern_analysis": {
                "sequential_reads": self.analysis["sequential_reads"],
                "random_reads": self.analysis["random_reads"],
                "sequential_writes": self.analysis["sequential_writes"],
                "random_writes": self.analysis["random_writes"],
                "hot_sectors_count": len(self.analysis["hot_sectors"]),
                "cold_sectors_count": len(self.analysis["cold_sectors"]),
                "read_bursts_count": len(self.analysis["read_bursts"]),
                "write_bursts_count": len(self.analysis["write_bursts"]),
                "avg_read_size_bytes": self.analysis["avg_read_size"],
                "avg_write_size_bytes": self.analysis["avg_write_size"],
                "io_amplification_factor": self.analysis["io_amplification"]
            },
            "optimization_recommendations": self.generate_optimization_recommendations(),
            "hot_sector_ranges": self.analysis.get("hot_sector_ranges", []),
            "raw_data": {
                "sector_access_patterns": dict(self.io_stats["sector_access_patterns"]),
                "temporal_patterns": dict(self.io_stats["temporal_patterns"])
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        return results


def main():
    parser = argparse.ArgumentParser(description="VM Pixel Flow Monitor")
    parser.add_argument("--device", default="/dev/vda", help="Block device to monitor")
    parser.add_argument("--duration", type=int, default=60, help="Monitoring duration in seconds")
    parser.add_argument("--output", default="/tmp/pixel_monitoring_results.json", 
                       help="Output file for results")
    parser.add_argument("--realtime", action="store_true", help="Enable real-time statistics")
    parser.add_argument("--analyze", action="store_true", help="Analyze existing results file")
    
    args = parser.parse_args()
    
    if args.analyze:
        # Analyze existing results
        if os.path.exists(args.output):
            with open(args.output, 'r') as f:
                results = json.load(f)
            
            print("[Pixel Monitor] Analysis of existing results:")
            print(f"  Total Reads: {results['io_statistics']['total_reads']}")
            print(f"  Total Writes: {results['io_statistics']['total_writes']}")
            amp = results['pattern_analysis']['io_amplification_factor']
            print(f"  I/O Amplification: {f'{amp:.1f}x' if amp is not None else 'n/a (diskstats-only run)'}")
            print(f"  Hot Sectors: {results['pattern_analysis']['hot_sectors_count']}")
            
            print("\nOptimization Recommendations:")
            for rec in results['optimization_recommendations']:
                print(f"\n  [{rec['type'].upper()}] Priority: {rec['priority']}")
                print(f"  Description: {rec['description']}")
                print(f"  Expected Impact: {rec['impact']}")
        else:
            print(f"Error: Results file not found: {args.output}")
            return 1
    else:
        # Run monitoring
        monitor = PixelFlowMonitor(
            device=args.device,
            duration=args.duration,
            realtime=args.realtime
        )
        
        # Run monitoring
        monitor.monitor_blocktrace()
        
        # Analyze patterns
        monitor.analyze_patterns()
        
        # Export results
        results = monitor.export_results(args.output)
        
        print(f"\n[Pixel Monitor] Results exported to {args.output}")
        print(f"[Pixel Monitor] Found {len(results['optimization_recommendations'])} optimization recommendations")
        
        # Print summary
        print("\n[Pixel Monitor] Summary:")
        print(f"  Total I/O: {results['io_statistics']['total_reads'] + results['io_statistics']['total_writes']} operations")
        print(f"  Throughput: {results['io_statistics']['read_throughput_mbps']:.2f} MB/s read, {results['io_statistics']['write_throughput_mbps']:.2f} MB/s write")
        print(f"  Hot Sectors: {results['pattern_analysis']['hot_sectors_count']}")
        amp = results['pattern_analysis']['io_amplification_factor']
        print(f"  I/O Amplification: {f'{amp:.1f}x' if amp is not None else 'n/a (diskstats-only run)'}")


if __name__ == "__main__":
    main()
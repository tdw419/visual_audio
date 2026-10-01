#!/usr/bin/env python3
import os
import subprocess
import sys
import json
import re

def analyze_elf(filepath):
    print(f"Analyzing ELF: {filepath}")
    calls = set()
    try:
        # Looking for generic calls or ecalls
        result = subprocess.run(["riscv64-linux-gnu-objdump", "-d", filepath], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "ecall" in line:
                    calls.add("RISC-V ecall")
                elif "call" in line and "<" in line and ">" in line:
                    m = re.search(r'<([^>]+)>', line)
                    if m:
                        calls.add(f"call {m.group(1)}")
    except Exception as e:
        print(f"Error analyzing {filepath}: {e}")
    return list(calls)

def main():
    boot_images_dir = "boot_images"
    if not os.path.isdir(boot_images_dir):
        print(f"Directory {boot_images_dir} not found.")
        sys.exit(1)
        
    inventory = {}
    
    for filename in os.listdir(boot_images_dir):
        if filename.endswith(".img") or filename.endswith(".elf"):
            filepath = os.path.join(boot_images_dir, filename)
            inventory[filename] = analyze_elf(filepath)
            
    with open("kernel_calls_inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)
        
    print("Inventory saved to kernel_calls_inventory.json")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Semantic Pixel Indexer for Boot Traces

Color-codes boot trace events by subsystem/trap type for visual pattern detection.
Designed for RV64I Alpine boot stall investigation.

Usage:
    python semantic_pixel_indexer.py /tmp/rv64i_boot_push.jsonl output.png

Output:
    - Pixel strip visualization (width = trace length, height = subsystem count)
    - JSONL with color annotations for interactive queries
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import hashlib

# Subsystem color palette (RGB tuples)
# Channel mapping: R=high_severity, G=progress, B=uart_output, A=metadata
PALETTE = {
    # Trap types
    "page_fault": (255, 50, 50, 255),      # Red - fault loop
    "load_fault": (255, 100, 100, 255),    # Light red - load page fault
    "inst_fault": (200, 50, 50, 255),      # Dark red - instruction fault
    "no_trap": (50, 200, 50, 255),         # Green - normal execution
    "other_trap": (255, 200, 50, 255),     # Orange - unknown trap

    # Subsystem ranges (kernel text regions, rough estimates)
    "kernel_text": (50, 100, 200, 255),    # Blue
    "kernel_data": (100, 100, 200, 255),   # Light blue
    "user_space": (150, 50, 150, 255),     # Purple
    "unknown_addr": (128, 128, 128, 255),  # Gray

    # Events
    "uart_output": (50, 255, 255, 255),    # Cyan - console output
    "stall_detected": (255, 0, 255, 255),  # Magenta - no progress
}


def classify_event(event: Dict) -> Tuple[str, Tuple[int, int, int, int]]:
    """
    Classify a trace event and return (category, rgba_color).
    """
    pc = event.get("pc", 0)
    mcause = event.get("mcause", 0)
    scause = event.get("scause", 0)
    uart_bytes = event.get("uart_new_bytes", 0)

    # Priority 1: UART output (most visible)
    if uart_bytes > 0:
        return "uart_output", PALETTE["uart_output"]

    # Priority 2: Trap classification
    if mcause == 9:  # Instruction page fault
        return "inst_fault", PALETTE["inst_fault"]
    if scause == 12:  # Load page fault
        return "load_fault", PALETTE["load_fault"]
    if mcause == 0 and scause == 0:
        return "no_trap", PALETTE["no_trap"]

    # Priority 3: Address range classification (kernel vs user)
    # Kernel text is typically in high memory (0xffffffff80000000+)
    if pc > 0xffffffff80000000:
        return "kernel_text", PALETTE["kernel_text"]
    elif pc > 0x80000000:
        return "kernel_data", PALETTE["kernel_data"]
    elif pc < 0x100000:
        return "user_space", PALETTE["user_space"]

    # Priority 4: Generic trap
    if mcause > 0 or scause > 0:
        return "other_trap", PALETTE["other_trap"]

    return "unknown_addr", PALETTE["unknown_addr"]


def detect_stall_sequence(events: List[Dict], window_size: int = 100) -> List[int]:
    """
    Detect stall patterns: repeated PC values with no UART output.
    Returns list of indices where stall is detected.
    """
    stall_indices = []
    for i in range(len(events) - window_size):
        window = events[i:i + window_size]

        # Check for zero UART output
        uart_sum = sum(e.get("uart_new_bytes", 0) for e in window)
        if uart_sum > 0:
            continue

        # Check for repeated PCs (within small address range)
        pcs = [e.get("pc", 0) for e in window]
        unique_pcs = len(set(pcs))
        if unique_pcs < window_size * 0.1:  # 90% of steps on same addresses
            stall_indices.append(i)

    return stall_indices


def generate_heatmap(events: List[Dict], output_png: str, events_per_row: int = 50):
    """
    Generate a 2D heatmap visualization where x=step progression, y=category.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Error: PIL/Pillow required. Install with: pip install Pillow")
        sys.exit(1)

    # Classify all events
    classified = []
    for event in events:
        category, color = classify_event(event)
        classified.append((category, color))

    # Detect stall region (continuous zero UART output)
    uart_zero_start = None
    for i, evt in enumerate(events):
        if evt.get("uart_new_bytes", 0) == 0:
            if uart_zero_start is None:
                uart_zero_start = i
        else:
            uart_zero_start = None

    # If more than 5 consecutive events have zero UART, mark as stall
    stall_region = None
    if uart_zero_start is not None and len(events) - uart_zero_start > 5:
        stall_region = (uart_zero_start, len(events) - 1)

    # Create heatmap grid
    num_events = len(classified)
    num_rows = (num_events + events_per_row - 1) // events_per_row
    num_categories = len(PALETTE)

    # Image: height = num_categories * 2 (category rows + label space)
    img_height = num_rows * num_categories + num_categories + 50  # +50 for legend
    img = Image.new("RGBA", (events_per_row, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw category heatmap
    category_to_y = {cat: i for i, cat in enumerate(PALETTE.keys())}

    for i, (category, color) in enumerate(classified):
        x = i % events_per_row
        row = i // events_per_row
        y = row * num_categories + category_to_y[category]
        draw.rectangle((x, y, x + 1, y + 1), fill=color)

    # Mark stall region with magenta border
    if stall_region:
        start, end = stall_region
        for i in range(start, end + 1):
            x = i % events_per_row
            row = i // events_per_row
            draw.rectangle((x, row * num_categories - 2, x + 1, row * num_categories + num_categories + 1),
                          outline=(255, 0, 255), width=1)

    # Draw legend at bottom
    legend_y = num_rows * num_categories + num_categories + 10
    legend_x = 10
    for cat, color in PALETTE.items():
        draw.rectangle((legend_x, legend_y, legend_x + 10, legend_y + 10), fill=color)
        draw.text((legend_x + 15, legend_y), cat, fill=(255, 255, 255, 255))
        legend_x += 120
        if legend_x > events_per_row - 100:
            legend_x = 10
            legend_y += 15

    # Add title
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
    except:
        font = ImageFont.load_default()
    draw.text((5, 5), f"RV64I Stall Trace: {num_events} events", fill=(255, 255, 255, 255), font=font)
    if stall_region:
        draw.text((5, 20), f"STALL DETECTED at event {stall_region[0]} → {stall_region[1]}", fill=(255, 0, 255), font=font)

    img.save(output_png)
    print(f"Heatmap saved to {output_png}")
    print(f"Dimensions: {events_per_row}x{img_height} (columns x rows)")

    return img


def generate_annotated_jsonl(events: List[Dict], output_jsonl: str):
    """
    Generate annotated JSONL with color/category metadata.
    """
    with open(output_jsonl, 'w') as f:
        for event in events:
            category, color = classify_event(event)
            annotated = {
                **event,
                "_semantic": {
                    "category": category,
                    "rgba": color
                }
            }
            f.write(json.dumps(annotated) + '\n')

    print(f"Annotated JSONL saved to {output_jsonl}")


def print_statistics(events: List[Dict]):
    """
    Print classification statistics.
    """
    categories = {}
    for event in events:
        category, _ = classify_event(event)
        categories[category] = categories.get(category, 0) + 1

    print("\n=== Semantic Classification Statistics ===")
    total = len(events)
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        pct = (count / total) * 100
        print(f"{cat:20s}: {count:7d} ({pct:5.1f}%)")

    # Detect and report stall pattern
    stall_indices = detect_stall_sequence(events)
    if stall_indices:
        stall_start = stall_indices[0]
        stall_end = stall_indices[-1]
        stall_duration = stall_end - stall_start
        print(f"\nSTALL DETECTED:")
        print(f"  Start event: {stall_start}")
        print(f"  End event: {stall_end}")
        print(f"  Duration: {stall_duration} events ({stall_duration/1000000:.1f} steps)")

        # Show representative PCs from stall region
        stall_events = events[stall_start:stall_start + 100]
        unique_pcs = sorted(set(e.get("pc", 0) for e in stall_events))
        print(f"  Unique PCs in stall region (first 10):")
        for pc in unique_pcs[:10]:
            print(f"    0x{pc:016x}")


def main():
    if len(sys.argv) < 2:
        print("Usage: semantic_pixel_indexer.py <trace.jsonl> [output.png] [annotated.jsonl]")
        sys.exit(1)

    trace_file = Path(sys.argv[1])
    output_png = sys.argv[2] if len(sys.argv) > 2 else trace_file.stem + "_semantic.png"
    annotated_jsonl = sys.argv[3] if len(sys.argv) > 3 else trace_file.stem + "_annotated.jsonl"

    # Load trace
    print(f"Loading trace from {trace_file}...")
    events = []
    with open(trace_file) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    print(f"Loaded {len(events)} events")

    # Print statistics
    print_statistics(events)

    # Generate visualizations
    generate_heatmap(events, output_png)
    generate_annotated_jsonl(events, annotated_jsonl)


if __name__ == "__main__":
    main()
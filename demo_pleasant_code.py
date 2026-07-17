#!/usr/bin/env python3
"""
demo_pleasant_code.py — Showcase the sonic code translator capabilities.

Demonstrates:
1. Converting code to pleasant audio
2. Different code patterns and their musical signatures
3. Dual-band encoding for human + machine consumption
4. Comparative analysis of code styles
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.sonic_code_translator import code_to_pleasant_audio, MusicalConstruct


def demo_basic_function():
    """Demo: Simple function sounds like a gentle melody."""
    code = """
def greet(name):
    return f"Hello, {name}!"

print(greet("World"))
"""
    print("=" * 70)
    print("DEMO 1: Basic Function")
    print("=" * 70)
    print("Code: Simple greeting function")
    print()
    
    audio, events = code_to_pleasant_audio(
        code,
        output_path="demo_basic_function.wav",
        project_path="demo_basic_function_metadata.json"
    )
    
    analyze_events(events, "Basic Function")


def demo_loop_patterns():
    """Demo: Loops create rhythmic patterns."""
    code = """
for i in range(10):
    print(f"Processing item {i}")
    
total = 0
while total < 100:
    total += 1
    print(f"Total: {total}")
"""
    print("=" * 70)
    print("DEMO 2: Loop Patterns")
    print("=" * 70)
    print("Code: For loop and while loop creating rhythmic patterns")
    print()
    
    audio, events = code_to_pleasant_audio(
        code,
        output_path="demo_loop_patterns.wav",
        project_path="demo_loop_patterns_metadata.json"
    )
    
    analyze_events(events, "Loop Patterns")


def demo_class_structure():
    """Demo: Classes create foundational musical themes."""
    code = """
class Calculator:
    def __init__(self):
        self.result = 0
    
    def add(self, a, b):
        self.result = a + b
        return self.result
    
    def multiply(self, a, b):
        self.result = a * b
        return self.result

calc = Calculator()
print(calc.add(5, 3))
print(calc.multiply(4, 7))
"""
    print("=" * 70)
    print("DEMO 3: Class Structure")
    print("=" * 70)
    print("Code: Calculator class with methods creates structured music")
    print()
    
    audio, events = code_to_pleasant_audio(
        code,
        output_path="demo_class_structure.wav",
        project_path="demo_class_structure_metadata.json"
    )
    
    analyze_events(events, "Class Structure")


def demo_complex_logic():
    """Demo: Complex logic creates intricate musical patterns."""
    code = """
def analyze_data(data, threshold=10):
    results = []
    
    if not data:
        return results
    
    for item in data:
        try:
            if item > threshold:
                processed = item * 2
                results.append(processed)
            elif item == threshold:
                results.append(item)
            else:
                results.append(0)
        except Exception as e:
            print(f"Error processing {item}: {e}")
    
    return results

data = [5, 15, 10, 20, 3, 12]
analyzed = analyze_data(data)
print(f"Results: {analyzed}")
"""
    print("=" * 70)
    print("DEMO 4: Complex Logic")
    print("=" * 70)
    print("Code: Nested conditionals, exception handling, and data processing")
    print()
    
    audio, events = code_to_pleasant_audio(
        code,
        output_path="demo_complex_logic.wav",
        project_path="demo_complex_logic_metadata.json"
    )
    
    analyze_events(events, "Complex Logic")


def demo_recursive_function():
    """Demo: Recursion creates self-similar musical patterns."""
    code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

print(f"factorial(5) = {factorial(5)}")
print(f"fibonacci(10) = {fibonacci(10)}")
"""
    print("=" * 70)
    print("DEMO 5: Recursive Functions")
    print("=" * 70)
    print("Code: Recursive functions create self-similar musical patterns")
    print()
    
    audio, events = code_to_pleasant_audio(
        code,
        output_path="demo_recursive.wav",
        project_path="demo_recursive_metadata.json"
    )
    
    analyze_events(events, "Recursive Functions")


def analyze_events(events, title):
    """Analyze and display event statistics."""
    if not events:
        print("No events generated")
        return
    
    duration = events[-1].start_time + events[-1].duration
    
    print(f"✓ Generated {len(events)} musical events")
    print(f"  Duration: {duration:.2f}s")
    print(f"  Event Rate: {len(events)/duration:.1f} events/second")
    print()
    
    # Group by construct
    by_construct = {}
    for event in events:
        if event.construct not in by_construct:
            by_construct[event.construct] = []
        by_construct[event.construct].append(event)
    
    print("Construct Distribution:")
    for construct, construct_events in sorted(by_construct.items(), key=lambda x: len(x[1]), reverse=True):
        if len(construct_events) > 0:
            print(f"  {construct.value:20s}: {len(construct_events):3d} events")
    
    print()
    print("Musical Characteristics:")
    pitches = [e.pitch for e in events]
    durations = [e.duration for e in events]
    
    print(f"  Pitch Range: {min(pitches):.1f} - {max(pitches):.1f} Hz")
    print(f"  Avg Duration: {sum(durations)/len(durations):.3f}s")
    print(f"  Duration Range: {min(durations):.3f} - {max(durations):.3f}s")
    
    # Calculate nesting depth
    indent_count = sum(1 for e in events if e.construct == MusicalConstruct.INDENT)
    dedent_count = sum(1 for e in events if e.construct == MusicalConstruct.DEDENT)
    max_depth = max(indent_count - dedent_count, 0)
    print(f"  Max Nesting Depth: {max_depth}")
    
    print()


def main():
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "  Sonic Code Translator - Demo Showcase".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("║" + "  Transform code into melodious, pleasant-to-listen audio".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "═" * 68 + "╝")
    print()
    
    demos = [
        ("Basic Function", demo_basic_function),
        ("Loop Patterns", demo_loop_patterns),
        ("Class Structure", demo_class_structure),
        ("Complex Logic", demo_complex_logic),
        ("Recursive Functions", demo_recursive_function),
    ]
    
    for i, (name, demo_func) in enumerate(demos, 1):
        print(f"\n{'=' * 70}")
        print(f"Running Demo {i}/{len(demos)}: {name}")
        print(f"{'=' * 70}\n")
        
        try:
            demo_func()
        except Exception as e:
            print(f"✗ Demo failed: {e}")
            import traceback
            traceback.print_exc()
    
    print()
    print("=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print()
    print("Generated Audio Files:")
    print("  - demo_basic_function.wav")
    print("  - demo_loop_patterns.wav")
    print("  - demo_class_structure.wav")
    print("  - demo_complex_logic.wav")
    print("  - demo_recursive.wav")
    print()
    print("Generated Metadata Files:")
    print("  - demo_*_metadata.json")
    print()
    print("Listen to the files to experience code as music!")
    print("Humans hear pleasant melodies; machines can extract exact code bytes.")
    print()


if __name__ == '__main__':
    main()
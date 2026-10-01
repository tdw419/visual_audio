#!/usr/bin/env python3
"""
Example code for sonic translation.
This script demonstrates different programming constructs.
"""

def fibonacci(n):
    """Calculate the nth Fibonacci number."""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

class DataProcessor:
    """Process and transform data."""
    
    def __init__(self, name):
        self.name = name
        self.count = 0
    
    def process(self, items):
        """Process a list of items."""
        results = []
        for item in items:
            if item > 0:
                processed = item * 2
                results.append(processed)
                self.count += 1
        return results
    
    def get_summary(self):
        """Get processing summary."""
        return f"{self.name}: processed {self.count} items"

# Main execution
if __name__ == "__main__":
    processor = DataProcessor("test")
    
    # Test data
    numbers = [1, 2, 3, 4, 5]
    results = processor.process(numbers)
    
    # Print results
    print(f"Results: {results}")
    print(f"Summary: {processor.get_summary()}")
    
    # Test Fibonacci
    fib_result = fibonacci(10)
    print(f"Fibonacci(10) = {fib_result}")
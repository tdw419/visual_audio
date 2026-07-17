#!/usr/bin/env python3
"""Simple test fixture for codec verification"""


def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


if __name__ == '__main__':
    result = fibonacci(10)
    print(f"Fibonacci(10) = {result}")
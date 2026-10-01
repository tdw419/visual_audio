#!/usr/bin/env python3
"""
Quick test of Ollama analyzer on vulnerable code.
"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path

vulnerable_code = '''import os
import subprocess
import sqlite3

def process_user_input(input_data):
    """Process user input without sanitization."""
    # SQL injection vulnerability
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE name = '{input_data}'"
    cursor.execute(query)
    results = cursor.fetchall()
    conn.close()
    return results
'''

with tempfile.TemporaryDirectory() as tmpdir:
    test_file = os.path.join(tmpdir, 'vulnerable.py')
    Path(test_file).write_text(vulnerable_code)

    review_path = os.path.join(tmpdir, 'review.md')

    print("Testing Ollama analyzer on vulnerable code...")
    print(f"File: {test_file}")
    print(f"Review: {review_path}")
    print()

    # Run analyzer (without Ollama for now - just test the structure)
    from tools.ollama_analyzer import (
        parse_diff, generate_review_document, analyze_pass
    )

    # Mock a pass result
    mock_pass = {
        'pass_name': 'security',
        'focus': 'Security vulnerabilities',
        'findings_count': 1,
        'raw_analysis': '''## [HIGH] SQL Injection Vulnerability
**File:** vulnerable.py:9
**Description:** Direct string interpolation in SQL query allows arbitrary SQL injection
**Impact:** Attackers can read, modify, or delete database data
**Fix:** Use parameterized queries: `cursor.execute("SELECT * FROM users WHERE name = ?", (input_data,))`''',
        'findings': ['## [HIGH] SQL Injection Vulnerability']
    }

    # Generate review
    generate_review_document([mock_pass], review_path)

    # Show review
    print("=" * 60)
    print("GENERATED REVIEW:")
    print("=" * 60)
    print()
    print(Path(review_path).read_text())

    print()
    print("✅ Test complete - analyzer structure works")
    print()
    print("To run with real Ollama:")
    print(f"  python3 tools/ollama_analyzer.py --files {test_file} --review {review_path} --passes security")
#!/usr/bin/env python3
"""
CLI wrapper for cross_modal.py - sets up path and forwards commands.
"""

import sys
import os

# Add project root to path for imports
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Import and run cross_modal
from tools import cross_modal

# Run the main function with command-line args
cross_modal.main()
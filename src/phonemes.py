#!/usr/bin/env python3
"""
phonemes.py — Re-export of phonemes from tools/ for backwards compatibility.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.phonemes import *

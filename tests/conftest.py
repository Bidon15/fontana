"""
Pytest configuration for Fontana tests.

This file helps pytest find and run tests correctly by setting up the Python path
and other configuration options.
"""

import os
import sys

# Add the project root to the Python path to help with imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

"""
Celestia bridge integration for Fontana.

This package contains clients and utilities for interacting with Celestia L1,
specifically for the bridge interface.
"""

from fontana.bridge.celestia.account_client import CelestiaAccountClient, CelestiaTransaction

__all__ = ["CelestiaAccountClient", "CelestiaTransaction"]

"""
Data Availability (DA) layer integration for Fontana.

This package provides the necessary components for integrating
with the Celestia Data Availability layer.
"""

from fontana.core.da.client import CelestiaClient, CelestiaSubmissionError
from fontana.core.da.poster import BlobPoster

__all__ = ["CelestiaClient", "CelestiaSubmissionError", "BlobPoster"]
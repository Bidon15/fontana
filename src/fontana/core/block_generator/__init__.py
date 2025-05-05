"""
Block generator module for Fontana.

This module provides a simplified block generator that processes transactions
directly and creates blocks at regular intervals.
"""
from fontana.core.block_generator.processor import TransactionProcessor, ProcessingError
from fontana.core.block_generator.generator import BlockGenerator, BlockGenerationError

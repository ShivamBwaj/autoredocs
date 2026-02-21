"""Backward-compatible re-export.

The canonical parser code now lives in :mod:`autoredocs.parsers.python_parser`.
This module re-exports ``PythonParser`` so that existing imports like
``from autoredocs.parser import PythonParser`` continue to work.
"""

from autoredocs.parsers.python_parser import PythonParser  # noqa: F401

__all__ = ["PythonParser"]

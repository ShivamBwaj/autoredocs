"""Abstract base parser for all language parsers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from autoredocs.models import ModuleDoc, ProjectDoc

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Abstract base class for language-specific code parsers."""

    # Subclasses should set this to their supported file extensions
    extensions: list[str] = []

    def __init__(self, exclude_private: bool = False):
        """Initialize an object with the exclude private attribute.

        Args:
            exclude_private: A boolean flag to exclude private attributes from the object.
        """
        self.exclude_private = exclude_private

    @abstractmethod
    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        """Parse a single source file and return a ModuleDoc, or None on failure."""

    def parse_directory(
        self,
        directory: str | Path,
        exclude_dirs: list[str] | None = None,
    ) -> ProjectDoc:
        """Parse all matching files in a directory tree and return a ProjectDoc."""
        directory = Path(directory)
        exclude_dirs_set = set(
            exclude_dirs or ["__pycache__", ".venv", "venv", "node_modules", ".git"]
        )

        project = ProjectDoc(title=directory.name)

        for ext in self.extensions:
            for src_file in sorted(directory.rglob(f"*{ext}")):
                # Skip excluded directories
                if any(part in exclude_dirs_set for part in src_file.parts):
                    continue

                module = self.parse_file(src_file)
                if module and not module.is_empty:
                    # Build a dotted module name from relative path
                    try:
                        rel = src_file.relative_to(directory)
                        parts = list(rel.parts[:-1]) + [rel.stem]
                        if parts[-1] in ("__init__", "index"):
                            parts = parts[:-1]
                        if parts:
                            module.module_name = ".".join(parts)
                    except ValueError:
                        pass

                    project.modules.append(module)

        return project

    def _should_include(self, name: str) -> bool:
        """Check if a name should be included based on privacy settings."""
        if self.exclude_private and name.startswith("_") and not name.startswith("__"):
            return False
        return True


class MultiParser:
    """Delegates parsing to the correct language parser based on file extension.

    Scans all supported file types in a single directory pass.
    """

    def __init__(self, exclude_private: bool = False):
        self.exclude_private = exclude_private

    def parse_directory(
        self,
        directory: str | Path,
        exclude_dirs: list[str] | None = None,
    ) -> ProjectDoc:
        """Parse all supported source files in a directory tree."""
        from autoredocs.parsers import ALL_EXTENSIONS, get_parser

        directory = Path(directory)
        exclude_dirs_set = set(
            exclude_dirs or ["__pycache__", ".venv", "venv", "node_modules", ".git"]
        )

        project = ProjectDoc(title=directory.name)
        # Cache parser instances by extension
        parser_cache: dict[str, BaseParser] = {}

        for ext in ALL_EXTENSIONS:
            for src_file in sorted(directory.rglob(f"*{ext}")):
                if any(part in exclude_dirs_set for part in src_file.parts):
                    continue

                if ext not in parser_cache:
                    p = get_parser(ext)
                    if p is None:
                        continue
                    p.exclude_private = self.exclude_private
                    parser_cache[ext] = p

                parser = parser_cache[ext]
                module = parser.parse_file(src_file)
                if module and not module.is_empty:
                    try:
                        rel = src_file.relative_to(directory)
                        parts = list(rel.parts[:-1]) + [rel.stem]
                        if parts[-1] in ("__init__", "index"):
                            parts = parts[:-1]
                        if parts:
                            module.module_name = ".".join(parts)
                    except ValueError:
                        pass

                    project.modules.append(module)

        return project

    def find_all_source_files(
        self,
        directory: str | Path,
        exclude_dirs: set[str] | None = None,
    ) -> list[Path]:
        """Find all supported source files in a directory tree."""
        from autoredocs.parsers import ALL_EXTENSIONS

        directory = Path(directory)
        exclude_dirs = exclude_dirs or {"__pycache__", ".venv", "venv", "node_modules", ".git"}
        files: list[Path] = []
        for ext in ALL_EXTENSIONS:
            for src_file in sorted(directory.rglob(f"*{ext}")):
                if not any(part in exclude_dirs for part in src_file.parts):
                    files.append(src_file)
        return sorted(files)

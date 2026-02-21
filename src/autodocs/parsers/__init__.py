"""Parser registry — maps file extensions to parser classes."""

from __future__ import annotations

from autodocs.parsers.base import BaseParser
from autodocs.parsers.python_parser import PythonParser

# Registry: extension -> parser class
PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    ".py": PythonParser,
}

try:
    from autodocs.parsers.typescript import TypeScriptParser

    PARSER_REGISTRY[".ts"] = TypeScriptParser
    PARSER_REGISTRY[".tsx"] = TypeScriptParser
    PARSER_REGISTRY[".js"] = TypeScriptParser
    PARSER_REGISTRY[".jsx"] = TypeScriptParser
except ImportError:
    pass

try:
    from autodocs.parsers.java import JavaParser

    PARSER_REGISTRY[".java"] = JavaParser
except ImportError:
    pass


def get_parser(extension: str) -> BaseParser | None:
    """Return a parser instance for the given file extension."""
    cls = PARSER_REGISTRY.get(extension)
    return cls() if cls else None


__all__ = ["BaseParser", "PythonParser", "PARSER_REGISTRY", "get_parser"]

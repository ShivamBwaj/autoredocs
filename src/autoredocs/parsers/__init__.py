"""Parser registry — maps file extensions to parser classes."""

from __future__ import annotations

from autoredocs.parsers.base import BaseParser
from autoredocs.parsers.python_parser import PythonParser

# Registry: extension -> parser class
PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    ".py": PythonParser,
}

try:
    from autoredocs.parsers.typescript import TypeScriptParser

    PARSER_REGISTRY[".ts"] = TypeScriptParser
    PARSER_REGISTRY[".tsx"] = TypeScriptParser
    PARSER_REGISTRY[".js"] = TypeScriptParser
    PARSER_REGISTRY[".jsx"] = TypeScriptParser
except ImportError:
    pass

try:
    from autoredocs.parsers.java import JavaParser

    PARSER_REGISTRY[".java"] = JavaParser
except ImportError:
    pass

try:
    from autoredocs.parsers.go import GoParser

    PARSER_REGISTRY[".go"] = GoParser
except ImportError:
    pass

try:
    from autoredocs.parsers.rust import RustParser

    PARSER_REGISTRY[".rs"] = RustParser
except ImportError:
    pass

try:
    from autoredocs.parsers.csharp import CSharpParser

    PARSER_REGISTRY[".cs"] = CSharpParser
except ImportError:
    pass

try:
    from autoredocs.parsers.cpp import CppParser

    for _ext in CppParser.extensions:
        PARSER_REGISTRY[_ext] = CppParser
except ImportError:
    pass

try:
    from autoredocs.parsers.ruby import RubyParser

    PARSER_REGISTRY[".rb"] = RubyParser
except ImportError:
    pass

try:
    from autoredocs.parsers.kotlin import KotlinParser

    PARSER_REGISTRY[".kt"] = KotlinParser
    PARSER_REGISTRY[".kts"] = KotlinParser
except ImportError:
    pass

# Convenience set of all supported extensions
ALL_EXTENSIONS: set[str] = set(PARSER_REGISTRY.keys())


def get_parser(extension: str) -> BaseParser | None:
    """Return a parser instance for the given file extension."""
    cls = PARSER_REGISTRY.get(extension)
    return cls() if cls else None


__all__ = ["BaseParser", "PythonParser", "PARSER_REGISTRY", "ALL_EXTENSIONS", "get_parser"]

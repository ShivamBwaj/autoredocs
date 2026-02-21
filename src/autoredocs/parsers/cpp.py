"""C/C++ regex-based parser.

Extracts functions, classes, and structs from C/C++ source and header files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from autoredocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autoredocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# -- Regex patterns -----------------------------------------------------------

# Doxygen /** ... */ or /*! ... */
_DOXYGEN_BLOCK_RE = re.compile(r"/\*[*!](.*?)\*/", re.DOTALL)

# Doxygen /// or //! line comments
_DOXYGEN_LINE_RE = re.compile(
    r"((?:^[ \t]*(?:///|//!)[^\n]*\n)+)",
    re.MULTILINE,
)

# Class declaration
_CLASS_RE = re.compile(
    r"^(?:template\s*<[^>]*>\s*)?"
    r"class\s+(?:\w+\s+)*(\w+)"  # class name (skip __declspec etc)
    r"(?:\s*:\s*(?:public|protected|private)\s+([^\n{]+))?"  # bases
    r"\s*\{",
    re.MULTILINE,
)

# Struct declaration
_STRUCT_RE = re.compile(
    r"^(?:typedef\s+)?struct\s+(\w+)"
    r"\s*\{",
    re.MULTILINE,
)

# Function declaration (top-level, not inside class)
_FUNC_RE = re.compile(
    r"^(?:(?:static|inline|extern|virtual|explicit|constexpr|const|unsigned|signed)\s+)*"
    r"([\w:*&<>,\s]+?)\s+"  # return type
    r"(\w+)"  # function name
    r"\s*\(([^)]*)\)"  # params
    r"(?:\s*const)?"
    r"(?:\s*(?:noexcept|override|final))?"
    r"\s*[{;]",
    re.MULTILINE,
)

# Method inside class body
_METHOD_RE = re.compile(
    r"^[ \t]+(?:(?:static|virtual|inline|explicit|constexpr|const|override|final)\s+)*"
    r"([\w:*&<>,\s]+?)\s+"  # return type
    r"(\w+)"  # method name
    r"\s*\(([^)]*)\)"  # params
    r"(?:\s*const)?"
    r"(?:\s*(?:noexcept|override|final))?"
    r"\s*[{;=]",
    re.MULTILINE,
)


class CppParser(BaseParser):
    """Regex-based parser for C/C++ source and header files."""

    extensions = [".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"]

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        """Parse a C/C++ source file and return a ModuleDoc."""
        filepath = Path(filepath)
        if not filepath.exists():
            return None

        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return None

        module = ModuleDoc(
            filepath=str(filepath),
            module_name=filepath.stem,
        )

        doc_map = _build_doc_map(source)

        # -- Classes -----------------------------------------------------------
        for m in _CLASS_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            bases = [b.strip() for b in (m.group(2) or "").split(",") if b.strip()]
            cls = ClassDoc(
                name=name,
                bases=bases,
                docstring=doc_map.get(m.start(), ""),
                line_number=source[: m.start()].count("\n") + 1,
            )
            cls.methods = self._extract_methods(source, m.end(), doc_map)
            module.classes.append(cls)

        # -- Structs -----------------------------------------------------------
        for m in _STRUCT_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=[],
                    docstring=doc_map.get(m.start(), ""),
                    decorators=["struct"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        # -- Top-level functions -----------------------------------------------
        for m in _FUNC_RE.finditer(source):
            name = m.group(2)
            if not self._should_include(name):
                continue
            # Skip keywords that look like functions
            if name in ("if", "for", "while", "switch", "return", "sizeof", "typedef"):
                continue
            ret_type = m.group(1).strip()
            # Skip macros (all caps)
            if name.isupper():
                continue

            module.functions.append(
                FunctionDoc(
                    name=name,
                    args=_parse_cpp_params(m.group(3)),
                    return_type=ret_type,
                    docstring=doc_map.get(m.start(), ""),
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        return module

    def _extract_methods(
        self, source: str, body_start: int, parent_doc_map: dict[int, str]
    ) -> list[FunctionDoc]:
        """Extract methods from a class body."""
        body = _extract_brace_body(source, body_start)
        doc_map = _build_doc_map(body)
        methods: list[FunctionDoc] = []

        for m in _METHOD_RE.finditer(body):
            name = m.group(2)
            if name in ("if", "for", "while", "switch", "return"):
                continue
            if not self._should_include(name):
                continue
            methods.append(
                FunctionDoc(
                    name=name,
                    args=_parse_cpp_params(m.group(3)),
                    return_type=m.group(1).strip(),
                    docstring=doc_map.get(m.start(), ""),
                    is_method=True,
                    line_number=body[: m.start()].count("\n") + 1,
                )
            )

        return methods


# -- Helpers -------------------------------------------------------------------


def _extract_brace_body(source: str, start: int) -> str:
    """Extract text inside braces starting at position."""
    depth = 1
    pos = start
    while pos < len(source) and depth > 0:
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
        pos += 1
    return source[start:pos]


def _build_doc_map(source: str) -> dict[int, str]:
    """Map positions to preceding doc comments (block or line style)."""
    result: dict[int, str] = {}

    # Block comments: /** ... */ or /*! ... */
    for m in _DOXYGEN_BLOCK_RE.finditer(source):
        end = m.end()
        skip = len(source[end:]) - len(source[end:].lstrip())
        result[end + skip] = _clean_doxygen_block(m.group(1))

    # Line comments: /// or //!
    for m in _DOXYGEN_LINE_RE.finditer(source):
        result[m.end()] = _clean_doxygen_lines(m.group(1))

    return result


def _clean_doxygen_block(raw: str) -> str:
    """Clean a Doxygen block comment."""
    lines = raw.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith("* "):
            line = line[2:]
        elif line.startswith("*"):
            line = line[1:]
        # Skip @param, @return tags
        if line.strip().startswith("@") or line.strip().startswith("\\"):
            continue
        cleaned.append(line.strip())
    return "\n".join(cleaned).strip()


def _clean_doxygen_lines(raw: str) -> str:
    """Clean Doxygen line comments (/// or //!)."""
    lines = raw.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith("/// "):
            line = line[4:]
        elif line.startswith("///"):
            line = line[3:]
        elif line.startswith("//! "):
            line = line[4:]
        elif line.startswith("//!"):
            line = line[3:]
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _parse_cpp_params(raw: str) -> list[ArgInfo]:
    """Parse C/C++ function parameters."""
    if not raw.strip() or raw.strip() == "void":
        return []
    params: list[ArgInfo] = []
    depth = 0
    current: list[str] = []
    parts: list[str] = []
    for ch in raw:
        if ch in "<({":
            depth += 1
            current.append(ch)
        elif ch in ">)}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))

    for part in parts:
        part = part.strip()
        if not part or part == "...":
            if part == "...":
                params.append(ArgInfo(name="...", type_hint="variadic"))
            continue

        # Remove default value
        default = ""
        if "=" in part:
            part, default = part.rsplit("=", 1)
            part = part.strip()
            default = default.strip()

        # Split type from name — last token is the name
        tokens = part.replace("*", "* ").replace("&", "& ").split()
        if len(tokens) >= 2:
            name = tokens[-1].strip("*& ")
            type_hint = " ".join(tokens[:-1])
        else:
            name = tokens[0] if tokens else part
            type_hint = ""

        params.append(ArgInfo(name=name, type_hint=type_hint, default=default))
    return params

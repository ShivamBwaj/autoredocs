"""C# regex-based parser.

Extracts classes, interfaces, structs, enums, methods, and properties
from C# source files using regular expressions.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from autodocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autodocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# -- Regex patterns -----------------------------------------------------------

# XML doc comment: consecutive /// lines
_XMLDOC_RE = re.compile(
    r"((?:^[ \t]*///[^\n]*\n)+)",
    re.MULTILINE,
)

# Namespace
_NAMESPACE_RE = re.compile(r"^namespace\s+([\w.]+)", re.MULTILINE)

# Class declaration
_CLASS_RE = re.compile(
    r"^(?:[ \t]*)"
    r"(?:(?:public|private|protected|internal|static|abstract|sealed|partial)\s+)*"
    r"class\s+(\w+)"
    r"(?:<[^>]*>)?"  # generics
    r"(?:\s*:\s*([^\n{]+))?"  # base classes
    r"\s*\{",
    re.MULTILINE,
)

# Interface declaration
_INTERFACE_RE = re.compile(
    r"^(?:[ \t]*)"
    r"(?:(?:public|private|protected|internal)\s+)?"
    r"interface\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"(?:\s*:\s*([^\n{]+))?"
    r"\s*\{",
    re.MULTILINE,
)

# Struct declaration
_STRUCT_RE = re.compile(
    r"^(?:[ \t]*)"
    r"(?:(?:public|private|protected|internal|readonly|ref)\s+)*"
    r"struct\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"(?:\s*:\s*([^\n{]+))?"
    r"\s*\{",
    re.MULTILINE,
)

# Enum declaration
_ENUM_RE = re.compile(
    r"^(?:[ \t]*)"
    r"(?:(?:public|private|protected|internal)\s+)?"
    r"enum\s+(\w+)"
    r"(?:\s*:\s*(\w+))?"
    r"\s*\{",
    re.MULTILINE,
)

# Method declaration
_METHOD_RE = re.compile(
    r"^[ \t]+(?:(?:public|private|protected|internal|static|virtual|override|"
    r"abstract|async|new|sealed|extern|partial)\s+)*"
    r"(?:<[^>]*>\s+)?"
    r"([\w.<>\[\],?\s]+?)\s+"  # return type
    r"(\w+)"  # method name
    r"\s*(?:<[^>]*>)?"  # generic params
    r"\s*\(([^)]*)\)"  # params
    r"(?:\s*where\s+[^{;]+)?"  # constraints
    r"\s*[{;]",
    re.MULTILINE,
)


class CSharpParser(BaseParser):
    """Regex-based parser for C# source files."""

    extensions = [".cs"]

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        """Parse a C# source file and return a ModuleDoc."""
        filepath = Path(filepath)
        if not filepath.exists():
            return None

        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return None

        ns_match = _NAMESPACE_RE.search(source)
        namespace = ns_match.group(1) if ns_match else ""
        name = f"{namespace}.{filepath.stem}" if namespace else filepath.stem

        module = ModuleDoc(filepath=str(filepath), module_name=name)
        doc_map = _build_xmldoc_map(source)

        # -- Classes -----------------------------------------------------------
        for m in _CLASS_RE.finditer(source):
            cls_name = m.group(1)
            if not self._should_include(cls_name):
                continue
            bases = [b.strip() for b in (m.group(2) or "").split(",") if b.strip()]
            cls = ClassDoc(
                name=cls_name,
                bases=bases,
                docstring=doc_map.get(m.start(), ""),
                line_number=source[: m.start()].count("\n") + 1,
            )
            cls.methods = self._extract_methods(source, m.end())
            module.classes.append(cls)

        # -- Interfaces --------------------------------------------------------
        for m in _INTERFACE_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            bases = [b.strip() for b in (m.group(2) or "").split(",") if b.strip()]
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=bases,
                    docstring=doc_map.get(m.start(), ""),
                    decorators=["interface"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        # -- Structs -----------------------------------------------------------
        for m in _STRUCT_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            cls = ClassDoc(
                name=name,
                bases=[],
                docstring=doc_map.get(m.start(), ""),
                decorators=["struct"],
                line_number=source[: m.start()].count("\n") + 1,
            )
            cls.methods = self._extract_methods(source, m.end())
            module.classes.append(cls)

        # -- Enums -------------------------------------------------------------
        for m in _ENUM_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=[],
                    docstring=doc_map.get(m.start(), ""),
                    decorators=["enum"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        return module

    def _extract_methods(self, source: str, body_start: int) -> list[FunctionDoc]:
        """Extract methods from a class body."""
        body = _extract_brace_body(source, body_start)
        doc_map = _build_xmldoc_map(body)
        methods: list[FunctionDoc] = []

        for m in _METHOD_RE.finditer(body):
            ret_type = m.group(1).strip()
            name = m.group(2)

            # Skip property-like or control flow keywords
            if name in ("if", "for", "while", "switch", "return", "get", "set"):
                continue
            if not self._should_include(name):
                continue

            methods.append(
                FunctionDoc(
                    name=name,
                    args=_parse_csharp_params(m.group(3)),
                    return_type=ret_type,
                    docstring=doc_map.get(m.start(), ""),
                    is_method=True,
                    is_async="async"
                    in source[max(0, body_start + m.start() - 30) : body_start + m.start()],
                    line_number=body[: m.start()].count("\n") + 1,
                )
            )

        return methods


# -- Helpers -------------------------------------------------------------------


def _extract_brace_body(source: str, start: int) -> str:
    """Extract text from opening brace to matching close."""
    depth = 1
    pos = start
    while pos < len(source) and depth > 0:
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
        pos += 1
    return source[start:pos]


def _build_xmldoc_map(source: str) -> dict[int, str]:
    """Map declaration positions to preceding /// XML doc comments."""
    result: dict[int, str] = {}
    for m in _XMLDOC_RE.finditer(source):
        result[m.end()] = _clean_xmldoc(m.group(1))
    return result


def _clean_xmldoc(raw: str) -> str:
    """Clean C# XML doc comment, extracting summary text."""
    lines = raw.strip().split("\n")
    cleaned = []
    in_summary = False
    for line in lines:
        line = line.strip()
        if line.startswith("/// "):
            line = line[4:]
        elif line.startswith("///"):
            line = line[3:]

        # Extract text from <summary> tags
        if "<summary>" in line:
            in_summary = True
            line = re.sub(r"</?summary>", "", line).strip()
            if line:
                cleaned.append(line)
            continue
        if "</summary>" in line:
            in_summary = False
            line = re.sub(r"</summary>", "", line).strip()
            if line:
                cleaned.append(line)
            continue
        if in_summary:
            cleaned.append(line)
        elif not line.startswith("<"):
            cleaned.append(line)

    return "\n".join(cleaned).strip()


def _parse_csharp_params(raw: str) -> list[ArgInfo]:
    """Parse C# method parameters."""
    if not raw.strip():
        return []
    params: list[ArgInfo] = []
    depth = 0
    current: list[str] = []
    parts: list[str] = []
    for ch in raw:
        if ch in "<({[":
            depth += 1
            current.append(ch)
        elif ch in ">)}]":
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
        if not part:
            continue
        # Remove modifiers: ref, out, in, params, this
        part = re.sub(r"^(?:ref|out|in|params|this)\s+", "", part).strip()

        default = ""
        if "=" in part:
            part, default = part.rsplit("=", 1)
            part = part.strip()
            default = default.strip()

        tokens = part.rsplit(None, 1)
        if len(tokens) == 2:
            type_hint, name = tokens
        else:
            name = tokens[0]
            type_hint = ""
        params.append(ArgInfo(name=name, type_hint=type_hint, default=default))
    return params

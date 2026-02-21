"""Go regex-based parser.

Extracts functions, types, structs, methods, and interfaces from Go source files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from autoredocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autoredocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# -- Regex patterns -----------------------------------------------------------

# Go doc comment: consecutive // lines immediately before a declaration
_GODOC_RE = re.compile(
    r"((?:^//[^\n]*\n)+)",
    re.MULTILINE,
)

# Package declaration
_PACKAGE_RE = re.compile(r"^package\s+(\w+)", re.MULTILINE)

# Function: func FuncName(params) returnType {
_FUNC_RE = re.compile(
    r"^func\s+"
    r"(\w+)"  # function name
    r"\s*\(([^)]*)\)"  # params
    r"(?:\s*\(([^)]*)\)|\s+(\S[^{\n]*?))?"  # return type(s)
    r"\s*\{",
    re.MULTILINE,
)

# Method: func (receiver) MethodName(params) returnType {
_METHOD_RE = re.compile(
    r"^func\s+"
    r"\((\w+)\s+\*?(\w+)\)\s+"  # receiver
    r"(\w+)"  # method name
    r"\s*\(([^)]*)\)"  # params
    r"(?:\s*\(([^)]*)\)|\s+(\S[^{\n]*?))?"  # return type(s)
    r"\s*\{",
    re.MULTILINE,
)

# Struct: type Name struct {
_STRUCT_RE = re.compile(
    r"^type\s+(\w+)\s+struct\s*\{",
    re.MULTILINE,
)

# Interface: type Name interface {
_INTERFACE_RE = re.compile(
    r"^type\s+(\w+)\s+interface\s*\{",
    re.MULTILINE,
)

# Type alias: type Name = SomeType  or  type Name SomeType
_TYPE_ALIAS_RE = re.compile(
    r"^type\s+(\w+)\s+=?\s*([^\s{][^\n{]*)",
    re.MULTILINE,
)


class GoParser(BaseParser):
    """Regex-based parser for Go source files."""

    extensions = [".go"]

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        """Parse a Go source file and return a ModuleDoc."""
        filepath = Path(filepath)
        if not filepath.exists():
            return None

        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return None

        # Skip test files
        if filepath.name.endswith("_test.go"):
            return None

        pkg_match = _PACKAGE_RE.search(source)
        pkg = pkg_match.group(1) if pkg_match else filepath.stem

        module = ModuleDoc(
            filepath=str(filepath),
            module_name=f"{pkg}.{filepath.stem}" if pkg != filepath.stem else pkg,
        )

        # Build godoc map: position -> cleaned comment
        godoc_map = _build_godoc_map(source)

        # -- Structs (as classes) -----------------------------------------------
        for m in _STRUCT_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name) or not name[0].isupper():
                continue
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=[],
                    docstring=godoc_map.get(m.start(), ""),
                    decorators=["struct"],
                    line_number=source[: m.start()].count("\n") + 1,
                    methods=self._extract_methods(source, name),
                )
            )

        # -- Interfaces (as classes) -------------------------------------------
        for m in _INTERFACE_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name) or not name[0].isupper():
                continue
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=[],
                    docstring=godoc_map.get(m.start(), ""),
                    decorators=["interface"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        # -- Top-level functions -----------------------------------------------
        for m in _FUNC_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name) or not name[0].isupper():
                continue
            ret = (m.group(3) or m.group(4) or "").strip()
            module.functions.append(
                FunctionDoc(
                    name=name,
                    args=_parse_go_params(m.group(2)),
                    return_type=ret,
                    docstring=godoc_map.get(m.start(), ""),
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        return module

    def _extract_methods(self, source: str, struct_name: str) -> list[FunctionDoc]:
        """Find all methods with a receiver of the given struct type."""
        methods: list[FunctionDoc] = []
        for m in _METHOD_RE.finditer(source):
            receiver_type = m.group(2)
            if receiver_type != struct_name:
                continue
            name = m.group(3)
            if not name[0].isupper():
                continue
            ret = (m.group(5) or m.group(6) or "").strip()
            methods.append(
                FunctionDoc(
                    name=name,
                    args=_parse_go_params(m.group(4)),
                    return_type=ret,
                    docstring=_build_godoc_map(source).get(m.start(), ""),
                    is_method=True,
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )
        return methods


# -- Helpers -------------------------------------------------------------------


def _build_godoc_map(source: str) -> dict[int, str]:
    """Map declaration positions to their preceding godoc comments."""
    result: dict[int, str] = {}
    for m in _GODOC_RE.finditer(source):
        end = m.end()
        # The declaration starts right after the comment block
        result[end] = _clean_godoc(m.group(1))
    return result


def _clean_godoc(raw: str) -> str:
    """Clean Go doc comment lines."""
    lines = raw.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith("// "):
            line = line[3:]
        elif line.startswith("//"):
            line = line[2:]
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _parse_go_params(raw: str) -> list[ArgInfo]:
    """Parse Go function parameters."""
    if not raw.strip():
        return []
    params: list[ArgInfo] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if len(tokens) >= 2:
            name = tokens[0]
            type_hint = " ".join(tokens[1:])
        else:
            name = tokens[0]
            type_hint = ""
        params.append(ArgInfo(name=name, type_hint=type_hint))
    return params

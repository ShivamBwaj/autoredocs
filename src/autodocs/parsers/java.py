"""Java regex-based parser.

Extracts classes, interfaces, methods, and fields from Java source files
using regular expressions (no javac/Maven dependency required).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from autodocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autodocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# -- Regex patterns -----------------------------------------------------------

# Javadoc block: /** ... */
_JAVADOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# Class declaration
_CLASS_RE = re.compile(
    r"^(?:(?:public|private|protected|abstract|final|static)\s+)*"
    r"class\s+(\w+)"
    r"(?:<[^>]*>)?"  # generics
    r"(?:\s+extends\s+([\w.<>,\s]+))?"  # extends
    r"(?:\s+implements\s+([\w.<>,\s]+))?"  # implements
    r"\s*\{",
    re.MULTILINE,
)

# Interface declaration
_INTERFACE_RE = re.compile(
    r"^(?:(?:public|private|protected)\s+)?interface\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"(?:\s+extends\s+([\w.<>,\s]+))?"
    r"\s*\{",
    re.MULTILINE,
)

# Method declaration
_METHOD_RE = re.compile(
    r"^\s+(?:(?:public|private|protected|static|final|abstract|synchronized|native|"
    r"default|strictfp|override)\s+)*"
    r"(?:<[^>]*>\s+)?"  # generic return
    r"([\w.<>,\[\]]+)\s+"  # return type
    r"(\w+)"  # method name
    r"\s*\(([^)]*)\)"  # params
    r"(?:\s+throws\s+[\w,.\s]+)?"  # throws
    r"\s*[{;]",
    re.MULTILINE,
)

# Enum declaration
_ENUM_RE = re.compile(
    r"^(?:(?:public|private|protected)\s+)?enum\s+(\w+)"
    r"(?:\s+implements\s+([\w.<>,\s]+))?"
    r"\s*\{",
    re.MULTILINE,
)

# Package declaration
_PACKAGE_RE = re.compile(r"^package\s+([\w.]+)\s*;", re.MULTILINE)


class JavaParser(BaseParser):
    """Regex-based parser for Java source files."""

    extensions = [".java"]

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        filepath = Path(filepath)
        if not filepath.exists():
            return None

        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return None

        # Module name from package + filename
        pkg_match = _PACKAGE_RE.search(source)
        pkg = pkg_match.group(1) if pkg_match else ""
        module_name = f"{pkg}.{filepath.stem}" if pkg else filepath.stem

        module = ModuleDoc(
            filepath=str(filepath),
            module_name=module_name,
        )

        # Build Javadoc map
        javadoc_map = self._build_javadoc_map(source)

        # -- Classes -----------------------------------------------------------
        for m in _CLASS_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            bases = []
            if m.group(2):
                bases.append(m.group(2).strip())
            if m.group(3):
                bases.extend(b.strip() for b in m.group(3).split(","))

            cls = ClassDoc(
                name=name,
                bases=bases,
                docstring=javadoc_map.get(m.start(), ""),
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
                    docstring=javadoc_map.get(m.start(), ""),
                    decorators=["interface"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        # -- Enums (as classes) ------------------------------------------------
        for m in _ENUM_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=[],
                    docstring=javadoc_map.get(m.start(), ""),
                    decorators=["enum"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        return module

    def _build_javadoc_map(self, source: str) -> dict[int, str]:
        result: dict[int, str] = {}
        for m in _JAVADOC_RE.finditer(source):
            end = m.end()
            skip = len(source[end:]) - len(source[end:].lstrip())
            target_pos = end + skip
            result[target_pos] = _clean_javadoc(m.group(1))
        return result

    def _extract_methods(self, source: str, class_body_start: int) -> list[FunctionDoc]:
        methods: list[FunctionDoc] = []
        depth = 1
        pos = class_body_start

        while pos < len(source) and depth > 0:
            if source[pos] == "{":
                depth += 1
            elif source[pos] == "}":
                depth -= 1
            pos += 1

        body = source[class_body_start:pos]
        javadoc_map = self._build_javadoc_map(body)

        for m in _METHOD_RE.finditer(body):
            return_type = m.group(1)
            name = m.group(2)

            # Skip constructor-like (returnType == className) — keep as method
            if not self._should_include(name):
                continue

            methods.append(
                FunctionDoc(
                    name=name,
                    args=_parse_java_params(m.group(3)),
                    return_type=return_type,
                    docstring=javadoc_map.get(m.start(), ""),
                    is_method=True,
                    line_number=body[: m.start()].count("\n") + 1,
                )
            )

        return methods


# -- Helpers -------------------------------------------------------------------


def _clean_javadoc(raw: str) -> str:
    """Clean Javadoc comment text."""
    lines = raw.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith("* "):
            line = line[2:]
        elif line.startswith("*"):
            line = line[1:]
        if line.startswith("@"):
            continue
        cleaned.append(line.strip())
    return "\n".join(cleaned).strip()


def _parse_java_params(raw: str) -> list[ArgInfo]:
    """Parse Java method parameters."""
    if not raw.strip():
        return []
    params: list[ArgInfo] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        # Remove annotations like @NotNull, @Nullable
        part = re.sub(r"@\w+\s*", "", part).strip()
        # Handle varargs
        part = part.replace("...", "[]")
        tokens = part.split()
        if len(tokens) >= 2:
            type_hint = " ".join(tokens[:-1])
            name = tokens[-1]
        else:
            name = tokens[0]
            type_hint = ""
        params.append(ArgInfo(name=name, type_hint=type_hint))
    return params

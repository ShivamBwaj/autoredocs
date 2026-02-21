"""Kotlin regex-based parser.

Extracts classes, interfaces, objects, data classes, and functions from Kotlin source files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from autodocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autodocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)

_KDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)
_PACKAGE_RE = re.compile(r"^package\s+([\w.]+)", re.MULTILINE)

_CLASS_RE = re.compile(
    r"^(?:(?:public|private|protected|internal|abstract|open|sealed|data|inner|enum)\s+)*"
    r"class\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"(?:\s*\([^)]*\))?"  # primary constructor
    r"(?:\s*:\s*([^\n{]+))?"
    r"\s*\{?",
    re.MULTILINE,
)

_INTERFACE_RE = re.compile(
    r"^(?:(?:public|private|protected|internal|sealed|fun)\s+)*"
    r"interface\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"(?:\s*:\s*([^\n{]+))?"
    r"\s*\{?",
    re.MULTILINE,
)

_OBJECT_RE = re.compile(
    r"^(?:(?:public|private|protected|internal)\s+)*"
    r"(?:companion\s+)?object\s+(\w+)"
    r"(?:\s*:\s*([^\n{]+))?"
    r"\s*\{",
    re.MULTILINE,
)

_FUNC_RE = re.compile(
    r"^(?:[ \t]*)(?:(?:public|private|protected|internal|override|open|abstract|"
    r"inline|suspend|operator|infix|tailrec|external)\s+)*"
    r"fun\s+(?:<[^>]*>\s+)?"
    r"(?:\w+\.)?"  # extension receiver
    r"(\w+)"
    r"\s*\(([^)]*)\)"
    r"(?:\s*:\s*([^\n{=]+))?"
    r"\s*[{=]?",
    re.MULTILINE,
)

_METHOD_RE = re.compile(
    r"^[ \t]+(?:(?:public|private|protected|internal|override|open|abstract|"
    r"inline|suspend|operator|infix)\s+)*"
    r"fun\s+(?:<[^>]*>\s+)?"
    r"(\w+)"
    r"\s*\(([^)]*)\)"
    r"(?:\s*:\s*([^\n{=]+))?"
    r"\s*[{=]?",
    re.MULTILINE,
)


class KotlinParser(BaseParser):
    """Regex-based parser for Kotlin source files."""

    extensions = [".kt", ".kts"]

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        filepath = Path(filepath)
        if not filepath.exists():
            return None
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return None

        pkg_match = _PACKAGE_RE.search(source)
        pkg = pkg_match.group(1) if pkg_match else ""
        name = f"{pkg}.{filepath.stem}" if pkg else filepath.stem

        module = ModuleDoc(filepath=str(filepath), module_name=name)
        doc_map = _build_kdoc_map(source)

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

        for m in _OBJECT_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=[],
                    docstring=doc_map.get(m.start(), ""),
                    decorators=["object"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        for m in _FUNC_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            line_start = source.rfind("\n", 0, m.start()) + 1
            if m.start() - line_start > 0:
                continue
            module.functions.append(
                FunctionDoc(
                    name=name,
                    args=_parse_kotlin_params(m.group(2)),
                    return_type=(m.group(3) or "").strip(),
                    docstring=doc_map.get(m.start(), ""),
                    is_async="suspend" in source[max(0, m.start() - 30) : m.start()],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )
        return module

    def _extract_methods(self, source: str, body_start: int) -> list[FunctionDoc]:
        body = _extract_brace_body(source, body_start)
        doc_map = _build_kdoc_map(body)
        methods: list[FunctionDoc] = []
        for m in _METHOD_RE.finditer(body):
            name = m.group(1)
            if not self._should_include(name):
                continue
            methods.append(
                FunctionDoc(
                    name=name,
                    args=_parse_kotlin_params(m.group(2)),
                    return_type=(m.group(3) or "").strip(),
                    docstring=doc_map.get(m.start(), ""),
                    is_method=True,
                    line_number=body[: m.start()].count("\n") + 1,
                )
            )
        return methods


def _extract_brace_body(source: str, start: int) -> str:
    depth = 1
    pos = start
    while pos < len(source) and depth > 0:
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
        pos += 1
    return source[start:pos]


def _build_kdoc_map(source: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for m in _KDOC_RE.finditer(source):
        end = m.end()
        skip = len(source[end:]) - len(source[end:].lstrip())
        result[end + skip] = _clean_kdoc(m.group(1))
    return result


def _clean_kdoc(raw: str) -> str:
    lines = raw.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith("* "):
            line = line[2:]
        elif line.startswith("*"):
            line = line[1:]
        if line.strip().startswith("@"):
            continue
        cleaned.append(line.strip())
    return "\n".join(cleaned).strip()


def _parse_kotlin_params(raw: str) -> list[ArgInfo]:
    if not raw.strip():
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
        if not part:
            continue
        default = ""
        if "=" in part:
            part, default = part.rsplit("=", 1)
            part = part.strip()
            default = default.strip()
        if ":" in part:
            name, type_hint = part.split(":", 1)
        else:
            name, type_hint = part, ""
        name = name.strip().removeprefix("vararg ")
        params.append(ArgInfo(name=name.strip(), type_hint=type_hint.strip(), default=default))
    return params

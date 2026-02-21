"""Ruby regex-based parser.

Extracts classes, modules, and method definitions from Ruby source files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from autodocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autodocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)

_RDOC_RE = re.compile(r"((?:^[ \t]*#[^\n]*\n)+)", re.MULTILINE)
_CLASS_RE = re.compile(r"^(?:[ \t]*)class\s+(\w+)(?:\s*<\s*(\w[^\n]*))?", re.MULTILINE)
_MODULE_RE = re.compile(r"^(?:[ \t]*)module\s+(\w+)", re.MULTILINE)
_METHOD_RE = re.compile(r"^[ \t]*def\s+(?:self\.)?(\w+[?!=]?)(?:\s*\(([^)]*)\))?", re.MULTILINE)
_BLOCK_OPENERS = re.compile(
    r"^\s*(?:class|module|def|if|unless|while|until|for|case|begin|do)\b", re.MULTILINE
)


class RubyParser(BaseParser):
    """Regex-based parser for Ruby source files."""

    extensions = [".rb"]

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        filepath = Path(filepath)
        if not filepath.exists():
            return None
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return None

        module = ModuleDoc(filepath=str(filepath), module_name=filepath.stem)
        doc_map = _build_rdoc_map(source)

        for m in _MODULE_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=[],
                    docstring=doc_map.get(m.start(), ""),
                    decorators=["module"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        for m in _CLASS_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            bases = [m.group(2).strip()] if m.group(2) else []
            cls = ClassDoc(
                name=name,
                bases=bases,
                docstring=doc_map.get(m.start(), ""),
                line_number=source[: m.start()].count("\n") + 1,
            )
            cls.methods = self._extract_class_methods(source, m.end())
            module.classes.append(cls)

        for m in _METHOD_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            line_start = source.rfind("\n", 0, m.start()) + 1
            if m.start() - line_start > 0:
                continue
            module.functions.append(
                FunctionDoc(
                    name=name,
                    args=_parse_ruby_params(m.group(2) or ""),
                    return_type="",
                    docstring=doc_map.get(m.start(), ""),
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )
        return module

    def _extract_class_methods(self, source: str, class_start: int) -> list[FunctionDoc]:
        body = _extract_ruby_body(source, class_start)
        doc_map = _build_rdoc_map(body)
        methods: list[FunctionDoc] = []
        for m in _METHOD_RE.finditer(body):
            name = m.group(1)
            if not self._should_include(name):
                continue
            methods.append(
                FunctionDoc(
                    name=name,
                    args=_parse_ruby_params(m.group(2) or ""),
                    return_type="",
                    docstring=doc_map.get(m.start(), ""),
                    is_method=True,
                    line_number=body[: m.start()].count("\n") + 1,
                )
            )
        return methods


def _extract_ruby_body(source: str, start: int) -> str:
    depth = 1
    lines = source[start:].split("\n")
    body_lines: list[str] = []
    for line in lines[1:]:
        stripped = line.strip()
        if _BLOCK_OPENERS.match(line) and not stripped.endswith("end"):
            depth += 1
        if stripped == "end" or stripped.startswith("end ") or stripped.startswith("end;"):
            depth -= 1
            if depth == 0:
                break
        body_lines.append(line)
    return "\n".join(body_lines)


def _build_rdoc_map(source: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for m in _RDOC_RE.finditer(source):
        result[m.end()] = _clean_rdoc(m.group(1))
    return result


def _clean_rdoc(raw: str) -> str:
    lines = raw.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            line = line[2:]
        elif line.startswith("#"):
            line = line[1:]
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _parse_ruby_params(raw: str) -> list[ArgInfo]:
    if not raw.strip():
        return []
    params: list[ArgInfo] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        default = ""
        if "=" in part:
            part, default = part.split("=", 1)
            part = part.strip()
            default = default.strip()
        name = part.strip().rstrip(":")
        params.append(ArgInfo(name=name, type_hint="", default=default))
    return params

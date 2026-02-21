"""Rust regex-based parser.

Extracts functions, structs, enums, traits, and impl blocks from Rust source files.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from autodocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autodocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# -- Regex patterns -----------------------------------------------------------

# Rust doc comment: consecutive /// lines
_RUSTDOC_RE = re.compile(
    r"((?:^[ \t]*///[^\n]*\n)+)",
    re.MULTILINE,
)

# Module-level doc comment: //!
_MOD_DOC_RE = re.compile(
    r"((?:^[ \t]*//![^\n]*\n)+)",
    re.MULTILINE,
)

# pub fn / fn
_FUNC_RE = re.compile(
    r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:extern\s+\"[^\"]*\"\s+)?"
    r"fn\s+(\w+)"
    r"(?:<[^>]*>)?"  # generics
    r"\s*\(([^)]*)\)"  # params
    r"(?:\s*->\s*([^\n{;]+))?"  # return type
    r"\s*(?:where[^{]*)?[{;]",
    re.MULTILINE,
)

# struct Name { ... } or struct Name(...);
_STRUCT_RE = re.compile(
    r"^(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"\s*[({]",
    re.MULTILINE,
)

# enum Name { ... }
_ENUM_RE = re.compile(
    r"^(?:pub(?:\([^)]*\))?\s+)?enum\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"\s*\{",
    re.MULTILINE,
)

# trait Name { ... }
_TRAIT_RE = re.compile(
    r"^(?:pub(?:\([^)]*\))?\s+)?(?:unsafe\s+)?trait\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"(?:\s*:\s*[^{]+)?"
    r"\s*\{",
    re.MULTILINE,
)

# impl [Trait for] Type { ... }
_IMPL_RE = re.compile(
    r"^(?:unsafe\s+)?impl(?:<[^>]*>)?\s+"
    r"(?:(\w+)\s+for\s+)?"  # optional trait
    r"(\w+)"  # type
    r"(?:<[^>]*>)?"
    r"\s*\{",
    re.MULTILINE,
)


class RustParser(BaseParser):
    """Regex-based parser for Rust source files."""

    extensions = [".rs"]

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        """Parse a Rust source file and return a ModuleDoc."""
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

        # Module-level doc
        mod_doc = _MOD_DOC_RE.search(source)
        if mod_doc and mod_doc.start() < 100:
            module.docstring = _clean_rustdoc(mod_doc.group(1), is_mod=True)

        doc_map = _build_doc_map(source)

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
                    methods=self._find_impl_methods(source, name, doc_map),
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
                    docstring=doc_map.get(m.start(), ""),
                    decorators=["enum"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        # -- Traits (as classes) -----------------------------------------------
        for m in _TRAIT_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=[],
                    docstring=doc_map.get(m.start(), ""),
                    decorators=["trait"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        # -- Top-level functions -----------------------------------------------
        for m in _FUNC_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            # Skip methods inside impl blocks (indented)
            line_start = source.rfind("\n", 0, m.start()) + 1
            indent = m.start() - line_start
            if indent > 0:
                continue
            module.functions.append(
                FunctionDoc(
                    name=name,
                    args=_parse_rust_params(m.group(2)),
                    return_type=(m.group(3) or "").strip(),
                    docstring=doc_map.get(m.start(), ""),
                    is_async="async" in source[max(0, m.start() - 30) : m.start()],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        return module

    def _find_impl_methods(
        self, source: str, type_name: str, doc_map: dict[int, str]
    ) -> list[FunctionDoc]:
        """Extract methods from impl blocks for the given type."""
        methods: list[FunctionDoc] = []
        for impl_m in _IMPL_RE.finditer(source):
            if impl_m.group(2) != type_name:
                continue
            # Find body of impl block
            body_start = impl_m.end()
            body = _extract_brace_body(source, body_start)
            body_doc_map = _build_doc_map(body)

            for m in _FUNC_RE.finditer(body):
                name = m.group(1)
                if not self._should_include(name):
                    continue
                methods.append(
                    FunctionDoc(
                        name=name,
                        args=_parse_rust_params(m.group(2)),
                        return_type=(m.group(3) or "").strip(),
                        docstring=body_doc_map.get(m.start(), ""),
                        is_method=True,
                        line_number=source[: body_start + m.start()].count("\n") + 1,
                    )
                )
        return methods


# -- Helpers -------------------------------------------------------------------


def _extract_brace_body(source: str, start: int) -> str:
    """Extract text inside braces starting at position (after opening {)."""
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
    """Map declaration positions to preceding /// doc comments."""
    result: dict[int, str] = {}
    for m in _RUSTDOC_RE.finditer(source):
        result[m.end()] = _clean_rustdoc(m.group(1))
    return result


def _clean_rustdoc(raw: str, is_mod: bool = False) -> str:
    """Clean Rust doc comment lines."""
    prefix = "//!" if is_mod else "///"
    lines = raw.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith(f"{prefix} "):
            line = line[len(prefix) + 1 :]
        elif line.startswith(prefix):
            line = line[len(prefix) :]
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _parse_rust_params(raw: str) -> list[ArgInfo]:
    """Parse Rust function parameters."""
    if not raw.strip():
        return []
    params: list[ArgInfo] = []
    # Split respecting generics
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
        if not part or part == "self" or part == "&self" or part == "&mut self":
            continue
        if ":" in part:
            name, type_hint = part.split(":", 1)
            name = name.strip().lstrip("mut ")
            params.append(ArgInfo(name=name.strip(), type_hint=type_hint.strip()))
        else:
            params.append(ArgInfo(name=part, type_hint=""))
    return params

"""TypeScript / JavaScript regex-based parser.

Extracts functions, classes, interfaces, and type aliases from TS/JS files
using regular expressions (no Node.js dependency required).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from autodocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autodocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)

# -- Regex patterns -----------------------------------------------------------

# JSDoc block: /** ... */
_JSDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)

# function declarations
_FUNC_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)"
    r"\s*(?:<[^>]*>)?"  # optional generics
    r"\s*\(([^)]*)\)"  # params
    r"(?:\s*:\s*([^\s{]+))?"  # optional return type
    r"\s*\{",
    re.MULTILINE,
)

# Arrow / const functions
_ARROW_RE = re.compile(
    r"^(?:export\s+)?(?:const|let|var)\s+(\w+)"
    r"\s*(?::\s*[^=]+?)?\s*=\s*"
    r"(?:async\s+)?"
    r"\(([^)]*)\)"  # params
    r"(?:\s*:\s*([^\s=>{]+))?"  # return type
    r"\s*=>\s*",
    re.MULTILINE,
)

# Class declaration
_CLASS_RE = re.compile(
    r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)"
    r"(?:<[^>]*>)?"  # generics
    r"(?:\s+extends\s+([\w.<>,\s]+))?"  # extends
    r"(?:\s+implements\s+([\w.<>,\s]+))?"  # implements
    r"\s*\{",
    re.MULTILINE,
)

# Interface declaration
_INTERFACE_RE = re.compile(
    r"^(?:export\s+)?interface\s+(\w+)"
    r"(?:<[^>]*>)?"
    r"(?:\s+extends\s+([\w.<>,\s]+))?"
    r"\s*\{",
    re.MULTILINE,
)

# Type alias
_TYPE_ALIAS_RE = re.compile(
    r"^(?:export\s+)?type\s+(\w+)(?:<[^>]*>)?\s*=\s*(.+?);\s*$",
    re.MULTILINE,
)

# Method inside a class body (simplified)
_METHOD_RE = re.compile(
    r"^\s+(?:(?:public|private|protected|static|async|readonly|override|abstract)\s+)*"
    r"(\w+)"
    r"\s*(?:<[^>]*>)?"
    r"\s*\(([^)]*)\)"
    r"(?:\s*:\s*([^\s{;]+))?"
    r"\s*[{;]",
    re.MULTILINE,
)


class TypeScriptParser(BaseParser):
    """Regex-based parser for TypeScript and JavaScript files."""

    extensions = [".ts", ".tsx", ".js", ".jsx"]

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        """Parse a JavaScript file and extract its documentation.

        Args:
            filepath: The path to the JavaScript file to parse. Can be a string or a Path object.

        Returns:
            A ModuleDoc object representing the parsed JavaScript file, or None if the file does not exist or cannot be read.

        Raises:
            OSError: If the file cannot be read due to a system-level error.
            UnicodeDecodeError: If the file cannot be read due to encoding issues.
        """
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

        # Extract top-level doc comment (first JSDoc in file)
        first_doc = _JSDOC_RE.search(source)
        if first_doc and first_doc.start() < 50:  # near start of file
            module.docstring = _clean_jsdoc(first_doc.group(1))

        # Build a map of JSDoc comments by their end position
        jsdoc_map = self._build_jsdoc_map(source)

        # -- Functions ---------------------------------------------------------
        for m in _FUNC_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            module.functions.append(
                FunctionDoc(
                    name=name,
                    args=_parse_params(m.group(2)),
                    return_type=m.group(3) or "",
                    docstring=jsdoc_map.get(m.start(), ""),
                    is_async="async" in source[max(0, m.start() - 20) : m.start()],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        for m in _ARROW_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            module.functions.append(
                FunctionDoc(
                    name=name,
                    args=_parse_params(m.group(2)),
                    return_type=m.group(3) or "",
                    docstring=jsdoc_map.get(m.start(), ""),
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        # -- Classes -----------------------------------------------------------
        for m in _CLASS_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            bases = [b.strip() for b in (m.group(2) or "").split(",") if b.strip()]
            cls = ClassDoc(
                name=name,
                bases=bases,
                docstring=jsdoc_map.get(m.start(), ""),
                line_number=source[: m.start()].count("\n") + 1,
            )
            # Extract methods from class body
            cls.methods = self._extract_class_methods(source, m.end())
            module.classes.append(cls)

        # -- Interfaces (as classes) -------------------------------------------
        for m in _INTERFACE_RE.finditer(source):
            name = m.group(1)
            if not self._should_include(name):
                continue
            bases = [b.strip() for b in (m.group(2) or "").split(",") if b.strip()]
            module.classes.append(
                ClassDoc(
                    name=name,
                    bases=bases,
                    docstring=jsdoc_map.get(m.start(), ""),
                    decorators=["interface"],
                    line_number=source[: m.start()].count("\n") + 1,
                )
            )

        return module

    def _build_jsdoc_map(self, source: str) -> dict[int, str]:
        """Build mapping: position after JSDoc -> cleaned docstring."""
        result: dict[int, str] = {}
        for m in _JSDOC_RE.finditer(source):
            end = m.end()
            # Skip whitespace/newlines after the comment
            skip = len(source[end:]) - len(source[end:].lstrip())
            target_pos = end + skip
            result[target_pos] = _clean_jsdoc(m.group(1))
        return result

    def _extract_class_methods(self, source: str, class_body_start: int) -> list[FunctionDoc]:
        """Extract methods from a class body (simplified brace matching)."""
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
        jsdoc_map = self._build_jsdoc_map(body)

        for m in _METHOD_RE.finditer(body):
            name = m.group(1)
            if name in ("constructor", "if", "for", "while", "switch", "return"):
                if name != "constructor":
                    continue
            if not self._should_include(name):
                continue

            methods.append(
                FunctionDoc(
                    name=name,
                    args=_parse_params(m.group(2)),
                    return_type=m.group(3) or "",
                    docstring=jsdoc_map.get(m.start(), ""),
                    is_method=True,
                    line_number=body[: m.start()].count("\n") + 1,
                )
            )

        return methods


# -- Helpers -------------------------------------------------------------------


def _clean_jsdoc(raw: str) -> str:
    """Remove leading * from JSDoc lines, trim whitespace."""
    lines = raw.strip().split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line.startswith("* "):
            line = line[2:]
        elif line.startswith("*"):
            line = line[1:]
        # Skip @param/@returns tags for the docstring (keep human text)
        if line.startswith("@"):
            continue
        cleaned.append(line.strip())
    return "\n".join(cleaned).strip()


def _parse_params(raw: str) -> list[ArgInfo]:
    """Parse a TypeScript/JS parameter list string."""
    if not raw.strip():
        return []
    params: list[ArgInfo] = []
    for part in _split_params(raw):
        part = part.strip()
        if not part:
            continue
        # Handle destructured params
        if part.startswith("{") or part.startswith("["):
            params.append(ArgInfo(name=part.split(":")[0].strip(), type_hint="object"))
            continue

        # name?: Type = default  OR  name: Type = default
        optional = "?" in part.split(":")[0] if ":" in part else "?" in part
        part_clean = part.replace("?", "")

        if "=" in part_clean:
            lhs, default = part_clean.split("=", 1)
            default = default.strip()
        else:
            lhs, default = part_clean, ""

        if ":" in lhs:
            name, type_hint = lhs.split(":", 1)
        else:
            name, type_hint = lhs, ""

        name = name.strip()
        type_hint = type_hint.strip()
        if optional and type_hint and not type_hint.endswith("| undefined"):
            type_hint += " | undefined"

        params.append(ArgInfo(name=name, type_hint=type_hint, default=default))
    return params


def _split_params(raw: str) -> list[str]:
    """Split a parameter string respecting nested <> and {} brackets."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in raw:
        if ch in "<{([":
            depth += 1
            current.append(ch)
        elif ch in ">})]":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts

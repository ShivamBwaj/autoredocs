"""AI-powered docstring generation using Groq API (Llama models).

Groq provides an OpenAI-compatible API at https://api.groq.com/openai/v1.
We use the openai Python client with a custom base_url to connect.

Supports all languages: Python (AST-based), and generic AI fill for
Java, TypeScript, Go, Rust, C#, C/C++, Ruby, Kotlin.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.1-8b-instant"

# -- Language configuration ---------------------------------------------------

LANGUAGE_MAP: dict[str, dict[str, str]] = {
    ".py": {"name": "Python", "comment": '"""docstring"""', "style": "docstring"},
    ".java": {"name": "Java", "comment": "/** Javadoc */", "style": "javadoc"},
    ".ts": {"name": "TypeScript", "comment": "/** JSDoc */", "style": "jsdoc"},
    ".tsx": {"name": "TypeScript", "comment": "/** JSDoc */", "style": "jsdoc"},
    ".js": {"name": "JavaScript", "comment": "/** JSDoc */", "style": "jsdoc"},
    ".jsx": {"name": "JavaScript", "comment": "/** JSDoc */", "style": "jsdoc"},
    ".go": {"name": "Go", "comment": "// GoDoc", "style": "godoc"},
    ".rs": {"name": "Rust", "comment": "/// rustdoc", "style": "rustdoc"},
    ".cs": {"name": "C#", "comment": "/// XML doc", "style": "xmldoc"},
    ".c": {"name": "C", "comment": "/** Doxygen */", "style": "doxygen"},
    ".cpp": {"name": "C++", "comment": "/** Doxygen */", "style": "doxygen"},
    ".cc": {"name": "C++", "comment": "/** Doxygen */", "style": "doxygen"},
    ".h": {"name": "C/C++", "comment": "/** Doxygen */", "style": "doxygen"},
    ".hpp": {"name": "C++", "comment": "/** Doxygen */", "style": "doxygen"},
    ".rb": {"name": "Ruby", "comment": "# RDoc", "style": "rdoc"},
    ".kt": {"name": "Kotlin", "comment": "/** KDoc */", "style": "kdoc"},
    ".kts": {"name": "Kotlin", "comment": "/** KDoc */", "style": "kdoc"},
}

# -- Docstring style templates (Python-specific for AST mode) -----------------

STYLE_PROMPTS: dict[str, str] = {
    "google": (
        "Write a Google-style Python docstring. Include:\n"
        "- A one-line summary\n"
        "- Args section with type descriptions\n"
        "- Returns section describing the return value\n"
        "- Raises section if exceptions are raised\n"
    ),
    "numpy": (
        "Write a NumPy-style Python docstring. Include:\n"
        "- A one-line summary\n"
        "- Parameters section with type\n"
        "- Returns section\n"
    ),
    "sphinx": (
        "Write a Sphinx-style Python docstring. Include:\n"
        "- A one-line summary\n"
        "- :param name: description lines\n"
        "- :returns: description\n"
        "- :raises ExcType: description (if applicable)\n"
    ),
}

SYSTEM_PROMPT = (
    "You are a documentation expert. "
    "Given a function or class signature and its source body, "
    "write a clear, accurate, and concise docstring. "
    "Return ONLY the docstring text (no triple quotes, no code fences). "
    "Do not explain your reasoning."
)

GENERIC_SYSTEM_PROMPT = (
    "You are an expert code documentation writer. "
    "Given source code in {language}, add missing documentation comments "
    "to all public functions, methods, classes, and types that lack them. "
    "Use the {style} comment style ({comment_format}). "
    "Return the COMPLETE modified source code with documentation added. "
    "Do NOT remove any existing code or comments. "
    "Do NOT wrap the output in code fences. "
    "Do NOT add any explanation."
)


class DocGenerator:
    """Generates docstrings for code using Groq API (Llama models).

    Uses the OpenAI-compatible endpoint at api.groq.com.
    Supports Python (AST-based) and all other languages (generic AI fill).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        style: str = "google",
        max_tokens: int = 300,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model = model
        self.style = style
        self.max_tokens = max_tokens
        self._client = None

        if not self.api_key:
            raise ValueError(
                "Groq API key not found. Set GROQ_API_KEY in your .env or pass via config."
            )

    @property
    def client(self):
        """Lazy-init OpenAI-compatible client pointed at Groq."""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key,
                base_url=GROQ_BASE_URL,
            )
        return self._client

    # -- Python-specific (AST-based) ------------------------------------------

    def generate_docstring(self, signature: str, body: str = "") -> str:
        """Generate a docstring for a Python function/class signature."""
        style_guide = STYLE_PROMPTS.get(self.style, STYLE_PROMPTS["google"])
        user_msg = f"{style_guide}\n\nSignature:\n```python\n{signature}\n```\n"
        if body:
            truncated = body[:1500]
            user_msg += f"\nBody:\n```python\n{truncated}\n```\n"
        user_msg += "\nWrite the docstring now:"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=self.max_tokens,
                temperature=0.3,
            )
            docstring = response.choices[0].message.content.strip()
            docstring = docstring.strip("`\"'")
            if docstring.startswith("python\n"):
                docstring = docstring[7:]
            return docstring
        except Exception as exc:
            logger.warning("AI docstring generation failed: %s", exc)
            return ""

    def fill_missing_docstrings(
        self,
        filepath: Path,
        *,
        dry_run: bool = False,
    ) -> list[dict]:
        """Scan a Python file and fill in missing docstrings using AST."""
        source = filepath.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError:
            return []

        suggestions: list[dict] = []
        lines = source.splitlines(keepends=True)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            existing = ast.get_docstring(node)
            if existing:
                continue
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue

            sig = ast.unparse(node)[:200]
            body_lines = lines[node.lineno - 1 : node.end_lineno]
            body_src = "".join(body_lines)
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            docstring = self.generate_docstring(sig, body_src)

            if docstring:
                suggestions.append(
                    {"name": node.name, "type": kind, "line": node.lineno, "docstring": docstring}
                )

        if not dry_run and suggestions:
            self._write_docstrings(filepath, source, tree, suggestions)

        return suggestions

    def _write_docstrings(
        self, filepath: Path, source: str, tree: ast.Module, suggestions: list[dict]
    ) -> None:
        """Insert generated docstrings into a Python source file."""
        lines = source.splitlines(keepends=True)
        nodes_by_line: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nodes_by_line[node.lineno] = node

        for suggestion in sorted(suggestions, key=lambda s: s["line"], reverse=True):
            node = nodes_by_line.get(suggestion["line"])
            if node is None:
                continue
            if node.body:
                insert_line = node.body[0].lineno - 1
            else:
                insert_line = node.end_lineno - 1

            def_line = lines[node.lineno - 1]
            base_indent = len(def_line) - len(def_line.lstrip())
            doc_indent = " " * (base_indent + 4)
            doc_text = suggestion["docstring"]
            doc_lines = doc_text.split("\n")
            if len(doc_lines) == 1:
                formatted = f'{doc_indent}"""{doc_text}"""\n'
            else:
                formatted = f'{doc_indent}"""{doc_lines[0]}\n'
                for dl in doc_lines[1:]:
                    formatted += f"{doc_indent}{dl}\n"
                formatted += f'{doc_indent}"""\n'
            lines.insert(insert_line, formatted)

        filepath.write_text("".join(lines), encoding="utf-8")

    # -- Generic AI fill (all other languages) --------------------------------

    def fill_missing_docs_generic(
        self,
        filepath: Path,
        *,
        dry_run: bool = False,
    ) -> list[dict]:
        """Add missing doc comments to any supported language file using AI.

        Instead of AST manipulation, sends the full source to the AI and asks
        it to return the source with documentation comments added.

        Returns list of dicts with 'name', 'type' for reporting.
        """
        ext = filepath.suffix.lower()
        lang_info = LANGUAGE_MAP.get(ext)
        if not lang_info:
            return []

        source = filepath.read_text(encoding="utf-8")
        if not source.strip():
            return []

        # Truncate very large files to stay within token limits
        max_chars = 6000
        truncated = source[:max_chars]
        was_truncated = len(source) > max_chars

        system_msg = GENERIC_SYSTEM_PROMPT.format(
            language=lang_info["name"],
            style=lang_info["style"],
            comment_format=lang_info["comment"],
        )

        user_msg = f"Add documentation comments to this {lang_info['name']} code:\n\n{truncated}"
        if was_truncated:
            user_msg += "\n\n(File was truncated. Only document what you see.)"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=4096,
                temperature=0.2,
            )
            result = response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("AI generic doc fill failed for %s: %s", filepath, exc)
            return []

        # Strip code fences if the model wrapped them
        if result.startswith("```"):
            first_nl = result.index("\n")
            result = result[first_nl + 1 :]
        if result.endswith("```"):
            result = result[:-3].rstrip()

        # Only write if the AI actually changed the code
        if result.strip() == source.strip():
            return []

        # Build a simple diff report
        suggestions = self._diff_report(source, result, lang_info["name"])

        if not dry_run and suggestions:
            if was_truncated:
                # Only replace the documented portion, keep the rest
                filepath.write_text(result + source[max_chars:], encoding="utf-8")
            else:
                filepath.write_text(result, encoding="utf-8")

        return suggestions

    def _diff_report(self, original: str, modified: str, language: str) -> list[dict]:
        """Create a simple report of what changed between original and modified."""
        orig_lines = set(original.splitlines())
        mod_lines = modified.splitlines()
        suggestions: list[dict] = []
        line_num = 0

        for line in mod_lines:
            line_num += 1
            if line not in orig_lines and line.strip():
                # This is a new line added by the AI, likely a doc comment
                stripped = line.strip()
                is_doc = any(
                    [
                        stripped.startswith("/**"),
                        stripped.startswith("///"),
                        stripped.startswith("//!"),
                        stripped.startswith("// "),
                        stripped.startswith("#"),
                        stripped.startswith('"""'),
                        stripped.startswith("*"),
                    ]
                )
                if is_doc and stripped not in ("*", "*/", "/**", '"""'):
                    suggestions.append(
                        {
                            "name": f"{language}_doc",
                            "type": "doc_comment",
                            "line": line_num,
                            "docstring": stripped,
                        }
                    )

        # Deduplicate: count unique doc blocks, not individual lines
        if suggestions:
            # Group consecutive doc lines as one suggestion
            groups: list[dict] = []
            prev_line = -2
            for s in suggestions:
                if s["line"] == prev_line + 1:
                    # Same doc block
                    groups[-1]["docstring"] += "\n" + s["docstring"]
                else:
                    groups.append(s)
                prev_line = s["line"]
            return groups

        return suggestions

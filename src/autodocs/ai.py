"""AI-powered docstring generation using Groq API (Llama models).

Groq provides an OpenAI-compatible API at https://api.groq.com/openai/v1.
We use the openai Python client with a custom base_url to connect.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from project root (or cwd)
load_dotenv()

# -- Constants ----------------------------------------------------------------

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# -- Docstring style templates ------------------------------------------------

STYLE_PROMPTS: dict[str, str] = {
    "google": (
        "Write a Google-style Python docstring. Include:\n"
        "- A one-line summary\n"
        "- Args section with type descriptions\n"
        "- Returns section describing the return value\n"
        "- Raises section if exceptions are raised\n"
        "Example:\n"
        '    """Fetch records from the database.\n\n'
        "    Args:\n"
        "        table: The table name to query.\n"
        "        limit: Maximum number of records.\n\n"
        "    Returns:\n"
        "        A list of record dictionaries.\n"
        '    """'
    ),
    "numpy": (
        "Write a NumPy-style Python docstring. Include:\n"
        "- A one-line summary\n"
        "- Parameters section with type\n"
        "- Returns section\n"
        "Example:\n"
        '    """Fetch records from the database.\n\n'
        "    Parameters\n"
        "    ----------\n"
        "    table : str\n"
        "        The table name to query.\n"
        "    limit : int\n"
        "        Maximum number of records.\n\n"
        "    Returns\n"
        "    -------\n"
        "    list\n"
        "        A list of record dictionaries.\n"
        '    """'
    ),
    "sphinx": (
        "Write a Sphinx-style Python docstring. Include:\n"
        "- A one-line summary\n"
        "- :param name: description lines\n"
        "- :returns: description\n"
        "- :raises ExcType: description (if applicable)\n"
        "Example:\n"
        '    """Fetch records from the database.\n\n'
        "    :param table: The table name to query.\n"
        "    :param limit: Maximum number of records.\n"
        "    :returns: A list of record dictionaries.\n"
        '    """'
    ),
}

SYSTEM_PROMPT = (
    "You are a documentation expert. "
    "Given a function or class signature and its source body, "
    "write a clear, accurate, and concise docstring. "
    "Return ONLY the docstring text (no triple quotes, no code fences). "
    "Do not explain your reasoning."
)


class DocGenerator:
    """Generates docstrings for code using Groq API (Llama models).

    Uses the OpenAI-compatible endpoint at api.groq.com.
    Requires GROQ_API_KEY environment variable or passed via config.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        style: str = "google",
        max_tokens: int = 300,
    ):
        """Initialize the Groq API client.

        Args:
            api_key: The Groq API key to use, or None to load from the environment variable GROQ_API_KEY.
            model: The default Groq model to use.
            style: The style of the Groq API response (default: 'google').
            max_tokens: The maximum number of tokens to use in the Groq API request (default: 300).

        Raises:
            ValueError: If the Groq API key is not found in the environment variable or passed via config.
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model = model
        self.style = style
        self.max_tokens = max_tokens
        self._client = None

        if not self.api_key:
            raise ValueError(
                "Groq API key not found. Set GROQ_API_KEY in your .env file or pass it via config."
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

    def generate_docstring(self, signature: str, body: str = "") -> str:
        """Generate a docstring for a given function/class signature.

        Args:
            signature: The function or class signature line.
            body: Optional source body of the function/class.

        Returns:
            The generated docstring text.
        """
        style_guide = STYLE_PROMPTS.get(self.style, STYLE_PROMPTS["google"])

        user_msg = f"{style_guide}\n\nSignature:\n```python\n{signature}\n```\n"
        if body:
            # Limit body size to avoid token waste
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
            # Strip any accidental triple-quote wrapping
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
        """Scan a file and fill in missing docstrings.

        Args:
            filepath: Path to the Python source file.
            dry_run: If True, return suggestions without writing.

        Returns:
            List of dicts with 'name', 'type', 'docstring' for each filled item.
        """
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

            # Skip if already has docstring
            existing = ast.get_docstring(node)
            if existing:
                continue

            # Skip private/dunder
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue

            sig = ast.unparse(node)[:200]  # brief signature
            # Get the body source (for context)
            body_lines = lines[node.lineno - 1 : node.end_lineno]
            body_src = "".join(body_lines)

            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            docstring = self.generate_docstring(sig, body_src)

            if docstring:
                suggestions.append(
                    {
                        "name": node.name,
                        "type": kind,
                        "line": node.lineno,
                        "docstring": docstring,
                    }
                )

        if not dry_run and suggestions:
            self._write_docstrings(filepath, source, tree, suggestions)

        return suggestions

    def _write_docstrings(
        self,
        filepath: Path,
        source: str,
        tree: ast.Module,
        suggestions: list[dict],
    ) -> None:
        """Insert generated docstrings into the source file."""
        lines = source.splitlines(keepends=True)

        # Process in reverse order so line numbers stay valid
        nodes_by_line: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nodes_by_line[node.lineno] = node

        for suggestion in sorted(suggestions, key=lambda s: s["line"], reverse=True):
            node = nodes_by_line.get(suggestion["line"])
            if node is None:
                continue

            # Find insertion point: right after the def/class line
            # The docstring goes as the first statement in the body
            if node.body:
                insert_line = node.body[0].lineno - 1  # 0-indexed
            else:
                insert_line = node.end_lineno - 1

            # Determine indentation
            def_line = lines[node.lineno - 1]
            base_indent = len(def_line) - len(def_line.lstrip())
            doc_indent = " " * (base_indent + 4)

            # Format the docstring
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

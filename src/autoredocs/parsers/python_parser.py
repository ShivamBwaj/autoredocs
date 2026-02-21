"""Python AST-based parser — refactored to extend BaseParser."""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from autoredocs.models import ArgInfo, ClassDoc, FunctionDoc, ModuleDoc
from autoredocs.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class PythonParser(BaseParser):
    """Parses Python source files and extracts documentation structures."""

    extensions = [".py"]

    _DEPRECATED_RE = re.compile(r"\bdeprecated\b", re.IGNORECASE)

    def parse_file(self, filepath: str | Path) -> ModuleDoc | None:
        """Parse a single Python file and return a ModuleDoc, or None on failure."""
        filepath = Path(filepath)
        if not filepath.exists() or filepath.suffix != ".py":
            logger.warning("Skipping non-Python or missing file: %s", filepath)
            return None

        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return None

        try:
            tree = ast.parse(source, filename=str(filepath))
        except SyntaxError as exc:
            logger.warning("Syntax error in %s: %s", filepath, exc)
            return None

        module_name = filepath.stem
        module_doc = ModuleDoc(
            filepath=str(filepath),
            module_name=module_name,
            docstring=ast.get_docstring(tree) or "",
        )

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = self._extract_function(node)
                if func and self._should_include(func.name):
                    module_doc.functions.append(func)
            elif isinstance(node, ast.ClassDef):
                cls = self._extract_class(node)
                if cls and self._should_include(cls.name):
                    module_doc.classes.append(cls)

        return module_doc

    # -- Extraction helpers --------------------------------------------------

    def _extract_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> FunctionDoc:
        args = self._extract_args(node.args)
        return_type = self._unparse_annotation(node.returns)
        decorators = [self._unparse_node(d) for d in node.decorator_list]

        return FunctionDoc(
            name=node.name,
            args=args,
            return_type=return_type,
            docstring=ast.get_docstring(node) or "",
            decorators=decorators,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_deprecated=self._is_deprecated(node),
            line_number=node.lineno,
        )

    def _extract_class(self, node: ast.ClassDef) -> ClassDoc:
        bases = [self._unparse_node(b) for b in node.bases]
        decorators = [self._unparse_node(d) for d in node.decorator_list]

        methods: list[FunctionDoc] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = self._extract_function(item)
                func.is_method = True
                if self._should_include(func.name):
                    methods.append(func)

        return ClassDoc(
            name=node.name,
            bases=bases,
            docstring=ast.get_docstring(node) or "",
            methods=methods,
            decorators=decorators,
            is_deprecated=self._is_deprecated(node),
            line_number=node.lineno,
        )

    def _extract_args(self, args: ast.arguments) -> list[ArgInfo]:
        result: list[ArgInfo] = []

        all_args = args.posonlyargs + args.args
        num_defaults = len(args.defaults)
        num_args = len(all_args)

        for i, arg in enumerate(all_args):
            default_idx = i - (num_args - num_defaults)
            default = ""
            if default_idx >= 0:
                default = self._unparse_node(args.defaults[default_idx])

            result.append(
                ArgInfo(
                    name=arg.arg,
                    type_hint=self._unparse_annotation(arg.annotation),
                    default=default,
                )
            )

        if args.vararg:
            result.append(
                ArgInfo(
                    name=f"*{args.vararg.arg}",
                    type_hint=self._unparse_annotation(args.vararg.annotation),
                )
            )

        for i, arg in enumerate(args.kwonlyargs):
            default = ""
            if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
                default = self._unparse_node(args.kw_defaults[i])
            result.append(
                ArgInfo(
                    name=arg.arg,
                    type_hint=self._unparse_annotation(arg.annotation),
                    default=default,
                )
            )

        if args.kwarg:
            result.append(
                ArgInfo(
                    name=f"**{args.kwarg.arg}",
                    type_hint=self._unparse_annotation(args.kwarg.annotation),
                )
            )

        return result

    def _unparse_annotation(self, node: ast.expr | None) -> str:
        if node is None:
            return ""
        return self._unparse_node(node)

    def _unparse_node(self, node: ast.AST | None) -> str:
        if node is None:
            return ""
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    def _is_deprecated(self, node: ast.AST) -> bool:
        decorator_list = getattr(node, "decorator_list", [])
        for dec in decorator_list:
            dec_str = self._unparse_node(dec).lower()
            if "deprecated" in dec_str:
                return True

        docstring = ast.get_docstring(node) or ""
        if self._DEPRECATED_RE.search(docstring):
            return True

        return False

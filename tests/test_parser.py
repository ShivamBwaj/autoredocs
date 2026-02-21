"""Tests for the Python AST parser."""

from pathlib import Path

import pytest

from autoredocs.parser import PythonParser

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def parser():
    return PythonParser()


@pytest.fixture
def private_parser():
    return PythonParser(exclude_private=True)


@pytest.fixture
def sample_module(parser):
    return parser.parse_file(FIXTURES / "sample_module.py")


class TestParseFile:
    """Tests for parsing individual files."""

    def test_returns_module_doc(self, sample_module):
        assert sample_module is not None
        assert sample_module.module_name == "sample_module"

    def test_extracts_module_docstring(self, sample_module):
        assert "Sample Python module" in sample_module.docstring

    def test_extracts_functions(self, sample_module):
        func_names = [f.name for f in sample_module.functions]
        assert "greet" in func_names
        assert "add" in func_names
        assert "no_docs" in func_names
        assert "fetch_data" in func_names

    def test_extracts_function_args(self, sample_module):
        greet = next(f for f in sample_module.functions if f.name == "greet")
        arg_names = [a.name for a in greet.args]
        assert "name" in arg_names
        assert "excited" in arg_names

    def test_extracts_type_hints(self, sample_module):
        greet = next(f for f in sample_module.functions if f.name == "greet")
        name_arg = next(a for a in greet.args if a.name == "name")
        assert name_arg.type_hint == "str"
        assert greet.return_type == "str"

    def test_extracts_default_values(self, sample_module):
        greet = next(f for f in sample_module.functions if f.name == "greet")
        excited_arg = next(a for a in greet.args if a.name == "excited")
        assert excited_arg.default == "False"

    def test_extracts_docstrings(self, sample_module):
        greet = next(f for f in sample_module.functions if f.name == "greet")
        assert "greeting message" in greet.docstring

    def test_detects_no_docstring(self, sample_module):
        no_docs = next(f for f in sample_module.functions if f.name == "no_docs")
        assert no_docs.docstring == ""

    def test_detects_async_functions(self, sample_module):
        fetch = next(f for f in sample_module.functions if f.name == "fetch_data")
        assert fetch.is_async is True

    def test_non_async_functions(self, sample_module):
        add = next(f for f in sample_module.functions if f.name == "add")
        assert add.is_async is False

    def test_extracts_classes(self, sample_module):
        class_names = [c.name for c in sample_module.classes]
        assert "User" in class_names
        assert "Calculator" in class_names

    def test_extracts_class_methods(self, sample_module):
        user_cls = next(c for c in sample_module.classes if c.name == "User")
        method_names = [m.name for m in user_cls.methods]
        assert "full_info" in method_names
        assert "is_adult" in method_names

    def test_methods_marked_as_method(self, sample_module):
        user_cls = next(c for c in sample_module.classes if c.name == "User")
        for method in user_cls.methods:
            assert method.is_method is True

    def test_extracts_class_docstring(self, sample_module):
        user_cls = next(c for c in sample_module.classes if c.name == "User")
        assert "Represents a user" in user_cls.docstring

    def test_extracts_class_bases(self, sample_module):
        # _PrivateHelper has no explicit base (object is implicit)
        calc = next(c for c in sample_module.classes if c.name == "Calculator")
        assert calc.bases == []

    def test_extracts_decorated_methods(self, sample_module):
        calc = next(c for c in sample_module.classes if c.name == "Calculator")
        static = next(m for m in calc.methods if m.name == "is_positive")
        assert "staticmethod" in static.decorators

    def test_function_signature_property(self, sample_module):
        greet = next(f for f in sample_module.functions if f.name == "greet")
        sig = greet.signature
        assert "def greet(" in sig
        assert "-> str" in sig

    def test_class_signature_property(self, sample_module):
        user_cls = next(c for c in sample_module.classes if c.name == "User")
        assert user_cls.signature == "class User"

    def test_line_numbers(self, sample_module):
        greet = next(f for f in sample_module.functions if f.name == "greet")
        assert greet.line_number > 0


class TestErrorHandling:
    """Tests for parser error handling."""

    def test_syntax_error_returns_none(self, parser):
        result = parser.parse_file(FIXTURES / "bad_syntax.py")
        assert result is None

    def test_missing_file_returns_none(self, parser):
        result = parser.parse_file(FIXTURES / "nonexistent.py")
        assert result is None

    def test_non_python_file_returns_none(self, parser):
        result = parser.parse_file(FIXTURES / "readme.txt")
        assert result is None


class TestPrivateExclusion:
    """Tests for excluding private names."""

    def test_includes_private_by_default(self, sample_module):
        class_names = [c.name for c in sample_module.classes]
        assert "_PrivateHelper" in class_names

    def test_excludes_private_when_configured(self, private_parser):
        module = private_parser.parse_file(FIXTURES / "sample_module.py")
        class_names = [c.name for c in module.classes]
        assert "_PrivateHelper" not in class_names


class TestParseDirectory:
    """Tests for directory-level parsing."""

    def test_parse_directory_returns_project(self, parser):
        project = parser.parse_directory(FIXTURES)
        assert project.module_count >= 1

    def test_module_name_is_filename(self, parser):
        project = parser.parse_directory(FIXTURES)
        names = [m.module_name for m in project.modules]
        assert "sample_module" in names

    def test_empty_modules_excluded(self, parser):
        project = parser.parse_directory(FIXTURES)
        for module in project.modules:
            assert not module.is_empty

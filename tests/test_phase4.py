"""Tests for Phase 4: Multi-language parsers (TypeScript, Java)."""

from pathlib import Path

import pytest

from autoredocs.parsers.base import BaseParser
from autoredocs.parsers.python_parser import PythonParser
from autoredocs.parsers.typescript import TypeScriptParser
from autoredocs.parsers.java import JavaParser
from autoredocs.parsers import get_parser

FIXTURES = Path(__file__).parent / "fixtures"


# -- Parser registry tests -----------------------------------------------------


class TestParserRegistry:
    def test_python_extension(self):
        p = get_parser(".py")
        assert isinstance(p, PythonParser)

    def test_ts_extension(self):
        p = get_parser(".ts")
        assert isinstance(p, TypeScriptParser)

    def test_java_extension(self):
        p = get_parser(".java")
        assert isinstance(p, JavaParser)

    def test_unknown_extension(self):
        assert get_parser(".xyz") is None


# -- TypeScript parser tests ---------------------------------------------------


class TestTypeScriptParser:
    @pytest.fixture
    def module(self):
        return TypeScriptParser().parse_file(FIXTURES / "sample_module.ts")

    def test_module_parsed(self, module):
        assert module is not None
        assert module.module_name == "sample_module"

    def test_functions_extracted(self, module):
        names = [f.name for f in module.functions]
        assert "greet" in names
        assert "add" in names

    def test_function_args(self, module):
        greet = next(f for f in module.functions if f.name == "greet")
        arg_names = [a.name for a in greet.args]
        assert "name" in arg_names

    def test_class_extracted(self, module):
        names = [c.name for c in module.classes]
        assert "User" in names

    def test_class_methods(self, module):
        user = next(c for c in module.classes if c.name == "User")
        method_names = [m.name for m in user.methods]
        assert "fullInfo" in method_names

    def test_interface_extracted(self, module):
        names = [c.name for c in module.classes]
        assert "UserDTO" in names

    def test_jsdoc_extracted(self, module):
        greet = next(f for f in module.functions if f.name == "greet")
        assert "Greet" in greet.docstring


# -- Java parser tests ---------------------------------------------------------


class TestJavaParser:
    @pytest.fixture
    def module(self):
        return JavaParser().parse_file(FIXTURES / "Calculator.java")

    def test_module_parsed(self, module):
        assert module is not None

    def test_package_in_module_name(self, module):
        assert "com.example" in module.module_name

    def test_class_extracted(self, module):
        names = [c.name for c in module.classes]
        assert "Calculator" in names

    def test_class_methods(self, module):
        calc = next(c for c in module.classes if c.name == "Calculator")
        method_names = [m.name for m in calc.methods]
        assert "add" in method_names
        assert "divide" in method_names

    def test_interface_extracted(self, module):
        names = [c.name for c in module.classes]
        assert "User" in names
        user = next(c for c in module.classes if c.name == "User")
        assert "interface" in user.decorators

    def test_enum_extracted(self, module):
        names = [c.name for c in module.classes]
        assert "BuildStatus" in names

    def test_javadoc_extracted(self, module):
        calc = next(c for c in module.classes if c.name == "Calculator")
        assert "calculator" in calc.docstring.lower()

    def test_method_params(self, module):
        calc = next(c for c in module.classes if c.name == "Calculator")
        add = next(m for m in calc.methods if m.name == "add")
        assert len(add.args) == 2
        assert add.args[0].type_hint == "double"


# -- Backward compatibility ---------------------------------------------------


class TestBackwardCompat:
    def test_old_import_works(self):
        from autoredocs.parser import PythonParser as P

        assert P is PythonParser

    def test_base_parser_abstract(self):
        with pytest.raises(TypeError):
            BaseParser()

"""Tests for the Markdown and HTML generators."""

from pathlib import Path

import pytest

from autoredocs.generator import HTMLGenerator, MarkdownGenerator
from autoredocs.parser import PythonParser

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def project():
    parser = PythonParser()
    return parser.parse_directory(FIXTURES)


@pytest.fixture
def md_output(tmp_path, project):
    gen = MarkdownGenerator()
    gen.generate(project, tmp_path)
    return tmp_path


@pytest.fixture
def html_output(tmp_path, project):
    gen = HTMLGenerator()
    gen.generate(project, tmp_path)
    return tmp_path


class TestMarkdownGenerator:
    """Tests for Markdown output."""

    def test_creates_index(self, md_output):
        assert (md_output / "index.md").exists()

    def test_creates_module_files(self, md_output):
        assert (md_output / "sample_module.md").exists()

    def test_index_contains_module_link(self, md_output):
        content = (md_output / "index.md").read_text(encoding="utf-8")
        assert "sample_module" in content

    def test_module_contains_function_signature(self, md_output):
        content = (md_output / "sample_module.md").read_text(encoding="utf-8")
        assert "greet" in content

    def test_module_contains_class(self, md_output):
        content = (md_output / "sample_module.md").read_text(encoding="utf-8")
        assert "Calculator" in content

    def test_module_contains_docstring(self, md_output):
        content = (md_output / "sample_module.md").read_text(encoding="utf-8")
        assert "greeting message" in content


class TestHTMLGenerator:
    """Tests for HTML output."""

    def test_creates_index_html(self, html_output):
        assert (html_output / "index.html").exists()

    def test_creates_module_html(self, html_output):
        assert (html_output / "sample_module.html").exists()

    def test_css_embedded_inline(self, html_output):
        content = (html_output / "index.html").read_text(encoding="utf-8")
        assert "<style>" in content
        assert "--bg-primary" in content

    def test_html_has_sidebar(self, html_output):
        content = (html_output / "index.html").read_text(encoding="utf-8")
        assert "sidebar" in content

    def test_html_has_module_content(self, html_output):
        content = (html_output / "sample_module.html").read_text(encoding="utf-8")
        assert "greet" in content
        assert "Calculator" in content

    def test_html_has_stats(self, html_output):
        content = (html_output / "index.html").read_text(encoding="utf-8")
        assert "modules" in content
        assert "functions" in content

    def test_no_external_css_file(self, html_output):
        """CSS is embedded inline, no separate file needed."""
        assert not (html_output / "style.css").exists()

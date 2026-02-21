"""Tests for the CLI commands."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from autodocs.cli import app

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


class TestGenerateCommand:
    """Tests for 'autodocs generate'."""

    def test_generate_markdown(self, tmp_path):
        result = runner.invoke(app, [
            "generate",
            "--source", str(FIXTURES),
            "--output", str(tmp_path / "docs"),
            "--format", "markdown",
        ])
        assert result.exit_code == 0
        assert (tmp_path / "docs" / "index.md").exists()
        assert "Build Report" in result.output or "generated" in result.output.lower()

    def test_generate_html(self, tmp_path):
        result = runner.invoke(app, [
            "generate",
            "--source", str(FIXTURES),
            "--output", str(tmp_path / "docs"),
            "--format", "html",
        ])
        assert result.exit_code == 0
        assert (tmp_path / "docs" / "index.html").exists()

    def test_generate_missing_source(self, tmp_path):
        result = runner.invoke(app, [
            "generate",
            "--source", str(tmp_path / "nonexistent"),
        ])
        assert result.exit_code == 1


class TestInitCommand:
    """Tests for 'autodocs init'."""

    def test_creates_config_file(self, tmp_path):
        result = runner.invoke(app, [
            "init",
            "--path", str(tmp_path),
        ])
        assert result.exit_code == 0
        config_path = tmp_path / "autodocs.yaml"
        assert config_path.exists()
        content = config_path.read_text()
        assert "title" in content
        assert "source" in content


class TestVersionCommand:
    """Tests for 'autodocs version'."""

    def test_shows_version(self):
        from autodocs import __version__
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output

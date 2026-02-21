"""Tests for Phase 2 features: build state, deprecation, and incremental builds."""

from pathlib import Path

import pytest

from autodocs.parser import PythonParser
from autodocs.state import STATE_FILENAME, BuildState

FIXTURES = Path(__file__).parent / "fixtures"


# -- BuildState tests ----------------------------------------------------------


class TestBuildState:
    """Tests for hash-based build state tracking."""

    def test_new_file_is_changed(self, tmp_path):
        """A file not previously tracked should register as changed."""
        state = BuildState(tmp_path / STATE_FILENAME)
        sample = FIXTURES / "sample_module.py"
        assert state.has_changed(sample)

    def test_known_file_unchanged(self, tmp_path):
        """After recording a file, it should be unchanged."""
        state = BuildState(tmp_path / STATE_FILENAME)
        sample = FIXTURES / "sample_module.py"
        state.update(sample)
        assert not state.has_changed(sample)

    def test_save_and_reload(self, tmp_path):
        """State should survive save + reload."""
        state_path = tmp_path / STATE_FILENAME
        state = BuildState(state_path)
        sample = FIXTURES / "sample_module.py"
        state.update(sample)
        state.save()

        # Reload
        state2 = BuildState(state_path)
        assert not state2.has_changed(sample)

    def test_compute_diff_detects_new(self, tmp_path):
        """A fresh state should see all files as added/modified."""
        state = BuildState(tmp_path / STATE_FILENAME)
        files = [FIXTURES / "sample_module.py"]
        added, unchanged, deleted = state.compute_diff(files)
        assert len(added) == 1
        assert len(unchanged) == 0
        assert len(deleted) == 0

    def test_compute_diff_detects_deleted(self, tmp_path):
        """Files in state but missing on disk should be flagged as deleted."""
        state = BuildState(tmp_path / STATE_FILENAME)
        fake = tmp_path / "gone.py"
        fake.write_text("x = 1", encoding="utf-8")
        state.update(fake)
        fake.unlink()

        added, unchanged, deleted = state.compute_diff([])
        assert len(deleted) == 1

    def test_remove_clears_hash(self, tmp_path):
        state = BuildState(tmp_path / STATE_FILENAME)
        sample = FIXTURES / "sample_module.py"
        state.update(sample)
        state.remove(sample)
        assert state.has_changed(sample)


# -- Deprecation detection tests -----------------------------------------------


class TestDeprecationDetection:
    """Tests that deprecated functions/classes are correctly flagged."""

    @pytest.fixture
    def module(self):
        parser = PythonParser()
        return parser.parse_file(FIXTURES / "sample_module.py")

    def test_deprecated_function_detected(self, module):
        """old_function() has 'Deprecated' in its docstring."""
        func = next((f for f in module.functions if f.name == "old_function"), None)
        assert func is not None
        assert func.is_deprecated

    def test_deprecated_class_detected(self, module):
        """LegacyProcessor has 'deprecated' in its docstring."""
        cls = next((c for c in module.classes if c.name == "LegacyProcessor"), None)
        assert cls is not None
        assert cls.is_deprecated

    def test_normal_function_not_deprecated(self, module):
        """greet() should not be flagged as deprecated."""
        func = next((f for f in module.functions if f.name == "greet"), None)
        assert func is not None
        assert not func.is_deprecated

    def test_normal_class_not_deprecated(self, module):
        """Calculator should not be flagged as deprecated."""
        cls = next((c for c in module.classes if c.name == "Calculator"), None)
        assert cls is not None
        assert not cls.is_deprecated


# -- Incremental CLI test -------------------------------------------------------


class TestIncrementalCLI:
    """Tests the --incremental flag in the generate CLI command."""

    def test_incremental_creates_state_file(self, tmp_path):
        from typer.testing import CliRunner
        from autodocs.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "generate",
                "--source",
                str(FIXTURES),
                "--output",
                str(tmp_path / "docs"),
                "--format",
                "markdown",
                "--incremental",
            ],
        )
        assert result.exit_code == 0
        assert (tmp_path / "docs" / STATE_FILENAME).exists()

    def test_incremental_second_run_skips(self, tmp_path):
        from typer.testing import CliRunner
        from autodocs.cli import app

        runner = CliRunner()
        # First build
        runner.invoke(
            app,
            [
                "generate",
                "-s",
                str(FIXTURES),
                "-o",
                str(tmp_path / "docs"),
                "-f",
                "markdown",
                "--incremental",
            ],
        )
        # Second build — no changes
        result = runner.invoke(
            app,
            [
                "generate",
                "-s",
                str(FIXTURES),
                "-o",
                str(tmp_path / "docs"),
                "-f",
                "markdown",
                "--incremental",
            ],
        )
        assert result.exit_code == 0
        assert "No changes detected" in result.output

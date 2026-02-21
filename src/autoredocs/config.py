"""Configuration management for autoredocs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional for non-AI usage

DEFAULT_CONFIG_FILENAME = "autoredocs.yaml"

DEFAULT_EXCLUDES = [
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    "*.egg-info",
]


@dataclass
class AIConfig:
    """Configuration for AI docstring generation."""

    enabled: bool = True
    api_key: str = ""
    model: str = "llama-3.1-8b-instant"
    style: str = "google"  # google, numpy, sphinx
    max_tokens: int = 300

    def resolve_api_key(self) -> str:
        """Resolve API key: config value > env var > empty."""
        return self.api_key or os.getenv("GROQ_API_KEY", "")


@dataclass
class AutoredocsConfig:
    """Configuration for an autoredocs run."""

    title: str = "Project Documentation"
    source: str = "."
    output: str = "./docs"
    format: str = "markdown"  # "markdown" or "html"
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    exclude_private: bool = False
    port: int = 8000
    ai: AIConfig = field(default_factory=AIConfig)

    @classmethod
    def load(cls, path: str | Path | None = None) -> AutoredocsConfig:
        """Load config from a YAML file. Falls back to defaults if file missing."""
        if path is None:
            path = Path.cwd() / DEFAULT_CONFIG_FILENAME

        path = Path(path)
        if not path.exists():
            return cls()

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return cls()

        # Parse AI config section
        ai_data = data.get("ai", {})
        ai_config = AIConfig(
            enabled=ai_data.get("enabled", True),
            api_key=ai_data.get("api_key", ""),
            model=ai_data.get("model", "llama-3.3-70b-versatile"),
            style=ai_data.get("style", "google"),
            max_tokens=ai_data.get("max_tokens", 300),
        )

        return cls(
            title=data.get("title", cls.title),
            source=data.get("source", cls.source),
            output=data.get("output", cls.output),
            format=data.get("format", cls.format),
            exclude=data.get("exclude", list(DEFAULT_EXCLUDES)),
            exclude_private=data.get("exclude_private", cls.exclude_private),
            port=data.get("port", cls.port),
            ai=ai_config,
        )

    def save(self, path: str | Path | None = None) -> Path:
        """Save config to a YAML file."""
        if path is None:
            path = Path.cwd() / DEFAULT_CONFIG_FILENAME

        path = Path(path)
        data = {
            "title": self.title,
            "source": self.source,
            "output": self.output,
            "format": self.format,
            "exclude": self.exclude,
            "exclude_private": self.exclude_private,
            "port": self.port,
            "ai": {
                "enabled": self.ai.enabled,
                "model": self.ai.model,
                "style": self.ai.style,
                "max_tokens": self.ai.max_tokens,
                # NOTE: api_key intentionally omitted — use .env instead
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        return path

    def resolve_source(self, base: Path | None = None) -> Path:
        """Resolve source path relative to a base directory."""
        base = base or Path.cwd()
        return (base / self.source).resolve()

    def resolve_output(self, base: Path | None = None) -> Path:
        """Resolve output path relative to a base directory."""
        base = base or Path.cwd()
        return (base / self.output).resolve()

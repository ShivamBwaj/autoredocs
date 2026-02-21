# Contributing to autodocs

Thank you for considering contributing to autodocs.

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/autodocs.git
cd autodocs
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

All 78 tests must pass before submitting a pull request.

## Code Style

This project uses [Ruff](https://github.com/astral-sh/ruff) for linting:

```bash
pip install ruff
ruff check src/ tests/
```

Target: Python 3.10+, line length 100.

## Pull Request Guidelines

1. Fork the repository and create your branch from `main`.
2. Add tests for any new functionality.
3. Ensure all tests pass.
4. Run the linter with zero warnings.
5. Write clear commit messages.

## Adding a New Language Parser

1. Create a new parser class in `src/autodocs/parsers/` that extends `BaseParser`.
2. Implement the `parse_file` method.
3. Set the `extensions` class attribute to the file extensions it handles.
4. The parser registry in `src/autodocs/parsers/__init__.py` will auto-discover it.
5. Add tests in `tests/`.

## Adding a New Deploy Target

1. Create a new class in `src/autodocs/deploy.py` that extends `BaseDeployer`.
2. Implement the `deploy(docs_dir: Path) -> str` method.
3. Add it to the `DEPLOYERS` registry dict.
4. Document the required environment variables in `README.md` and `.env.example`.

## Reporting Issues

Open an issue on GitHub with:

- Python version (`python --version`)
- Operating system
- Steps to reproduce
- Expected vs actual behavior

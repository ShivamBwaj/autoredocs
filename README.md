<p align="center">
  <strong>autodocs</strong><br>
  <em>Self-maintaining code documentation that stays in sync with your codebase.</em>
</p>

<p align="center">
  <a href="https://github.com/YOUR_USERNAME/autodocs/actions/workflows/ci.yml"><img src="https://github.com/YOUR_USERNAME/autodocs/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"></a>
  <a href="https://pypi.org/project/autodocs/"><img src="https://img.shields.io/badge/version-0.3.0-blue" alt="Version"></a>
</p>

---

autodocs parses your source code, detects what changed, generates structured documentation, and optionally fills missing docstrings using AI. It works locally on your machine or remotely via GitHub Actions with zero infrastructure overhead.

```
pip install autodocs
autodocs generate --source ./src --output ./docs --format html
```

---

## Table of Contents

- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands](#commands)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [AI Docstring Generation](#ai-docstring-generation)
- [Deployment](#deployment)
- [Serverless Handlers](#serverless-handlers)
- [CI/CD with GitHub Actions](#cicd-with-github-actions)
- [Supported Languages](#supported-languages)
- [Build Reports](#build-reports)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## How It Works

autodocs has three operating modes. Use whichever fits your workflow.

### Local one-shot build

Run the command, get docs, done. Nothing stays running.

```bash
autodocs generate --source ./src --output ./docs --format html
```

### Local file watcher

Watches your filesystem for changes. When you save a file, it rebuilds only the changed files. Does not call any external APIs. Kill with Ctrl+C.

```bash
autodocs watch --source ./src --output ./docs
```

Triggers on: file save, create, delete.
Does not trigger on: file reads, non-source files, files outside the watched directory.
Uses OS-native file events (inotify / ReadDirectoryChangesW). No polling.

### Remote via GitHub Actions

Push to GitHub. A workflow runs on GitHub's servers, builds docs with AI, and deploys. Your machine does not need to be on.

```
git push --> GitHub Actions --> autodocs generate --ai --incremental --> deploy to Netlify
```

The runner starts, builds, deploys, and shuts down. Nothing stays running between pushes.

---

## Installation

```bash
# Core
pip install autodocs

# With AI (Groq / Llama 3.3)
pip install "autodocs[ai]"

# With deploy (Netlify, Vercel, S3)
pip install "autodocs[deploy]"

# With live server (FastAPI)
pip install "autodocs[server]"

# Everything
pip install "autodocs[all]"

# Development
git clone https://github.com/YOUR_USERNAME/autodocs.git
cd autodocs
pip install -e ".[dev]"
```

---

## Quick Start

```bash
# 1. Initialize config
autodocs init

# 2. Generate HTML documentation
autodocs generate --source ./src --output ./docs --format html

# 3. Preview in browser
autodocs preview --source ./src

# 4. Watch for changes
autodocs watch --source ./src --output ./docs

# 5. Fill missing docstrings with AI
autodocs ai-fill --source ./src --dry-run

# 6. Generate + AI fill + deploy in one command
autodocs generate --source ./src --ai --deploy netlify --incremental
```

---

## Commands

| Command | Description |
|---------|-------------|
| `generate` | Parse source code and generate documentation |
| `watch` | Watch files and auto-rebuild on change (local, no AI) |
| `preview` | Build HTML docs and open in browser |
| `ai-fill` | Fill missing docstrings using Groq API |
| `deploy` | Deploy built docs to Netlify, Vercel, or S3 |
| `serve` | Start FastAPI server with webhook endpoint |
| `init` | Create default `autodocs.yaml` config file |
| `version` | Print version |

### `generate` flags

| Flag | Description |
|------|-------------|
| `--source`, `-s` | Source directory to parse |
| `--output`, `-o` | Output directory |
| `--format`, `-f` | `html` or `markdown` |
| `--incremental`, `-i` | Only rebuild changed files (SHA-256 hash comparison) |
| `--ai` | Fill missing docstrings before generating (only changed files in incremental mode) |
| `--deploy`, `-d` | Deploy after build: `netlify`, `vercel`, or `s3` |
| `--config`, `-c` | Path to `autodocs.yaml` |

---

## Configuration

Run `autodocs init` to create `autodocs.yaml`:

```yaml
title: My Project Docs
source: ./src
output: ./docs
format: html
exclude:
  - __pycache__
  - .venv
  - node_modules
exclude_private: false
port: 8000
ai:
  enabled: true
  model: llama-3.3-70b-versatile
  style: google       # google | numpy | sphinx
  max_tokens: 300
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values you need:

```bash
cp .env.example .env
```

| Variable | Purpose | Where to get it |
|----------|---------|-----------------|
| `GROQ_API_KEY` | AI docstring generation | [console.groq.com/keys](https://console.groq.com/keys) |
| `NETLIFY_TOKEN` | Netlify deploy | [Netlify personal access tokens](https://app.netlify.com/user/applications#personal-access-tokens) |
| `NETLIFY_SITE_ID` | Netlify deploy (optional) | Netlify dashboard |
| `VERCEL_TOKEN` | Vercel deploy | [vercel.com/account/tokens](https://vercel.com/account/tokens) |
| `VERCEL_PROJECT_ID` | Vercel deploy (optional) | Vercel dashboard |
| `AWS_ACCESS_KEY_ID` | S3 deploy | [AWS IAM console](https://console.aws.amazon.com/iam) |
| `AWS_SECRET_ACCESS_KEY` | S3 deploy | AWS IAM console |
| `AWS_REGION` | S3 deploy (default: `us-east-1`) | -- |
| `S3_BUCKET` | S3 deploy | AWS S3 console |
| `GITHUB_WEBHOOK_SECRET` | Webhook verification | Your GitHub repo webhook settings |

You only need the variables for features you actually use. For local builds without AI, you need zero keys.

---

## AI Docstring Generation

autodocs uses the [Groq API](https://groq.com) with Llama 3.3 70B to generate missing docstrings. The AI is opt-in and never runs unless you explicitly request it.

| Scenario | AI called? |
|----------|-----------|
| `autodocs generate` | No |
| `autodocs generate --ai` | Yes, all files |
| `autodocs generate --ai --incremental` | Yes, changed files only |
| `autodocs generate --ai --incremental` (nothing changed) | No |
| `autodocs watch` | No |
| `autodocs ai-fill --dry-run` | Yes (preview, no writes) |
| `autodocs ai-fill` | Yes (writes to files) |
| GitHub Actions (`deploy.yml`) | Yes, changed files only |

Supports three docstring styles: **Google**, **NumPy**, and **Sphinx**.

```bash
# Preview what AI would generate (no file changes)
autodocs ai-fill --source ./src --style numpy --dry-run

# Write AI-generated docstrings into source files
autodocs ai-fill --source ./src --style google
```

---

## Deployment

### Netlify

```bash
autodocs deploy --output ./docs --target netlify
```

Requires: `NETLIFY_TOKEN` in `.env`.

### Vercel

```bash
autodocs deploy --output ./docs --target vercel
```

Requires: `VERCEL_TOKEN` in `.env`.

### AWS S3

```bash
autodocs deploy --output ./docs --target s3
```

Requires: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET` in `.env`.

### One-command build + deploy

```bash
autodocs generate --source ./src --ai --deploy netlify --incremental
```

---

## Serverless Handlers

Pre-built webhook handlers for Vercel Functions and AWS Lambda. They receive GitHub push webhooks, verify the signature, rebuild docs, and optionally deploy.

**Vercel:** Copy `src/autodocs/serverless/vercel_handler.py` to `api/webhook.py` in your Vercel project.

**Lambda:** Set handler to `autodocs.serverless.lambda_handler.lambda_handler`.

Both require these environment variables on the hosting platform:

| Variable | Description |
|----------|-------------|
| `AUTODOCS_SOURCE` | Source directory path |
| `AUTODOCS_OUTPUT` | Output directory path |
| `GITHUB_WEBHOOK_SECRET` | Webhook HMAC secret |
| `AUTODOCS_DEPLOY_TARGET` | Optional: `netlify`, `vercel`, or `s3` |

---

## CI/CD with GitHub Actions

The included `.github/workflows/deploy.yml` runs on every push to `main`:

1. Installs autodocs.
2. Runs `autodocs generate --ai --incremental`.
3. Deploys to Netlify.
4. Uploads `build_report.json` as an artifact.

### Setup

1. Push your repo to GitHub.
2. Go to your repo **Settings > Secrets and variables > Actions**.
3. Add these secrets:

| Secret | Value |
|--------|-------|
| `GROQ_API_KEY` | Your Groq API key |
| `NETLIFY_TOKEN` | Your Netlify token |
| `NETLIFY_SITE_ID` | Your Netlify site ID |

1. Push to `main`. The workflow runs automatically.

---

## Supported Languages

| Language | Parser | What it extracts |
|----------|--------|------------------|
| **Python** | AST | Functions, classes, arguments, type hints, decorators, docstrings, deprecation markers |
| **TypeScript / JavaScript** | Regex | Functions, arrow functions, classes, interfaces, type aliases, JSDoc comments |
| **Java** | Regex | Classes, interfaces, enums, methods, Javadoc comments |

---

## Build Reports

Every build writes `build_report.json` to the output directory:

```json
{
  "summary": {
    "files_scanned": 12,
    "files_changed": 3,
    "files_generated": 8,
    "deprecated": 2,
    "ai_filled": 4
  },
  "changes": [
    { "name": "UserService", "kind": "class", "action": "modified" },
    { "name": "old_handler", "kind": "function", "action": "deprecated" }
  ]
}
```

---

## Project Structure

```
autodocs/
  src/autodocs/
    cli.py               # CLI (9 commands)
    config.py            # YAML configuration
    ai.py                # Groq API integration
    reporter.py          # Build reports (JSON + console)
    deploy.py            # Netlify / Vercel / S3 deploy
    server.py            # FastAPI server + webhooks
    state.py             # Incremental build state
    generator.py         # Markdown + HTML output
    models.py            # Data models
    watcher.py           # Filesystem watcher
    parser.py            # Backward-compat re-export
    parsers/
      base.py            # Abstract parser
      python_parser.py   # Python AST parser
      typescript.py      # TS/JS regex parser
      java.py            # Java regex parser
    serverless/
      vercel_handler.py  # Vercel function
      lambda_handler.py  # Lambda function
    templates/           # Jinja2 templates + CSS
  tests/                 # 78 tests
  .github/workflows/
    ci.yml               # Lint + test
    deploy.yml           # Build + deploy
  .env.example           # Environment template
  autodocs.yaml          # Project config
  pyproject.toml         # Package metadata
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and pull request guidelines.

---

## License

MIT License. See [LICENSE](LICENSE).

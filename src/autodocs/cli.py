"""Autodocs CLI — command-line interface for generating code documentation."""

from __future__ import annotations

import http.server
import logging
import threading
import webbrowser
from functools import partial
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from autodocs import __version__
from autodocs.config import AutodocsConfig
from autodocs.generator import HTMLGenerator, MarkdownGenerator
from autodocs.parsers.base import MultiParser
from autodocs.state import STATE_FILENAME, BuildState
from autodocs.watcher import watch_and_rebuild

app = typer.Typer(
    name="autodocs",
    help="Real-time, self-maintaining code documentation tool.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

# -- Helpers -------------------------------------------------------------------


def _build_docs(
    source: Path,
    output: Path,
    fmt: str,
    config: AutodocsConfig,
    *,
    incremental: bool = False,
    ai: bool = False,
) -> None:
    """Core build pipeline: parse -> [AI fill] -> generate (with optional incremental mode)."""
    from autodocs.reporter import BuildReport, ChangeItem

    parser = MultiParser(exclude_private=config.exclude_private)
    report = BuildReport(
        source=str(source),
        output=str(output),
        format=fmt,
        incremental=incremental,
    )

    exclude_dirs = set(config.exclude or ["__pycache__", ".venv", "venv", ".git"])

    if incremental:
        state = BuildState(output / STATE_FILENAME)
        src_files = parser.find_all_source_files(source, exclude_dirs)

        changed, unchanged, deleted = state.compute_diff(src_files)
        report.files_scanned = len(src_files) + len(deleted)
        report.files_changed = len(changed)
        report.files_unchanged = len(unchanged)
        report.files_deleted = len(deleted)

        if not changed and not deleted:
            console.print("[dim]No changes detected -- skipping rebuild.[/dim]")
            return

        # Parse all current files
        project = parser.parse_directory(source, exclude_dirs=list(exclude_dirs))
        project.title = config.title

        # Track changes
        for f in changed:
            report.changes.append(
                ChangeItem(
                    name=f.stem,
                    module=f.stem,
                    kind="file",
                    action="modified" if f in [p for p, _ in state._hashes.items()] else "added",
                )
            )
        for f in deleted:
            report.changes.append(
                ChangeItem(
                    name=str(f.name),
                    module=str(f.stem),
                    kind="file",
                    action="removed",
                )
            )

        # Update state
        for f in src_files:
            state.update(f)
        for f in deleted:
            state.remove(f)
        state.save()
    else:
        src_files = parser.find_all_source_files(source, exclude_dirs)
        report.files_scanned = len(src_files)
        report.files_changed = len(src_files)

        project = parser.parse_directory(source, exclude_dirs=list(exclude_dirs))
        project.title = config.title

    # AI auto-fill missing docstrings (only on changed files)
    if ai:
        try:
            from autodocs.ai import DocGenerator

            api_key = config.ai.resolve_api_key()
            if api_key:
                gen_ai = DocGenerator(
                    api_key=api_key,
                    model=config.ai.model,
                    style=config.ai.style,
                    max_tokens=config.ai.max_tokens,
                )
                # Only run AI on changed files (incremental) or all files (full build)
                ai_targets = changed if incremental else src_files
                for src_file in ai_targets:
                    if src_file.suffix == ".py":
                        # Python: precise AST-based docstring injection
                        suggestions = gen_ai.fill_missing_docstrings(src_file, dry_run=False)
                    else:
                        # All other languages: generic AI doc fill
                        suggestions = gen_ai.fill_missing_docs_generic(src_file, dry_run=False)
                    report.ai_filled_count += len(suggestions)
                    for s in suggestions:
                        report.changes.append(
                            ChangeItem(
                                name=s["name"],
                                module=src_file.stem,
                                kind=s["type"],
                                action="added",
                                line=s.get("line", 0),
                            )
                        )

                # Re-parse after AI fill to get updated docstrings
                if report.ai_filled_count > 0:
                    project = parser.parse_directory(source, exclude_dirs=list(exclude_dirs))
                    project.title = config.title
            else:
                report.errors.append("AI enabled but no GROQ_API_KEY found")
        except Exception as exc:
            report.errors.append(f"AI fill failed: {exc}")

    # Track deprecated items
    for m in project.modules:
        for f in m.functions:
            if f.is_deprecated:
                report.changes.append(
                    ChangeItem(
                        name=f.name,
                        module=m.module_name,
                        kind="function",
                        action="deprecated",
                        line=f.line_number,
                    )
                )
        for c in m.classes:
            if c.is_deprecated:
                report.changes.append(
                    ChangeItem(
                        name=c.name,
                        module=m.module_name,
                        kind="class",
                        action="deprecated",
                        line=c.line_number,
                    )
                )
            for meth in c.methods:
                if meth.is_deprecated:
                    report.changes.append(
                        ChangeItem(
                            name=f"{c.name}.{meth.name}",
                            module=m.module_name,
                            kind="method",
                            action="deprecated",
                            line=meth.line_number,
                        )
                    )

    report.deprecated_count = len(report.deprecated)
    report.modules = project.module_count
    report.functions = project.function_count
    report.classes = project.class_count

    # Generate docs
    if fmt == "html":
        gen = HTMLGenerator()
    else:
        gen = MarkdownGenerator()

    output.mkdir(parents=True, exist_ok=True)
    files = gen.generate(project, output)
    report.files_generated = len(files)

    # Save report JSON alongside docs
    report.save_json(output / "build_report.json")

    # Print rich summary
    report.print_summary(console)


def _resolve_paths(
    source: str | None,
    output: str | None,
    fmt: str | None,
    config_file: str | None,
) -> tuple[Path, Path, str, AutodocsConfig]:
    """Resolve CLI args with config file fallbacks."""
    config = AutodocsConfig.load(config_file)

    src = Path(source or config.source).resolve()
    out = Path(output or config.output).resolve()
    format_ = fmt or config.format

    return src, out, format_, config


# -- Commands ------------------------------------------------------------------


@app.command()
def generate(
    source: str = typer.Option(None, "--source", "-s", help="Source directory to parse"),
    output: str = typer.Option(None, "--output", "-o", help="Output directory for docs"),
    format: str = typer.Option(None, "--format", "-f", help="Output format: markdown or html"),
    config: str = typer.Option(None, "--config", "-c", help="Path to autodocs.yaml"),
    incremental: bool = typer.Option(
        False, "--incremental", "-i", help="Only rebuild changed files"
    ),
    ai: bool = typer.Option(False, "--ai", help="Auto-fill missing docstrings with AI"),
    deploy: str = typer.Option(
        None, "--deploy", "-d", help="Deploy after build (netlify/vercel/s3)"
    ),
) -> None:
    """Generate documentation from your codebase."""
    src, out, fmt, cfg = _resolve_paths(source, output, format, config)

    mode_parts = []
    if incremental:
        mode_parts.append("incremental")
    if ai:
        mode_parts.append("AI-assisted")
    if deploy:
        mode_parts.append(f"deploy:{deploy}")
    mode_str = " | ".join(mode_parts) if mode_parts else "full"

    console.print(
        Panel(
            f"[bold]Source:[/bold] {src}\n"
            f"[bold]Output:[/bold] {out}\n"
            f"[bold]Format:[/bold] {fmt}\n"
            f"[bold]Mode:[/bold] {mode_str}",
            title="[bold cyan]autodocs generate[/bold cyan]",
            border_style="cyan",
        )
    )

    if not src.exists():
        console.print(f"[red]Error:[/red] Source directory not found: {src}")
        raise typer.Exit(1)

    _build_docs(src, out, fmt, cfg, incremental=incremental, ai=ai)

    # Auto-deploy after successful build
    if deploy:
        try:
            from autodocs.deploy import get_deployer

            deployer = get_deployer(deploy)
            console.print(f"\n[cyan]Deploying to {deploy}...[/cyan]")
            url = deployer.deploy(out)
            console.print(f"[green]Deployed:[/green] {url}")
        except Exception as exc:
            console.print(f"[red]Deploy failed:[/red] {exc}")


@app.command()
def watch(
    source: str = typer.Option(None, "--source", "-s", help="Source directory to watch"),
    output: str = typer.Option(None, "--output", "-o", help="Output directory for docs"),
    format: str = typer.Option(None, "--format", "-f", help="Output format: markdown or html"),
    config: str = typer.Option(None, "--config", "-c", help="Path to autodocs.yaml"),
) -> None:
    """Watch for file changes and auto-regenerate docs."""
    src, out, fmt, cfg = _resolve_paths(source, output, format, config)

    if not src.exists():
        console.print(f"[red]Error:[/red] Source directory not found: {src}")
        raise typer.Exit(1)

    # Initial build
    console.print("[bold cyan]autodocs watch[/bold cyan]\n")
    _build_docs(src, out, fmt, cfg)

    # Watch loop (always use incremental for watch mode)
    rebuild_fn = partial(_build_docs, src, out, fmt, cfg, incremental=True)
    watch_and_rebuild(src, rebuild_fn)


@app.command()
def preview(
    source: str = typer.Option(None, "--source", "-s", help="Source directory to parse"),
    output: str = typer.Option(None, "--output", "-o", help="Output directory for docs"),
    config: str = typer.Option(None, "--config", "-c", help="Path to autodocs.yaml"),
    port: int = typer.Option(None, "--port", "-p", help="Port for the preview server"),
) -> None:
    """Generate HTML docs and open a local preview server."""
    src, out, _, cfg = _resolve_paths(source, output, "html", config)
    serve_port = port or cfg.port

    if not src.exists():
        console.print(f"[red]Error:[/red] Source directory not found: {src}")
        raise typer.Exit(1)

    # Build HTML docs
    console.print("[bold cyan]autodocs preview[/bold cyan]\n")
    _build_docs(src, out, "html", cfg)

    # Start HTTP server
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    server = http.server.HTTPServer(("localhost", serve_port), handler)

    url = f"http://localhost:{serve_port}"
    console.print(f"\n[bold green]Preview server running at[/bold green] [link={url}]{url}[/link]")
    console.print("   Press [bold]Ctrl+C[/bold] to stop.\n")

    # Open browser in background
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[bold cyan]Server stopped.[/bold cyan]")
        server.server_close()


@app.command()
def init(
    path: str = typer.Option(".", "--path", help="Directory to create config in"),
) -> None:
    """Create a default autodocs.yaml configuration file."""
    cfg = AutodocsConfig()
    config_path = cfg.save(Path(path) / "autodocs.yaml")
    console.print(f"[green]\u2713[/green] Created config at [cyan]{config_path}[/cyan]")


@app.command("ai-fill")
def ai_fill(
    source: str = typer.Option(None, "--source", "-s", help="Source directory to scan"),
    config: str = typer.Option(None, "--config", "-c", help="Path to autodocs.yaml"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without writing changes"),
    style: str = typer.Option(None, "--style", help="Docstring style: google, numpy, sphinx"),
) -> None:
    """Generate missing docstrings using AI (OpenAI GPT)."""
    from autodocs.ai import DocGenerator

    cfg = AutodocsConfig.load(config)
    src = Path(source or cfg.source).resolve()

    if not src.exists():
        console.print(f"[red]Error:[/red] Source directory not found: {src}")
        raise typer.Exit(1)

    # Resolve API key and style
    api_key = cfg.ai.resolve_api_key()
    doc_style = style or cfg.ai.style

    if not api_key:
        console.print(
            "[red]Error:[/red] No Groq API key found.\n"
            "  Set [cyan]GROQ_API_KEY[/cyan] in .env or autodocs.yaml"
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold]Source:[/bold] {src}\n"
            f"[bold]Style:[/bold] {doc_style}\n"
            f"[bold]Mode:[/bold] {'dry-run (preview)' if dry_run else 'write'}",
            title="[bold cyan]autodocs ai-fill[/bold cyan]",
            border_style="cyan",
        )
    )

    gen = DocGenerator(
        api_key=api_key,
        model=cfg.ai.model,
        style=doc_style,
        max_tokens=cfg.ai.max_tokens,
    )

    # Scan all Python files
    exclude_dirs = set(cfg.exclude or [])
    total_filled = 0

    for py_file in sorted(src.rglob("*.py")):
        if any(part in exclude_dirs for part in py_file.parts):
            continue

        rel = py_file.relative_to(src)
        console.print(f"[dim]Scanning {rel}...[/dim]")

        suggestions = gen.fill_missing_docstrings(py_file, dry_run=dry_run)

        for s in suggestions:
            icon = "[yellow]~[/yellow]" if dry_run else "[green]+[/green]"
            console.print(f"  {icon} {s['type']} [bold]{s['name']}[/bold] (line {s['line']})")
            if dry_run:
                # Show preview of generated docstring
                preview = s["docstring"][:120]
                if len(s["docstring"]) > 120:
                    preview += "..."
                console.print(f"    [dim]{preview}[/dim]")

        total_filled += len(suggestions)

    if total_filled:
        action = "Would fill" if dry_run else "Filled"
        console.print(f"\n[green]\u2713[/green] {action} [bold]{total_filled}[/bold] docstring(s)")
    else:
        console.print("\n[dim]All functions and classes already have docstrings.[/dim]")


@app.command()
def serve(
    source: str = typer.Option(None, "--source", "-s", help="Source directory"),
    output: str = typer.Option(None, "--output", "-o", help="Output directory"),
    fmt: str = typer.Option(None, "--format", "-f", help="Output format (html/markdown)"),
    config: str = typer.Option(None, "--config", "-c", help="Path to autodocs.yaml"),
    port: int = typer.Option(None, "--port", "-p", help="Server port (default: 8000)"),
    webhook_secret: str = typer.Option("", "--webhook-secret", help="GitHub webhook secret"),
) -> None:
    """Start a live documentation server with build API and webhook support."""
    from autodocs.server import create_app

    cfg = AutodocsConfig.load(config)
    src = source or cfg.source
    out = output or cfg.output
    output_fmt = fmt or cfg.format
    server_port = port or cfg.port

    console.print(
        Panel(
            f"[bold]Source:[/bold] {src}\n"
            f"[bold]Output:[/bold] {out}\n"
            f"[bold]Format:[/bold] {output_fmt}\n"
            f"[bold]Port:[/bold] {server_port}",
            title="[bold cyan]autodocs serve[/bold cyan]",
            border_style="cyan",
        )
    )

    fastapi_app = create_app(source=src, output=out, fmt=output_fmt, webhook_secret=webhook_secret)

    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]Error:[/red] uvicorn is required for server mode.\n"
            "  Install with: [cyan]pip install autodocs\\[server][/cyan]"
        )
        raise typer.Exit(1)

    console.print(f"\n[green]Starting server at http://localhost:{server_port}[/green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    uvicorn.run(fastapi_app, host="0.0.0.0", port=server_port, log_level="info")


@app.command()
def deploy(
    output: str = typer.Option(None, "--output", "-o", help="Docs directory to deploy"),
    target: str = typer.Option(..., "--target", "-t", help="Deploy target: netlify, vercel, or s3"),
    config: str = typer.Option(None, "--config", "-c", help="Path to autodocs.yaml"),
) -> None:
    """Deploy generated docs to a hosting provider."""
    cfg = AutodocsConfig.load(config)
    out = Path(output or cfg.output).resolve()

    if not out.exists() or not any(out.iterdir()):
        console.print(
            f"[red]Error:[/red] No docs found at {out}\n  Run [cyan]autodocs generate[/cyan] first."
        )
        raise typer.Exit(1)

    console.print(
        Panel(
            f"[bold]Source:[/bold] {out}\n[bold]Target:[/bold] {target}",
            title="[bold cyan]autodocs deploy[/bold cyan]",
            border_style="cyan",
        )
    )

    try:
        from autodocs.deploy import get_deployer

        deployer = get_deployer(target)
        url = deployer.deploy(out)
        console.print(f"\n[green]Deployed successfully![/green]\n  [cyan]{url}[/cyan]")
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]Deploy failed:[/red] {exc}")
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show autodocs version."""
    console.print(f"[bold cyan]autodocs[/bold cyan] v{__version__}")


# -- Logging setup -------------------------------------------------------------


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Autodocs — self-maintaining code documentation tool."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


if __name__ == "__main__":
    app()

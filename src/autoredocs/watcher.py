"""File watcher for real-time documentation regeneration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from rich.console import Console
from watchfiles import Change, watch

logger = logging.getLogger(__name__)
console = Console()


# Map watchfiles Change enum to human-readable strings
CHANGE_LABELS = {
    Change.added: "[green]added[/green]",
    Change.modified: "[yellow]modified[/yellow]",
    Change.deleted: "[red]deleted[/red]",
}


def watch_and_rebuild(
    source_dir: str | Path,
    rebuild_fn: Callable[[], None],
    extensions: set[str] | None = None,
) -> None:
    """Watch a directory for changes and call rebuild_fn when Python files change.

    Args:
        source_dir: The directory to watch.
        rebuild_fn: Callable invoked on each relevant change batch.
        extensions: File extensions to watch (default: {".py"}).
    """
    source_dir = Path(source_dir).resolve()
    extensions = extensions or {".py"}

    console.print(
        f"\n[bold cyan]👁  Watching[/bold cyan] {source_dir} for changes…\n"
        "   Press [bold]Ctrl+C[/bold] to stop.\n"
    )

    try:
        for changes in watch(source_dir):
            # Filter to only relevant file types
            relevant = [
                (change_type, path)
                for change_type, path in changes
                if Path(path).suffix in extensions
            ]

            if not relevant:
                continue

            # Report what changed
            for change_type, path in relevant:
                rel = Path(path).relative_to(source_dir)
                label = CHANGE_LABELS.get(change_type, str(change_type))
                console.print(f"   {label}  {rel}")

            # Rebuild
            console.print("[dim]   Regenerating docs…[/dim]")
            try:
                rebuild_fn()
                console.print("[green]   ✓ Docs updated[/green]\n")
            except Exception as exc:
                console.print(f"[red]   ✗ Build error: {exc}[/red]\n")
                logger.exception("Rebuild failed")

    except KeyboardInterrupt:
        console.print("\n[bold cyan]Stopped watching.[/bold cyan]")

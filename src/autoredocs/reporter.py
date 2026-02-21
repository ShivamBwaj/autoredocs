"""Build change reporter — structured summaries of documentation changes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@dataclass
class ChangeItem:
    """A single item that changed in the codebase."""

    name: str
    module: str
    kind: str  # "function", "class", "method"
    action: str  # "added", "modified", "removed", "deprecated"
    line: int = 0


@dataclass
class BuildReport:
    """Structured report of a documentation build."""

    source: str = ""
    output: str = ""
    format: str = ""
    incremental: bool = False

    files_scanned: int = 0
    files_changed: int = 0
    files_deleted: int = 0
    files_unchanged: int = 0
    files_generated: int = 0

    modules: int = 0
    functions: int = 0
    classes: int = 0

    deprecated_count: int = 0
    ai_filled_count: int = 0

    changes: list[ChangeItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def added(self) -> list[ChangeItem]:
        """Fetch a list of change items marked as 'added'.

        Args:
            self: The current object instance.

        Returns:
            A list of ChangeItem objects that have been added.

        Raises:
            AttributeError: If self.changes is not a list or attribute.
            TypeError: If self.changes contains non-ChangeItem objects.
        """
        return [c for c in self.changes if c.action == "added"]

    @property
    def modified(self) -> list[ChangeItem]:
        """Fetch modified change items from the list of changes.

        Args:
            self: The instance of the class containing the changes.

        Returns:
            A list of ChangeItem objects that have been modified.

        Raises:
            AttributeError: If the instance does not have a 'changes' attribute.
        """
        return [c for c in self.changes if c.action == "modified"]

    @property
    def removed(self) -> list[ChangeItem]:
        """Fetch removed changes from the list of changes.

        Args:
            self: The instance of the class.
            None: This property does not take any explicit arguments.

        Returns:
            A list of ChangeItem objects representing removed changes.

        Raises:
            AttributeError: If the 'changes' attribute is not set.
            TypeError: If the 'changes' attribute is not a list.
        """
        return [c for c in self.changes if c.action == "removed"]

    @property
    def deprecated(self) -> list[ChangeItem]:
        """Fetch deprecated changes from the list of changes.

        Args:
            self: The instance of the class containing the changes.
            None: This method is a property and does not accept any additional arguments.

        Returns:
            A list of ChangeItem objects representing deprecated changes.

        Raises:
            AttributeError: If the instance does not have a 'changes' attribute.

        Note: This method is deprecated and should not be used in new code.
        """
        return [c for c in self.changes if c.action == "deprecated"]

    def to_json(self) -> str:
        """Serialize report to JSON for CI/CD integration."""
        return json.dumps(
            {
                "source": self.source,
                "output": self.output,
                "format": self.format,
                "incremental": self.incremental,
                "summary": {
                    "files_scanned": self.files_scanned,
                    "files_changed": self.files_changed,
                    "files_deleted": self.files_deleted,
                    "files_unchanged": self.files_unchanged,
                    "files_generated": self.files_generated,
                    "modules": self.modules,
                    "functions": self.functions,
                    "classes": self.classes,
                    "deprecated": self.deprecated_count,
                    "ai_filled": self.ai_filled_count,
                },
                "changes": [
                    {
                        "name": c.name,
                        "module": c.module,
                        "kind": c.kind,
                        "action": c.action,
                        "line": c.line,
                    }
                    for c in self.changes
                ],
                "errors": self.errors,
            },
            indent=2,
        )

    def save_json(self, path: Path) -> None:
        """Write report JSON to file."""
        path.write_text(self.to_json(), encoding="utf-8")

    def print_summary(self, console: Console | None = None) -> None:
        """Print a rich summary to the console."""
        console = console or Console()

        # Change table
        if self.changes:
            table = Table(title="Changes Detected", show_lines=False)
            table.add_column("Action", style="bold", width=12)
            table.add_column("Kind", width=10)
            table.add_column("Name")
            table.add_column("Module", style="dim")

            action_colors = {
                "added": "green",
                "modified": "yellow",
                "removed": "red",
                "deprecated": "magenta",
            }

            for c in self.changes:
                color = action_colors.get(c.action, "white")
                table.add_row(
                    f"[{color}]{c.action}[/{color}]",
                    c.kind,
                    c.name,
                    c.module,
                )
            console.print(table)

        # Summary panel
        lines = [
            f"[bold]Files:[/bold] {self.files_scanned} scanned",
        ]
        if self.incremental:
            lines.append(
                f"  [green]+{self.files_changed}[/green] changed | "
                f"[dim]{self.files_unchanged} unchanged[/dim] | "
                f"[red]-{self.files_deleted} deleted[/red]"
            )
        lines.append(f"[bold]Output:[/bold] {self.files_generated} docs generated")
        lines.append(
            f"[bold]Content:[/bold] {self.modules} modules | "
            f"{self.functions} functions | {self.classes} classes"
        )
        if self.deprecated_count:
            lines.append(f"[bold yellow]Deprecated:[/bold yellow] {self.deprecated_count} items")
        if self.ai_filled_count:
            lines.append(f"[bold cyan]AI-filled:[/bold cyan] {self.ai_filled_count} docstrings")
        if self.errors:
            lines.append(f"[bold red]Errors:[/bold red] {len(self.errors)}")

        console.print(
            Panel(
                "\n".join(lines),
                title="[bold cyan]Build Report[/bold cyan]",
                border_style="cyan",
            )
        )

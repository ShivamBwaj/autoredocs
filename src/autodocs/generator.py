"""Documentation generator — renders parsed code into Markdown and HTML."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from autodocs.models import ProjectDoc

# Path to bundled Jinja2 templates
TEMPLATES_DIR = Path(__file__).parent / "templates"


class MarkdownGenerator:
    """Generates Markdown documentation from parsed project data."""

    def __init__(self):
        """Initializes a Jinja2 Environment instance.

        Args:
            TEMPLATES_DIR: The path to the templates directory.

        Returns:
            A Jinja2 Environment instance configured for file system template loading.

        Raises:
            None
        """
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, project: ProjectDoc, output_dir: str | Path) -> list[Path]:
        """Generate Markdown files for the entire project. Returns list of created files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files: list[Path] = []

        # Generate index page
        index_template = self.env.get_template("index.md.j2")
        index_content = index_template.render(project=project)
        index_path = output_dir / "index.md"
        index_path.write_text(index_content, encoding="utf-8")
        created_files.append(index_path)

        # Generate per-module pages
        module_template = self.env.get_template("module.md.j2")
        for module in project.modules:
            content = module_template.render(module=module, project=project)
            # Create subdirectories for dotted module names
            safe_name = module.module_name.replace(".", "/")
            file_path = output_dir / f"{safe_name}.md"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            created_files.append(file_path)

        return created_files


class HTMLGenerator:
    """Generates styled HTML documentation from parsed project data."""

    def __init__(self):
        """Initialize a Jinja2 template environment and load CSS styles.

        Args:
            None

        Returns:
            None

        Raises:
            None
        """
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Read CSS once at init — will be embedded inline in every page
        css_path = TEMPLATES_DIR / "style.css"
        self._css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    def _relative_prefix(self, file_path: Path, output_dir: Path) -> str:
        """Compute the relative prefix from a file back to the output root.

        Example: if file is at output/sub/page.html, prefix is '../'
        """
        rel = file_path.parent.relative_to(output_dir)
        depth = len(rel.parts)
        if depth == 0:
            return ""
        return "../" * depth

    def generate(self, project: ProjectDoc, output_dir: str | Path) -> list[Path]:
        """Generate HTML files for the entire project. Returns list of created files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        created_files: list[Path] = []
        page_template = self.env.get_template("page.html.j2")

        # Generate index page
        index_path = output_dir / "index.html"
        index_template = self.env.get_template("index.html.j2")
        index_body = index_template.render(project=project)
        index_html = page_template.render(
            title=project.title,
            body=index_body,
            css=self._css,
            project=project,
            current_module=None,
            root_prefix="",
        )
        index_path.write_text(index_html, encoding="utf-8")
        created_files.append(index_path)

        # Generate per-module pages
        module_body_template = self.env.get_template("module.html.j2")
        for module in project.modules:
            body = module_body_template.render(module=module)
            safe_name = module.module_name.replace(".", "/")
            file_path = output_dir / f"{safe_name}.html"
            file_path.parent.mkdir(parents=True, exist_ok=True)

            root_prefix = self._relative_prefix(file_path, output_dir)

            html = page_template.render(
                title=f"{module.module_name} — {project.title}",
                body=body,
                css=self._css,
                project=project,
                current_module=module.module_name,
                root_prefix=root_prefix,
            )
            file_path.write_text(html, encoding="utf-8")
            created_files.append(file_path)

        return created_files

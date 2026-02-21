"""FastAPI server for autodocs — live documentation build & serve."""

from __future__ import annotations

import hashlib
import hmac
import logging
from pathlib import Path

from autodocs.generator import HTMLGenerator, MarkdownGenerator
from autodocs.parser import PythonParser
from autodocs.state import STATE_FILENAME, BuildState

logger = logging.getLogger(__name__)


def create_app(
    source: str | Path = ".",
    output: str | Path = "./docs",
    fmt: str = "html",
    webhook_secret: str = "",
):
    """Create and return a FastAPI application.

    Lazy import to avoid requiring fastapi as a hard dependency.
    """
    try:
        from fastapi import FastAPI, Request, HTTPException
        from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise ImportError(
            "FastAPI is required for server mode. "
            "Install with: pip install autodocs[server]"
        ) from exc

    source = Path(source).resolve()
    output = Path(output).resolve()

    app = FastAPI(
        title="autodocs API",
        description="Live documentation build service",
        version="0.2.0",
    )

    # -- Build endpoint --------------------------------------------------------

    @app.post("/build")
    async def trigger_build():
        """Trigger a documentation rebuild."""
        try:
            result = _run_build(source, output, fmt)
            return JSONResponse({"status": "ok", **result})
        except Exception as exc:
            logger.exception("Build failed")
            raise HTTPException(500, detail=str(exc))

    @app.get("/build/status")
    async def build_status():
        """Check if docs are built and up-to-date."""
        state_path = output / STATE_FILENAME
        has_docs = output.exists() and any(output.iterdir())
        has_state = state_path.exists()
        return {
            "has_docs": has_docs,
            "has_state": has_state,
            "output_dir": str(output),
        }

    # -- GitHub webhook --------------------------------------------------------

    @app.post("/webhook/github")
    async def github_webhook(request: Request):
        """Handle GitHub push webhook — triggers rebuild."""
        body = await request.body()

        # Verify signature if secret is set
        if webhook_secret:
            sig_header = request.headers.get("X-Hub-Signature-256", "")
            expected = "sha256=" + hmac.new(
                webhook_secret.encode(), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(sig_header, expected):
                raise HTTPException(403, detail="Invalid signature")

        event = request.headers.get("X-GitHub-Event", "")
        if event == "push":
            result = _run_build(source, output, fmt)
            return JSONResponse({"status": "rebuilt", **result})
        return JSONResponse({"status": "ignored", "event": event})

    # -- Serve docs ------------------------------------------------------------

    @app.get("/")
    async def serve_index():
        """Redirect to the docs index."""
        index = output / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse(
            "<h1>No docs built yet</h1>"
            "<p>Send a POST to <code>/build</code> first.</p>",
            status_code=200,
        )

    # Mount the output directory as static files
    if output.exists():
        app.mount("/docs", StaticFiles(directory=str(output), html=True), name="docs")

    return app


def _run_build(source: Path, output: Path, fmt: str) -> dict:
    """Run the documentation build pipeline and return stats."""
    parser = PythonParser()
    project = parser.parse_directory(str(source))

    output.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        gen = HTMLGenerator()
    else:
        gen = MarkdownGenerator()

    files = gen.generate(project, output)

    # Update build state
    state = BuildState(output / STATE_FILENAME)
    for py_file in source.rglob("*.py"):
        state.update(py_file)
    state.save()

    return {
        "modules": len(project.modules),
        "files_generated": len(files),
    }

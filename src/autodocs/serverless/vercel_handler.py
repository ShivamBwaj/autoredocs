"""Vercel serverless function handler for autodocs.

Deploy this as a Vercel serverless function to handle
GitHub webhooks and trigger documentation rebuilds.

Usage:
    1. Copy this file to `api/webhook.py` in your Vercel project
    2. Set env vars: AUTODOCS_SOURCE, AUTODOCS_OUTPUT, GITHUB_WEBHOOK_SECRET
    3. Deploy to Vercel
    4. Point your GitHub repo webhook to https://your-app.vercel.app/api/webhook
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path


def handler(request):
    """Vercel serverless function entry point."""
    # Only accept POST
    if request.method != "POST":
        return {"statusCode": 405, "body": "Method not allowed"}

    # Verify GitHub signature
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if secret:
        sig = request.headers.get("x-hub-signature-256", "")
        body = request.body.encode() if isinstance(request.body, str) else request.body
        expected = "sha256=" + hmac.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return {"statusCode": 403, "body": "Invalid signature"}

    # Parse event
    event = request.headers.get("x-github-event", "")
    if event != "push":
        return {"statusCode": 200, "body": json.dumps({"status": "ignored", "event": event})}

    # Run build
    try:
        from autodocs.parser import PythonParser
        from autodocs.generator import HTMLGenerator, MarkdownGenerator
        from autodocs.state import STATE_FILENAME, BuildState

        source = Path(os.getenv("AUTODOCS_SOURCE", ".")).resolve()
        output = Path(os.getenv("AUTODOCS_OUTPUT", "/tmp/docs")).resolve()
        fmt = os.getenv("AUTODOCS_FORMAT", "html")

        output.mkdir(parents=True, exist_ok=True)

        parser = PythonParser()
        project = parser.parse_directory(str(source))

        gen = HTMLGenerator() if fmt == "html" else MarkdownGenerator()
        files = gen.generate(project, output)

        # Update state
        state = BuildState(output / STATE_FILENAME)
        for py in source.rglob("*.py"):
            state.update(py)
        state.save()

        result = {
            "status": "rebuilt",
            "modules": len(project.modules),
            "files": len(files),
        }

        # Optional deploy
        deploy_target = os.getenv("AUTODOCS_DEPLOY_TARGET", "")
        if deploy_target:
            from autodocs.deploy import get_deployer
            deployer = get_deployer(deploy_target)
            url = deployer.deploy(output)
            result["deployed_url"] = url

        return {
            "statusCode": 200,
            "body": json.dumps(result),
            "headers": {"Content-Type": "application/json"},
        }

    except Exception as exc:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
            "headers": {"Content-Type": "application/json"},
        }

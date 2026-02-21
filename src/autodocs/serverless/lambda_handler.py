"""AWS Lambda handler for autodocs.

Deploy this as a Lambda function (behind API Gateway) to handle
GitHub webhooks and trigger documentation rebuilds.

Usage:
    1. Package autodocs as a Lambda layer or bundle
    2. Set env vars: AUTODOCS_SOURCE, AUTODOCS_OUTPUT, GITHUB_WEBHOOK_SECRET
    3. Create API Gateway trigger pointing to this handler
    4. Configure your GitHub repo webhook URL
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path


def lambda_handler(event: dict, context) -> dict:
    """AWS Lambda entry point."""
    # Parse API Gateway event
    method = event.get(
        "httpMethod", event.get("requestContext", {}).get("http", {}).get("method", "")
    )
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = event.get("body", "")

    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    else:
        body_bytes = body or b""

    if method != "POST":
        return _response(405, {"error": "Method not allowed"})

    # Verify signature
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if secret:
        sig = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return _response(403, {"error": "Invalid signature"})

    gh_event = headers.get("x-github-event", "")
    if gh_event != "push":
        return _response(200, {"status": "ignored", "event": gh_event})

    # Build docs
    try:
        from autodocs.parser import PythonParser
        from autodocs.generator import HTMLGenerator, MarkdownGenerator
        from autodocs.state import STATE_FILENAME, BuildState

        source = Path(os.getenv("AUTODOCS_SOURCE", "/var/task/src")).resolve()
        output = Path(os.getenv("AUTODOCS_OUTPUT", "/tmp/docs")).resolve()
        fmt = os.getenv("AUTODOCS_FORMAT", "html")

        output.mkdir(parents=True, exist_ok=True)

        parser = PythonParser()
        project = parser.parse_directory(str(source))

        gen = HTMLGenerator() if fmt == "html" else MarkdownGenerator()
        files = gen.generate(project, output)

        state = BuildState(output / STATE_FILENAME)
        for py in source.rglob("*.py"):
            state.update(py)
        state.save()

        result = {
            "status": "rebuilt",
            "modules": len(project.modules),
            "files": len(files),
        }

        # Deploy if target is set
        deploy_target = os.getenv("AUTODOCS_DEPLOY_TARGET", "")
        if deploy_target:
            from autodocs.deploy import get_deployer

            deployer = get_deployer(deploy_target)
            url = deployer.deploy(output)
            result["deployed_url"] = url

        return _response(200, result)

    except Exception as exc:
        return _response(500, {"error": str(exc)})


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }

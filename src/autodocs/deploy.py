"""Static site deploy module — push generated docs to hosting providers."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseDeployer(ABC):
    """Abstract base class for documentation deployers."""

    @abstractmethod
    def deploy(self, docs_dir: Path) -> str:
        """Deploy docs directory and return the deployed URL."""


class NetlifyDeployer(BaseDeployer):
    """Deploy generated docs to Netlify via the REST API.

    Requires env var NETLIFY_TOKEN and optionally NETLIFY_SITE_ID.
    """

    API_BASE = "https://api.netlify.com/api/v1"

    def __init__(
        self,
        token: str | None = None,
        site_id: str | None = None,
    ):
        self.token = token or os.getenv("NETLIFY_TOKEN", "")
        self.site_id = site_id or os.getenv("NETLIFY_SITE_ID", "")

        if not self.token:
            raise ValueError(
                "Netlify token required. Set NETLIFY_TOKEN env var."
            )

    def deploy(self, docs_dir: Path) -> str:
        import httpx

        headers = {"Authorization": f"Bearer {self.token}"}

        # Create site if no site_id
        if not self.site_id:
            resp = httpx.post(
                f"{self.API_BASE}/sites",
                headers=headers,
                json={"name": f"autodocs-{docs_dir.name}"},
                timeout=30,
            )
            resp.raise_for_status()
            self.site_id = resp.json()["id"]
            logger.info("Created Netlify site: %s", self.site_id)

        # Build file digest for deploy
        file_hashes = {}
        for path in docs_dir.rglob("*"):
            if path.is_file():
                import hashlib

                rel = "/" + str(path.relative_to(docs_dir)).replace("\\", "/")
                sha1 = hashlib.sha1(path.read_bytes()).hexdigest()
                file_hashes[rel] = sha1

        # Create deploy
        resp = httpx.post(
            f"{self.API_BASE}/sites/{self.site_id}/deploys",
            headers={**headers, "Content-Type": "application/json"},
            json={"files": file_hashes},
            timeout=30,
        )
        resp.raise_for_status()
        deploy_data = resp.json()
        deploy_id = deploy_data["id"]
        required = deploy_data.get("required", [])

        # Upload required files
        for rel_path, sha in file_hashes.items():
            if sha in required:
                full_path = docs_dir / rel_path.lstrip("/")
                content_type = (
                    mimetypes.guess_type(str(full_path))[0]
                    or "application/octet-stream"
                )
                resp = httpx.put(
                    f"{self.API_BASE}/deploys/{deploy_id}/files{rel_path}",
                    headers={
                        **headers,
                        "Content-Type": content_type,
                    },
                    content=full_path.read_bytes(),
                    timeout=60,
                )
                resp.raise_for_status()

        url = deploy_data.get("ssl_url", deploy_data.get("url", ""))
        logger.info("Deployed to Netlify: %s", url)
        return url


class VercelDeployer(BaseDeployer):
    """Deploy generated docs to Vercel via the REST API.

    Requires env var VERCEL_TOKEN and optionally VERCEL_PROJECT_ID.
    """

    API_BASE = "https://api.vercel.com"

    def __init__(
        self,
        token: str | None = None,
        project_id: str | None = None,
    ):
        self.token = token or os.getenv("VERCEL_TOKEN", "")
        self.project_id = project_id or os.getenv("VERCEL_PROJECT_ID", "")

        if not self.token:
            raise ValueError(
                "Vercel token required. Set VERCEL_TOKEN env var."
            )

    def deploy(self, docs_dir: Path) -> str:
        import httpx

        headers = {"Authorization": f"Bearer {self.token}"}

        # Collect files
        files = []
        for path in docs_dir.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(docs_dir)).replace("\\", "/")
                data = path.read_text(encoding="utf-8", errors="replace")
                files.append({"file": rel, "data": data})

        payload: dict = {"files": files, "name": "autodocs"}
        if self.project_id:
            payload["project"] = self.project_id

        resp = httpx.post(
            f"{self.API_BASE}/v13/deployments",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()

        url = f"https://{result.get('url', '')}"
        logger.info("Deployed to Vercel: %s", url)
        return url


class S3Deployer(BaseDeployer):
    """Deploy generated docs to an AWS S3 bucket.

    Requires env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET.
    """

    def __init__(
        self,
        bucket: str | None = None,
        region: str | None = None,
    ):
        self.bucket = bucket or os.getenv("S3_BUCKET", "")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")

        if not self.bucket:
            raise ValueError("S3 bucket required. Set S3_BUCKET env var.")

    def deploy(self, docs_dir: Path) -> str:
        try:
            import boto3
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3 deploy. "
                "Install with: pip install boto3"
            ) from exc

        s3 = boto3.client("s3", region_name=self.region)

        for path in docs_dir.rglob("*"):
            if not path.is_file():
                continue
            key = str(path.relative_to(docs_dir)).replace("\\", "/")
            content_type = (
                mimetypes.guess_type(str(path))[0]
                or "application/octet-stream"
            )
            s3.upload_file(
                str(path),
                self.bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )

        url = f"http://{self.bucket}.s3-website-{self.region}.amazonaws.com"
        logger.info("Deployed to S3: %s", url)
        return url


# -- Registry ------------------------------------------------------------------

DEPLOYER_REGISTRY: dict[str, type[BaseDeployer]] = {
    "netlify": NetlifyDeployer,
    "vercel": VercelDeployer,
    "s3": S3Deployer,
}


def get_deployer(target: str, **kwargs) -> BaseDeployer:
    """Get a deployer instance by target name."""
    cls = DEPLOYER_REGISTRY.get(target.lower())
    if cls is None:
        raise ValueError(
            f"Unknown deploy target '{target}'. "
            f"Options: {', '.join(DEPLOYER_REGISTRY.keys())}"
        )
    return cls(**kwargs)

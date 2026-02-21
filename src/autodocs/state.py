"""State tracking for incremental documentation builds.

Stores per-file hashes so only changed / new / deleted files
trigger re-generation. State is persisted as a JSON file in
the output directory.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_FILENAME = ".autodocs_state.json"


class BuildState:
    """Tracks file hashes for incremental builds."""

    def __init__(self, state_path: Path):
        self._path = state_path
        self._hashes: dict[str, str] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────

    def _load(self) -> None:
        """Load previous state from disk."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._hashes = data.get("hashes", {})
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not load build state: %s", exc)
                self._hashes = {}

    def save(self) -> None:
        """Persist current state to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"hashes": self._hashes}
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Hash operations ──────────────────────────────────────────

    @staticmethod
    def _hash_file(filepath: Path) -> str:
        """Compute SHA-256 hash of a file's contents."""
        sha = hashlib.sha256()
        try:
            sha.update(filepath.read_bytes())
        except OSError:
            return ""
        return sha.hexdigest()

    def has_changed(self, filepath: Path) -> bool:
        """Check if a file has changed since the last build."""
        key = str(filepath.resolve())
        current_hash = self._hash_file(filepath)
        previous_hash = self._hashes.get(key, "")
        return current_hash != previous_hash

    def update(self, filepath: Path) -> None:
        """Record the current hash of a file."""
        key = str(filepath.resolve())
        self._hashes[key] = self._hash_file(filepath)

    def remove(self, filepath: Path) -> None:
        """Remove a file's hash from state (file was deleted)."""
        key = str(filepath.resolve())
        self._hashes.pop(key, None)

    def known_files(self) -> set[str]:
        """Return the set of file paths tracked in state."""
        return set(self._hashes.keys())

    # ── Diff operations ──────────────────────────────────────────

    def compute_diff(self, current_files: list[Path]) -> tuple[list[Path], list[Path], list[Path]]:
        """Compare current files against stored state.

        Returns:
            Tuple of (added_or_modified, unchanged, deleted) file lists.
        """
        current_set = {str(f.resolve()) for f in current_files}
        known = self.known_files()

        added_or_modified: list[Path] = []
        unchanged: list[Path] = []

        for f in current_files:
            if self.has_changed(f):
                added_or_modified.append(f)
            else:
                unchanged.append(f)

        # Files in state but no longer on disk
        deleted_keys = known - current_set
        deleted = [Path(k) for k in deleted_keys]

        return added_or_modified, unchanged, deleted

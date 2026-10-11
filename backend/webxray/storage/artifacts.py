"""Artifact (evidence blob) storage.

The interface mirrors an S3-style object store (put/get by key). The local
filesystem implementation is used for development and tests; an S3-compatible
implementation can be dropped in behind the same interface.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from webxray.config import get_settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str


class ArtifactStore(Protocol):
    def put(self, key: str, data: bytes) -> StoredObject: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or key.startswith(("/", "\\")) or ".." in key.split("/"):
            raise ValueError("invalid artifact key")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("artifact key escapes storage root")
        return path

    def put(self, key: str, data: bytes) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return StoredObject(key, len(data), hashlib.sha256(data).hexdigest())

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


_store: ArtifactStore | None = None


def get_artifact_store() -> ArtifactStore:
    global _store
    if _store is None:
        _store = LocalArtifactStore(get_settings().artifact_dir)
    return _store

"""Storage backend abstraction (plan.md Section 1A.8).

One interface, three implementations: B2Backend (real B2, S3-compatible via
boto3), LocalBackend (plain filesystem), FakeBackend (in-memory, with byte/
request counters — the ONLY backend tests may depend on; nothing in tests/
may require real B2 credentials).

No backend defines a delete operation. Removing a local raw file happens
only through src.storage.evict.safe_evict(), and nothing here can mutate or
delete anything in B2 at all — structurally, not just by convention.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.utils.env_check import AuthFailedError, NoCredentialsError, ReadOnlyKeyError, check_b2_credentials_present


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size_bytes: int
    etag: str | None = None


class LocalBackend:
    """A plain local-filesystem backend rooted at `root`."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        search_root = self.root
        if not search_root.is_dir():
            return []
        results = []
        for p in sorted(search_root.rglob("*")):
            if p.is_file():
                rel = p.relative_to(self.root).as_posix()
                if rel.startswith(prefix):
                    results.append(ObjectInfo(key=rel, size_bytes=p.stat().st_size))
        return results

    def stat(self, key: str) -> ObjectInfo:
        p = self._path(key)
        if not p.is_file():
            raise FileNotFoundError(key)
        return ObjectInfo(key=key, size_bytes=p.stat().st_size)

    def open_range(self, key: str, start: int, length: int) -> bytes:
        p = self._path(key)
        if not p.is_file():
            raise FileNotFoundError(key)
        with p.open("rb") as f:
            f.seek(start)
            return f.read(length)

    def download(self, key: str, dest: Path) -> None:
        src = self._path(key)
        if not src.is_file():
            raise FileNotFoundError(key)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())

    def upload(self, src: Path, key: str) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(Path(src).read_bytes())

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class FakeBackend:
    """In-memory backend for tests. Never touches the network or real disk
    beyond what a test explicitly seeds. Counts bytes transferred and
    requests made so tests can assert on both.
    """

    def __init__(self):
        self._objects: dict[str, bytes] = {}
        self.bytes_transferred = 0
        self.request_count = 0

    def seed(self, key: str, data: bytes) -> None:
        """Test fixture helper — populates an object without counting it as
        backend activity (it isn't; it's test setup)."""
        self._objects[key] = data

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        self.request_count += 1
        return [
            ObjectInfo(key=k, size_bytes=len(v)) for k, v in sorted(self._objects.items()) if k.startswith(prefix)
        ]

    def stat(self, key: str) -> ObjectInfo:
        self.request_count += 1
        if key not in self._objects:
            raise FileNotFoundError(key)
        return ObjectInfo(key=key, size_bytes=len(self._objects[key]))

    def open_range(self, key: str, start: int, length: int) -> bytes:
        self.request_count += 1
        if key not in self._objects:
            raise FileNotFoundError(key)
        chunk = self._objects[key][start : start + length]
        self.bytes_transferred += len(chunk)
        return chunk

    def download(self, key: str, dest: Path) -> None:
        self.request_count += 1
        if key not in self._objects:
            raise FileNotFoundError(key)
        data = self._objects[key]
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        self.bytes_transferred += len(data)

    def upload(self, src: Path, key: str) -> None:
        self.request_count += 1
        data = Path(src).read_bytes()
        self._objects[key] = data
        self.bytes_transferred += len(data)

    def exists(self, key: str) -> bool:
        self.request_count += 1
        return key in self._objects


class B2Backend:
    """Real Backblaze B2 backend via its S3-compatible API.

    Read operations need only a read-scoped key; upload needs write scope,
    surfaced as ReadOnlyKeyError (not a generic failure) if the key lacks
    it. `client` can be injected directly for testing the error-mapping
    logic without a real network call or real credentials.
    """

    def __init__(
        self,
        endpoint_url: str,
        bucket: str,
        key_id: str | None = None,
        application_key: str | None = None,
        client=None,
    ):
        self.bucket = bucket
        if client is not None:
            self._client = client
            return

        from src.utils.env_check import REQUIRED_B2_CREDENTIAL_ENV_VARS

        key_id = key_id or os.environ.get(REQUIRED_B2_CREDENTIAL_ENV_VARS[0])
        application_key = application_key or os.environ.get(REQUIRED_B2_CREDENTIAL_ENV_VARS[1])
        if not key_id or not application_key:
            check_b2_credentials_present()  # raises NoCredentialsError with the exact missing var(s)

        import boto3

        self._client = boto3.client(
            service_name="s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=key_id,
            aws_secret_access_key=application_key,
        )

    def _map_client_error(self, exc: Exception, context: str) -> Exception:
        from botocore.exceptions import ClientError

        if not isinstance(exc, ClientError):
            return exc
        code = exc.response.get("Error", {}).get("Code")
        if code in ("InvalidAccessKeyId", "SignatureDoesNotMatch"):
            return AuthFailedError(f"B2 rejected the credentials while {context}: {code}")
        if code in ("AccessDenied", "Forbidden"):
            return ReadOnlyKeyError(f"B2 denied permission while {context} — the key may be read-only scoped")
        return exc

    def list(self, prefix: str = "") -> list[ObjectInfo]:
        results = []
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    results.append(ObjectInfo(key=obj["Key"], size_bytes=obj["Size"]))
        except Exception as e:
            raise self._map_client_error(e, "listing objects") from e
        return results

    def stat(self, key: str) -> ObjectInfo:
        try:
            resp = self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            raise self._map_client_error(e, f"stat'ing {key}") from e
        etag = resp.get("ETag")
        if etag:
            etag = etag.strip('"')
        return ObjectInfo(key=key, size_bytes=resp["ContentLength"], etag=etag)

    def open_range(self, key: str, start: int, length: int) -> bytes:
        end = start + length - 1
        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}")
            return resp["Body"].read()
        except Exception as e:
            raise self._map_client_error(e, f"reading a range of {key}") from e

    def download(self, key: str, dest: Path) -> None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.download_file(self.bucket, key, str(dest))
        except Exception as e:
            raise self._map_client_error(e, f"downloading {key}") from e

    def upload(self, src: Path, key: str) -> None:
        try:
            self._client.upload_file(str(src), self.bucket, key)
        except Exception as e:
            raise self._map_client_error(e, f"uploading {key}") from e

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as e:
            from botocore.exceptions import ClientError

            if isinstance(e, ClientError):
                code = e.response.get("Error", {}).get("Code")
                if code in ("404", "NoSuchKey", "NotFound"):
                    return False
            raise self._map_client_error(e, f"checking existence of {key}") from e

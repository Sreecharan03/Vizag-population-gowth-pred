import ast

import pytest

from src.storage.backends import B2Backend, FakeBackend, LocalBackend
from src.utils.env_check import AuthFailedError, ReadOnlyKeyError
from src.utils.io import find_repo_root

# --- FakeBackend -------------------------------------------------------------


def test_fake_backend_counts_bytes_and_requests():
    backend = FakeBackend()
    backend.seed("a.txt", b"hello world")  # seeding is not counted as activity
    assert backend.request_count == 0
    assert backend.bytes_transferred == 0

    data = backend.open_range("a.txt", 0, 5)
    assert data == b"hello"
    assert backend.request_count == 1
    assert backend.bytes_transferred == 5

    backend.exists("a.txt")
    assert backend.request_count == 2


def test_fake_backend_list_filters_by_prefix():
    backend = FakeBackend()
    backend.seed("raw/a.tif", b"x")
    backend.seed("raw/b.tif", b"yy")
    backend.seed("processed/c.tif", b"zzz")

    results = backend.list(prefix="raw/")
    keys = sorted(o.key for o in results)
    assert keys == ["raw/a.tif", "raw/b.tif"]


def test_fake_backend_download_writes_file_and_counts_bytes(tmp_path):
    backend = FakeBackend()
    backend.seed("a.txt", b"some content")
    dest = tmp_path / "out" / "a.txt"

    backend.download("a.txt", dest)

    assert dest.read_bytes() == b"some content"
    assert backend.bytes_transferred == len(b"some content")
    assert backend.request_count == 1


def test_fake_backend_upload_stores_and_counts_bytes(tmp_path):
    backend = FakeBackend()
    src = tmp_path / "in.txt"
    src.write_bytes(b"upload me")

    backend.upload(src, "dest/in.txt")

    assert backend.stat("dest/in.txt").size_bytes == len(b"upload me")
    assert backend.bytes_transferred == len(b"upload me")


def test_fake_backend_missing_key_raises_file_not_found():
    backend = FakeBackend()
    with pytest.raises(FileNotFoundError):
        backend.stat("does/not/exist.txt")


# --- LocalBackend -------------------------------------------------------------


def test_local_backend_round_trip(tmp_path):
    backend = LocalBackend(root=tmp_path / "root")
    src = tmp_path / "source.txt"
    src.write_bytes(b"local round trip")

    backend.upload(src, "a/b/source.txt")
    assert backend.exists("a/b/source.txt")

    dest = tmp_path / "downloaded.txt"
    backend.download("a/b/source.txt", dest)
    assert dest.read_bytes() == b"local round trip"


def test_local_backend_missing_key_raises_file_not_found(tmp_path):
    backend = LocalBackend(root=tmp_path / "root")
    with pytest.raises(FileNotFoundError):
        backend.stat("nope.txt")


# --- B2Backend error mapping (no real network/credentials) -------------------


class _FakeClientError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class _FakeBoto3Client:
    def __init__(self, error_code):
        self._error_code = error_code

    def get_paginator(self, name):
        raise _FakeClientErrorForBotocore(self._error_code)

    def upload_file(self, *args, **kwargs):
        raise _FakeClientErrorForBotocore(self._error_code)


def _FakeClientErrorForBotocore(code):
    from botocore.exceptions import ClientError

    return ClientError(
        error_response={"Error": {"Code": code, "Message": "synthetic test error"}},
        operation_name="FakeOperation",
    )


def test_b2_backend_maps_invalid_access_key_to_auth_failed():
    client = _FakeBoto3Client("InvalidAccessKeyId")
    backend = B2Backend(endpoint_url="https://example.invalid", bucket="test-bucket", client=client)
    with pytest.raises(AuthFailedError):
        backend.list()


def test_b2_backend_maps_access_denied_to_read_only_key():
    client = _FakeBoto3Client("AccessDenied")
    backend = B2Backend(endpoint_url="https://example.invalid", bucket="test-bucket", client=client)
    with pytest.raises(ReadOnlyKeyError):
        backend.upload("/tmp/does_not_matter", "some/key.txt")


# --- Structural guarantee: no backend can delete anything --------------------


def test_no_backend_exposes_a_delete_method():
    forbidden_names = {"delete", "delete_object", "delete_objects", "delete_bucket", "remove"}
    for backend_cls in (FakeBackend, LocalBackend, B2Backend):
        exposed = forbidden_names & set(dir(backend_cls))
        assert not exposed, f"{backend_cls.__name__} exposes forbidden method(s): {exposed}"


def test_no_code_path_calls_backend_delete_on_b2():
    forbidden_attrs = {"delete_object", "delete_objects", "delete_bucket"}
    repo_root = find_repo_root()
    offenders = []
    for path in sorted((repo_root / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}:{node.attr}")
    assert not offenders, f"Found forbidden delete call(s) against a backend: {offenders}"

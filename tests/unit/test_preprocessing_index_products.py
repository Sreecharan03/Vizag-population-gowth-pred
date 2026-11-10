from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.preprocessing.index_products import (
    put_new_object, require_absent, validate_index_products, write_index_products,
)
from src.preprocessing.indices import BAND_NAMES, INDEX_FORMULAS, IndexPolicy


def make_source(tmp_path, *, all_nodata=False):
    path = tmp_path / "input.tif"
    values = np.tile(np.array([.1, .18, .2, .3, .35, .25], dtype="float32")[:, None, None], (1, 40, 48))
    values[:, :2, :] = -9999
    values[:, 4, 4] = 0
    values[2, 5, 5] = -.1
    if all_nodata:
        values[:] = -9999
    with rasterio.open(path, "w", driver="GTiff", width=48, height=40, count=6,
                       dtype="float32", crs="EPSG:32644", transform=from_origin(706610, 1990390, 10, 10),
                       nodata=-9999, tiled=True, blockxsize=16, blockysize=16) as dst:
        dst.write(values)
        dst.descriptions = BAND_NAMES
    paths = {name: tmp_path / f"{name}.tif" for name in INDEX_FORMULAS}
    return path, paths


def test_index_cogs_roundtrip_full_formula_audit_and_range_qc(tmp_path):
    source, paths = make_source(tmp_path)
    provenance = {"epoch": "2020", "source_sha256": "a" * 64, "contract_version": "3.6.0"}
    result = write_index_products(source, paths, policy=IndexPolicy(), provenance=provenance, chunk_size=16)
    assert set(result) == set(INDEX_FORMULAS)
    assert result["ndvi"]["statistics"]["out_of_range_pixels"] == 1
    for name, info in result.items():
        assert info["bytes"] > 0 and len(info["sha256"]) == 64
        assert info["strict_cog"] and info["local_formula_audit"]
        with rasterio.open(paths[name]) as dataset:
            assert dataset.descriptions == (name.upper(),)
            assert dataset.read(1)[4, 4] == -9999
            assert np.isfinite(dataset.read()).all()
    with rasterio.open(paths["ndvi"]) as dataset:
        assert dataset.read(1)[5, 5] == pytest.approx(2)


def test_full_formula_audit_detects_changed_source(tmp_path):
    source, paths = make_source(tmp_path)
    write_index_products(source, paths, policy=IndexPolicy(), provenance={"epoch": "2020"}, chunk_size=16)
    with rasterio.open(source, "r+") as dataset:
        values = dataset.read()
        values[0, 10, 10] = .2
        dataset.write(values)
    with pytest.raises(RuntimeError, match="formula mismatch"):
        validate_index_products(source, paths, policy=IndexPolicy(), provenance={"epoch": "2020"})


def test_index_writer_preserves_existing_file(tmp_path):
    source, paths = make_source(tmp_path)
    paths["ndvi"].write_bytes(b"preserve-me")
    with pytest.raises(FileExistsError):
        write_index_products(source, paths, policy=IndexPolicy(), provenance={}, chunk_size=16)
    assert paths["ndvi"].read_bytes() == b"preserve-me"


def test_all_nodata_source_halts_before_any_cog(tmp_path):
    source, paths = make_source(tmp_path, all_nodata=True)
    with pytest.raises(RuntimeError, match="empty or numerically invalid"):
        write_index_products(source, paths, policy=IndexPolicy(), provenance={}, chunk_size=16)
    assert not any(path.exists() for path in paths.values())


class FakeClient:
    def __init__(self, pages, fail=False):
        self.pages, self.fail, self.puts = pages, fail, 0

    def get_paginator(self, operation):
        assert operation == "list_object_versions"
        return self

    def paginate(self, **kwargs):
        return self.pages

    def put_object(self, **kwargs):
        self.puts += 1
        if self.fail:
            raise ConnectionError("ambiguous response")
        return {"VersionId": "new-version"}


@pytest.mark.parametrize("group", ["Versions", "DeleteMarkers"])
def test_publication_refuses_versions_or_deletion_markers_on_later_page(group):
    client = FakeClient([{}, {group: [{"Key": "new-key"}]}])
    with pytest.raises(FileExistsError):
        put_new_object(client, "bucket", "new-key", b"data", metadata={}, content_type="image/tiff")
    assert client.puts == 0


def test_publication_does_not_retry_ambiguous_put():
    client = FakeClient([{}], fail=True)
    with pytest.raises(ConnectionError, match="ambiguous"):
        put_new_object(client, "bucket", "new-key", b"data", metadata={}, content_type="image/tiff")
    assert client.puts == 1


def test_unrelated_prefix_does_not_count_as_exact_key_collision():
    client = FakeClient([{"Versions": [{"Key": "new-key-other"}]}])
    require_absent(client, "bucket", ["new-key"])
    assert put_new_object(client, "bucket", "new-key", b"x", metadata={}, content_type="image/tiff")["VersionId"] == "new-version"

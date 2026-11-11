import hashlib
import io
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.grid.dem_validation import (
    download_and_hash, inspect_dem, inspect_dem_header, require_expected_hash, validate_pair,
)


class Stream(io.BytesIO):
    def iter_chunks(self, chunk_size):
        while block := self.read(chunk_size):
            yield block


class FakeClient:
    def __init__(self, body=b"payload", version="v1"):
        self.body, self.version = body, version

    def get_paginator(self, operation):
        assert operation == "list_object_versions"
        return SimpleNamespace(paginate=lambda **kwargs: iter([{}, {"Versions": [
            {"Key": "dem", "Size": len(self.body), "VersionId": self.version, "IsLatest": True}
        ]}]))

    def head_object(self, **kwargs):
        return {"VersionId": self.version, "ContentLength": len(self.body)}

    def get_object(self, **kwargs):
        return {"Body": Stream(self.body)}


def test_download_is_version_pinned_create_only_and_hashed(tmp_path):
    client = FakeClient()
    spec = {"key": "dem", "version_id": "v1", "bytes": len(client.body)}
    target = tmp_path/"dem.tif"
    assert download_and_hash(client, "bucket", spec, target) == hashlib.sha256(client.body).hexdigest()
    assert target.read_bytes() == client.body
    with pytest.raises(FileExistsError):
        download_and_hash(client, "bucket", spec, target)
    with pytest.raises(RuntimeError, match="identity"):
        download_and_hash(FakeClient(version="v2"), "bucket", spec, tmp_path/"other.tif")


def test_inspect_dem_validates_schema_values_and_nodata(tmp_path):
    path = tmp_path/"tile.tif"
    data = np.arange(16, dtype="float32").reshape(4, 4)
    data[0, 0] = -9999
    profile = {"driver": "GTiff", "width": 4, "height": 4, "count": 1,
               "dtype": "float32", "crs": "EPSG:4326", "nodata": -9999.0,
               "transform": from_origin(82, 18, 0.25, 0.25), "tiled": True,
               "blockxsize": 16, "blockysize": 16}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    config = {"expected_band_count": 1, "expected_crs": "EPSG:4326",
              "expected_dtype": "float32", "expected_pixel_size_degrees": 0.25,
              "pixel_size_tolerance_degrees": 1e-12}
    spec = {"key": "tile", "bytes": path.stat().st_size,
            "version_id": "v", "expected_bounds": [82, 17, 83, 18]}
    record = inspect_dem(path, spec, config)
    assert record["valid_pixels"] == 15 and record["nodata_pixels"] == 1
    assert record["minimum_elevation_m"] == 1 and record["maximum_elevation_m"] == 15


def test_header_probe_reports_observed_metadata_without_expected_bounds(tmp_path):
    path = tmp_path/"probe.tif"
    profile = {"driver": "GTiff", "width": 3, "height": 2, "count": 1,
               "dtype": "float32", "crs": "EPSG:4326", "nodata": -9999.0,
               "transform": from_origin(81.5, 18.5, 0.5, 0.5)}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.ones((2, 3), dtype="float32"), 1)
    spec = {"key": "probe", "bytes": path.stat().st_size, "version_id": "v1"}
    record = inspect_dem_header(path, spec)
    assert record["bounds"] == [81.5, 17.5, 83.0, 18.5]
    assert record["transform"] == [0.5, 0.0, 81.5, 0.0, -0.5, 18.5]
    assert record["dtypes"] == ["float32"] and record["band_count"] == 1


def test_pair_requires_exact_bytes_and_compatible_seam():
    config = {"maximum_input_bytes": 30, "contract_version": "v",
              "pixel_size_tolerance_degrees": 1e-12}
    base = {"bytes": 15, "crs": "EPSG:4326", "dtype": "float32", "band_count": 1,
            "resolution_degrees": [1/3600, 1/3600], "nodata": -9999.0}
    left, right = {**base, "bounds": [82, 17, 83, 18]}, {**base, "bounds": [83, 17, 84, 18]}
    assert validate_pair([left, right], config)["status"] == "passed"
    with pytest.raises(RuntimeError, match="seam"):
        validate_pair([left, {**right, "bounds": [83.1, 17, 84.1, 18]}], config)


def test_expected_hash_is_mandatory_and_exact():
    spec = {"key": "dem", "sha256": "abc"}
    require_expected_hash({"sha256": "abc"}, spec)
    with pytest.raises(RuntimeError, match="SHA-256"):
        require_expected_hash({"sha256": "def"}, spec)

import hashlib
import io
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.grid.context_validation import assess_worldpop, download_and_hash, inspect_worldpop


class Stream(io.BytesIO):
    def iter_chunks(self, chunk_size):
        while block := self.read(chunk_size):
            yield block


class FakeClient:
    def __init__(self, body=b"context", version="v1"):
        self.body, self.version = body, version

    def get_paginator(self, operation):
        assert operation == "list_object_versions"
        return SimpleNamespace(paginate=lambda **kwargs: iter([{"Versions": [
            {"Key": "source", "Size": len(self.body), "VersionId": self.version, "IsLatest": True}
        ]}]))

    def head_object(self, **kwargs):
        return {"VersionId": self.version, "ContentLength": len(self.body)}

    def get_object(self, **kwargs):
        return {"Body": Stream(self.body)}


def test_context_download_is_exact_version_hashed_and_create_only(tmp_path):
    client = FakeClient()
    spec = {"key": "source", "version_id": "v1", "bytes": len(client.body)}
    target = tmp_path/"source.bin"
    assert download_and_hash(client, "b", spec, target) == hashlib.sha256(client.body).hexdigest()
    with pytest.raises(FileExistsError):
        download_and_hash(client, "b", spec, target)


def test_worldpop_inspection_records_schema_values_and_pixel_identity(tmp_path):
    path = tmp_path/"population.tif"
    data = np.array([[1, 2], [-9999, 4]], dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1,
                       dtype="float32", crs="EPSG:4326", nodata=-9999,
                       transform=from_origin(82, 18, 0.1, 0.1)) as dst:
        dst.write(data, 1)
    record = inspect_worldpop(path, {"year": 2018, "key": "wp", "bytes": path.stat().st_size,
                                     "version_id": "v"}, {"expected_worldpop_band_count": 1})
    assert record["valid_pixels"] == 3 and record["nodata_pixels"] == 1
    assert record["sum"] == 7 and len(record["pixel_sha256"]) == 64


def test_duplicate_worldpop_pixels_block_growth_even_with_distinct_years():
    base = {"crs": "EPSG:4326", "width": 2, "height": 2, "transform": [1],
            "bounds": [0, 0, 2, 2], "resolution": [1, 1], "dtype": "float32", "nodata": -9999}
    rows = [{**base, "year": year, "pixel_sha256": digest}
            for year, digest in ((2018, "a"), (2020, "b"), (2022, "b"), (2024, "b"))]
    result = assess_worldpop(rows)
    assert result["duplicate_pixel_groups"] == [[2020, 2022, 2024]]
    assert result["growth_calculation_allowed"] is False


def test_misaligned_worldpop_schemas_fail():
    base = {"crs": "EPSG:4326", "width": 2, "height": 2, "transform": [1],
            "bounds": [0, 0, 2, 2], "resolution": [1, 1], "dtype": "float32", "nodata": -9999}
    rows = [{**base, "year": year, "pixel_sha256": str(year)} for year in (2018, 2020, 2022, 2024)]
    rows[-1]["width"] = 3
    with pytest.raises(RuntimeError, match="aligned schema"):
        assess_worldpop(rows)

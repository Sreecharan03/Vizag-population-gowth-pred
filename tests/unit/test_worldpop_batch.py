import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.grid.worldpop_acquisition import inspect_official_raster, resolve_output_key, validate_raster_set


def test_official_raster_schema_and_total_are_validated(tmp_path):
    path = tmp_path/"wp.tif"
    data = np.array([[1, 2], [-99999, 4]], dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=1,
                       dtype="float32", crs="EPSG:4326", nodata=-99999,
                       transform=from_origin(82, 18, 0.1, 0.1)) as dst:
        dst.write(data, 1)
    config = {"expected": {"width": 2, "height": 2, "crs": "EPSG:4326", "nodata": -99999.0,
                           "bounds": [82, 17.8, 82.2, 18], "bounds_tolerance_degrees": 1e-9}}
    record = inspect_official_raster(path, {"year": 2018, "total_population": 7}, config)
    assert record["total_population"] == 7 and record["valid_pixels"] == 3


def test_epoch_set_rejects_duplicate_payload_or_pixels():
    config = {"expected": {"years": [{"year": year} for year in (2018, 2020, 2022, 2024)]}}
    records = [{"year": year, "sha256": str(year), "pixel_sha256": f"p-{year}"}
               for year in (2018, 2020, 2022, 2024)]
    validate_raster_set(records, config)
    records[-1]["pixel_sha256"] = records[-2]["pixel_sha256"]
    with pytest.raises(RuntimeError, match="duplicate epoch pixels"):
        validate_raster_set(records, config)


def test_yaml_integer_year_output_keys_are_resolved_without_string_coercion():
    config = {"outputs": {2018: "prefix/2018.tif"}}
    assert resolve_output_key(config, 2018) == "prefix/2018.tif"
    with pytest.raises(RuntimeError, match="integer key"):
        resolve_output_key({"outputs": {"2018": "wrong.tif"}}, 2018)

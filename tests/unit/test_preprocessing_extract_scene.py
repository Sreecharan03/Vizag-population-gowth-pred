import numpy as np
import rasterio
from rasterio.transform import from_origin

from src.preprocessing.extract_scene import REFLECTANCE_BANDS, write_scene_cogs


def test_write_scene_cogs_round_trip_and_schema(tmp_path):
    reflectance = np.full((6, 64, 64), 0.2, dtype="float32")
    reflectance[:, :4, :] = -9999.0
    scl = np.full((64, 64), 4, dtype="uint8")
    scl[:4, :] = 0
    transform = from_origin(706610, 1990390, 10, 10)
    reflectance_path = tmp_path / "reflectance.tif"
    scl_path = tmp_path / "scl.tif"
    result = write_scene_cogs(
        reflectance, scl, transform=transform, crs="EPSG:32644",
        reflectance_path=reflectance_path, scl_path=scl_path,
        scene_id="test-scene", contract_version="3.3.1",
        source_object_key="raw/test.SAFE.zip", source_size_bytes=123,
        source_etag="etag-123", processing_baseline="05.00",
        quantification_value=10000,
        band_offsets={band: -1000 for band in REFLECTANCE_BANDS},
    )
    assert result["reflectance"]["bytes"] > 0
    assert len(result["reflectance"]["sha256"]) == 64
    with rasterio.open(reflectance_path) as src:
        assert src.driver == "GTiff"
        assert src.descriptions == REFLECTANCE_BANDS
        np.testing.assert_array_equal(src.read()[:, :4, :], -9999.0)
        assert src.tags()["source_object_key"] == "raw/test.SAFE.zip"
        assert src.tags()["source_etag"] == "etag-123"
    with rasterio.open(scl_path) as src:
        np.testing.assert_array_equal(src.read(1)[:4, :], 0)


def test_write_scene_cogs_rejects_mismatched_shapes(tmp_path):
    reflectance = np.zeros((6, 10, 10), dtype="float32")
    scl = np.zeros((9, 10), dtype="uint8")
    try:
        write_scene_cogs(
            reflectance, scl, transform=from_origin(0, 10, 1, 1), crs="EPSG:32644",
            reflectance_path=tmp_path / "r.tif", scl_path=tmp_path / "s.tif",
            scene_id="x", contract_version="3.3.1",
            source_object_key="raw/test.SAFE.zip", source_size_bytes=123,
            source_etag="etag-123", processing_baseline="05.00",
            quantification_value=10000,
            band_offsets={band: -1000 for band in REFLECTANCE_BANDS},
        )
    except ValueError as exc:
        assert "SCL shape" in str(exc)
    else:
        raise AssertionError("shape mismatch was accepted")


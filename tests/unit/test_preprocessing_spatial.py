import numpy as np
import rasterio
from affine import Affine
from rasterio.io import MemoryFile
from rasterio.windows import Window

from src.preprocessing.spatial import grid_from_bounds, resample_array, snap_bounds_outward


def test_bounds_snap_outward_to_frozen_grid():
    assert snap_bounds_outward(
        (699963, 1900017, 700017, 1900073),
        origin_x=699960,
        origin_y=2000040,
        pixel_size=10,
    ) == (699960, 1900010, 700020, 1900080)


def test_grid_dimensions_and_transform_are_exact():
    transform, width, height = grid_from_bounds((100, 200, 160, 250), 10)
    assert (width, height) == (6, 5)
    assert transform == rasterio.transform.from_origin(100, 250, 10, 10)


def test_windowed_read_equals_full_read_then_slice():
    data = np.arange(400, dtype="uint16").reshape(20, 20)
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff", height=20, width=20, count=1, dtype="uint16",
            crs="EPSG:32644", transform=rasterio.transform.from_origin(699960, 2000040, 10, 10),
        ) as dst:
            dst.write(data, 1)
        with mem.open() as src:
            window = Window(3, 4, 7, 8)
            direct = src.read(1, window=window)
            reference = src.read(1)[4:12, 3:10]
    np.testing.assert_array_equal(direct, reference)


def test_scl_nearest_never_creates_new_classes():
    source = np.array([[4, 5], [6, 9]], dtype="uint8")
    result = resample_array(
        source,
        src_transform=Affine(20, 0, 0, 0, -20, 40),
        src_crs="EPSG:32644",
        dst_transform=Affine(10, 0, 0, 0, -10, 40),
        dst_crs="EPSG:32644",
        dst_shape=(4, 4),
        method="nearest",
        src_nodata=0,
        dst_nodata=0,
        dst_dtype="uint8",
    )
    assert set(np.unique(result)) == {4, 5, 6, 9}


def test_bilinear_does_not_mix_nodata_into_valid_values():
    source = np.array([[-9999, -9999], [-9999, 0.4]], dtype="float32")
    result = resample_array(
        source,
        src_transform=Affine(20, 0, 0, 0, -20, 40),
        src_crs="EPSG:32644",
        dst_transform=Affine(10, 0, 0, 0, -10, 40),
        dst_crs="EPSG:32644",
        dst_shape=(4, 4),
        method="bilinear",
        src_nodata=-9999.0,
        dst_nodata=-9999.0,
        dst_dtype="float32",
    )
    valid = result != -9999.0
    assert valid.any()
    np.testing.assert_allclose(result[valid], 0.4, atol=1e-6)


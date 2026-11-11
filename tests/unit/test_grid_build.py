import io
import json

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, box

from src.grid.build_grid import (
    boundary_from_bytes,
    build_grid,
    candidate_bins,
    cell_id,
    validate_grid,
)


def config():
    return {
        "contract_version": "4.1.0",
        "metric_crs": "EPSG:32644",
        "interchange_crs": "EPSG:4326",
        "anchor_m": [0, 0],
        "maximum_candidates": 100,
        "area_tolerance_m2": 0.0001,
        "roundtrip_tolerance_m": 0.001,
    }


def test_fixed_anchor_grid_keeps_full_squares_and_exact_edge_fractions():
    boundary = gpd.GeoDataFrame(
        geometry=[box(250, 250, 1250, 1250)], crs="EPSG:32644"
    )
    grid, candidates = build_grid(boundary, size=500, config=config())
    report, geojson = validate_grid(grid, boundary, size=500, config=config())
    assert candidates == 9
    assert len(grid) == 9
    assert set(grid.grid_id) == {
        cell_id(e, n, 32644) for e in range(0, 3) for n in range(0, 3)
    }
    assert grid.geometry.area.eq(250_000).all()
    assert grid.aoi_area_m2.sum() == pytest.approx(1_000_000)
    assert sorted(grid.aoi_fraction) == pytest.approx(
        sorted([0.25, 0.5, 0.25, 0.5, 1.0, 0.5, 0.25, 0.5, 0.25])
    )
    assert report["missing_aoi_area_m2"] == pytest.approx(0)
    assert report["overlap_area_m2"] == pytest.approx(0)
    assert len(json.loads(geojson)["features"]) == 9
    # RFC 7946 GeoJSON uses WGS84 coordinates and normally omits the legacy
    # top-level `crs` member. Validate the interpreted CRS, not that member.
    reopened = gpd.read_file(io.BytesIO(geojson))
    assert reopened.crs.to_epsg() == 4326


def test_stable_ids_do_not_depend_on_boundary_feature_order():
    features = [box(0, 0, 500, 500), box(500, 0, 1000, 500)]
    first = gpd.GeoDataFrame(geometry=features, crs="EPSG:32644")
    second = gpd.GeoDataFrame(geometry=list(reversed(features)), crs="EPSG:32644")
    grid1, _ = build_grid(first, size=500, config=config())
    grid2, _ = build_grid(second, size=500, config=config())
    assert set(grid1.grid_id) == set(grid2.grid_id)
    assert set(grid1.grid_id) == {"EPSG32644_E0_N0", "EPSG32644_E1_N0"}


def test_boundary_parser_reprojects_and_rejects_bad_or_empty_inputs():
    source = gpd.GeoDataFrame(geometry=[box(83.1, 17.6, 83.11, 17.61)], crs="EPSG:4326")
    parsed = boundary_from_bytes(source.to_json(drop_id=True).encode(), "EPSG:32644")
    assert parsed.crs.to_string() == "EPSG:32644" and parsed.area.sum() > 0
    with pytest.raises(ValueError, match="nonempty boundary"):
        boundary_from_bytes(b'{"type":"FeatureCollection","features":[]}', "EPSG:32644")
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    bad = gpd.GeoDataFrame(geometry=[bowtie], crs="EPSG:4326")
    with pytest.raises(ValueError, match="valid nonempty"):
        boundary_from_bytes(bad.to_json(drop_id=True).encode(), "EPSG:32644")


def test_candidate_range_and_guard_fail_closed():
    east, north = candidate_bins((250, 250, 1250, 1250), 500, (0, 0))
    assert list(east) == [0, 1, 2] and list(north) == [0, 1, 2]
    boundary = gpd.GeoDataFrame(geometry=[box(0, 0, 2000, 2000)], crs="EPSG:32644")
    tiny_cap = {**config(), "maximum_candidates": 15}
    with pytest.raises(ValueError, match="upper bound"):
        build_grid(boundary, size=500, config=tiny_cap)


def test_validation_detects_duplicate_ids_and_gaps():
    boundary = gpd.GeoDataFrame(geometry=[box(0, 0, 1000, 500)], crs="EPSG:32644")
    grid, _ = build_grid(boundary, size=500, config=config())
    duplicate = grid.copy()
    duplicate.loc[1, "grid_id"] = duplicate.loc[0, "grid_id"]
    with pytest.raises(ValueError, match="unique"):
        validate_grid(duplicate, boundary, size=500, config=config())
    with pytest.raises(ValueError, match="gaps"):
        validate_grid(grid.iloc[:1].copy(), boundary, size=500, config=config())

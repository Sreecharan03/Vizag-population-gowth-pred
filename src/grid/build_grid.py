"""Deterministic metric squares; no labels, features or land-cover exclusions."""
from __future__ import annotations

import io
import json
import math

import geopandas as gpd
import numpy as np
from shapely.geometry import box


def validate_boundary(boundary):
    if boundary.crs is None or boundary.empty:
        raise ValueError("Boundary needs a CRS and nonempty polygon features")
    if (boundary.geometry.isna().any() or boundary.geometry.is_empty.any()
            or not boundary.geometry.is_valid.all()
            or not boundary.geom_type.isin(["Polygon", "MultiPolygon"]).all()):
        raise ValueError("Boundary must contain only valid nonempty polygons")


def boundary_from_bytes(body, metric_crs):
    parsed = json.loads(body)
    if parsed.get("type") != "FeatureCollection" or not parsed.get("features"):
        raise ValueError("Expected nonempty boundary FeatureCollection")
    boundary = gpd.read_file(io.BytesIO(body))
    validate_boundary(boundary)
    boundary = boundary.to_crs(metric_crs)
    validate_boundary(boundary)
    if not np.isfinite(boundary.total_bounds).all() or boundary.area.sum() <= 0:
        raise ValueError("Boundary has nonfinite coordinates or zero area")
    return boundary


def candidate_bins(bounds, size, anchor):
    if not math.isfinite(size) or size <= 0 or len(anchor) != 2:
        raise ValueError("Invalid grid size or anchor")
    if not all(math.isfinite(v) for v in (*bounds, *anchor)):
        raise ValueError("Grid bounds/anchor must be finite")
    xmin, ymin, xmax, ymax = bounds
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("Empty grid extent")
    return (range(math.floor((xmin-anchor[0])/size), math.ceil((xmax-anchor[0])/size)),
            range(math.floor((ymin-anchor[1])/size), math.ceil((ymax-anchor[1])/size)))


def cell_id(easting_bin, northing_bin, epsg):
    return f"EPSG{epsg}_E{easting_bin}_N{northing_bin}"


def build_grid(boundary, *, size, config):
    validate_boundary(boundary)
    if boundary.crs.to_string() != config["metric_crs"]:
        raise ValueError("Construct grid in the configured metric CRS")
    if not boundary.crs.is_projected or boundary.crs.axis_info[0].unit_name != "metre":
        raise ValueError("Grid construction requires metre coordinates")
    aoi = boundary.geometry.union_all()
    anchor = config["anchor_m"]
    eastings, northings = candidate_bins(aoi.bounds, size, anchor)
    candidates = len(eastings)*len(northings)
    if candidates > config["maximum_candidates"]:
        raise ValueError("Grid candidate count exceeds approved upper bound")
    rows = []
    for east in eastings:
        for north in northings:
            x, y = anchor[0]+east*size, anchor[1]+north*size
            square = box(x, y, x+size, y+size)
            inside = square.intersection(aoi).area
            if inside > 0:
                rows.append({"grid_id": cell_id(east, north, boundary.crs.to_epsg()),
                             "easting_bin": east, "northing_bin": north,
                             "cell_area_m2": size*size, "aoi_area_m2": inside,
                             "aoi_fraction": inside/(size*size), "geometry": square})
    if not rows:
        raise ValueError("Grid contains no positive-area intersections")
    return gpd.GeoDataFrame(rows, crs=boundary.crs), candidates


def validate_grid(grid, boundary, *, size, config):
    """Independent schema/geometry/coverage audit, including geographic round-trip."""
    validate_boundary(boundary)
    if grid.empty or grid.crs != boundary.crs or grid.crs.to_string() != config["metric_crs"]:
        raise ValueError("Grid is empty or has a wrong CRS")
    if grid.grid_id.duplicated().any() or not grid.geometry.is_valid.all():
        raise ValueError("Grid IDs must be unique and geometries valid")
    tolerance, anchor = config["area_tolerance_m2"], config["anchor_m"]
    aoi = boundary.geometry.union_all()
    for row in grid.itertuples():
        east, north = row.easting_bin, row.northing_bin
        if int(east) != east or int(north) != north:
            raise ValueError("Noninteger grid coordinate bins")
        x, y = anchor[0]+east*size, anchor[1]+north*size
        expected = box(x, y, x+size, y+size)
        if (row.grid_id != cell_id(east, north, grid.crs.to_epsg())
                or not row.geometry.equals(expected)
                or abs(row.cell_area_m2-size*size) > tolerance):
            raise ValueError("Grid ID, anchor or full square dimensions mismatch")
        inside = row.geometry.intersection(aoi).area
        if (inside <= 0 or inside > size*size+tolerance
                or abs(row.aoi_area_m2-inside) > tolerance
                or not 0 < row.aoi_fraction <= 1+tolerance/(size*size)
                or abs(row.aoi_fraction-inside/(size*size)) > tolerance/(size*size)):
            raise ValueError("Invalid AOI area/fraction on grid cell")
    union = grid.geometry.union_all()
    missing = aoi.difference(union).area
    overlap = max(0.0, float(grid.area.sum()-union.area))
    area_error = abs(float(grid.aoi_area_m2.sum())-aoi.area)
    if max(missing, overlap, area_error) > tolerance:
        raise ValueError("Grid has gaps, overlaps or inconsistent intersection areas")
    geographic = grid.to_crs(config["interchange_crs"])
    geojson = geographic.to_json(drop_id=True, na="null").encode()
    restored = gpd.read_file(io.BytesIO(geojson)).to_crs(grid.crs)
    restored = restored.set_index("grid_id").loc[grid.grid_id]
    if len(restored) != len(grid):
        raise ValueError("GeoJSON round-trip lost grid rows")
    displacement = max(a.hausdorff_distance(b) for a, b in zip(grid.geometry, restored.geometry))
    if displacement > config["roundtrip_tolerance_m"]:
        raise ValueError("GeoJSON geographic round-trip exceeds metric tolerance")
    report = {"status": "passed", "contract_version": config["contract_version"],
              "geometry_only": True, "metric_crs": config["metric_crs"],
              "interchange_crs": config["interchange_crs"], "cell_size_m": size,
              "anchor_m": anchor, "grid_cells": len(grid),
              "full_cells": int((grid.aoi_fraction >= 1-tolerance/(size*size)).sum()),
              "edge_cells": int((grid.aoi_fraction < 1-tolerance/(size*size)).sum()),
              "aoi_area_m2": float(aoi.area), "missing_aoi_area_m2": float(missing),
              "overlap_area_m2": overlap, "intersection_area_error_m2": area_error,
              "maximum_roundtrip_displacement_m": float(displacement),
              "aoi_fraction_min": float(grid.aoi_fraction.min()),
              "aoi_fraction_max": float(grid.aoi_fraction.max()),
              "metric_grid_bounds": [float(v) for v in grid.total_bounds],
              "area_tolerance_m2": tolerance,
              "roundtrip_tolerance_m": config["roundtrip_tolerance_m"],
              "water_and_boundary_cells_retained": True,
              "features_labels_predictions_created": False,
              "grid_review": "pending_user_visual_review"}
    return report, geojson


def render_preview(grid, boundary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter
    fig, ax = plt.subplots(figsize=(9, 10))
    grid.plot(ax=ax, column="aoi_fraction", cmap="Blues", vmin=0, vmax=1,
              edgecolor="#8193a0", linewidth=0.12, legend=True,
              legend_kwds={"label": "Fraction of each full square inside buffered AOI", "shrink": 0.65})
    boundary.boundary.plot(ax=ax, color="#b02b34", linewidth=1.2)
    ax.set_title("Visakhapatnam | fixed 500 m analysis grid\nGeometry only - not a prediction map", pad=14)
    ax.set_xlabel("Easting (km), EPSG:32644")
    ax.set_ylabel("Northing (km), EPSG:32644")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x/1000:.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y/1000:.0f}"))
    ax.set_aspect("equal")
    ax.text(0.97, 0.97, "N ↑", transform=ax.transAxes, ha="right", va="top")
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=130)
    plt.close(fig)
    return buffer.getvalue()

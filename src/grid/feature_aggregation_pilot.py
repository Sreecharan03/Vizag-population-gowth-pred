"""Bounded one-index real-data pilot for Part 4.2b."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src.grid.feature_aggregation import aggregate_labeled_values, validate_index_aggregation


def build_cell_labels(grid, boundary, *, out_shape, transform, raster_crs, expected_cells):
    from rasterio.features import rasterize

    if len(grid) != expected_cells or grid["grid_id"].nunique() != expected_cells:
        raise RuntimeError("Pilot grid does not contain exactly 6,371 unique IDs")
    if grid["grid_id"].isna().any() or grid.geometry.isna().any() or boundary.geometry.isna().any():
        raise RuntimeError("Pilot grid/boundary contains missing identity or geometry")
    projected_grid = grid.to_crs(raster_crs).sort_values("grid_id").reset_index(drop=True)
    projected_boundary = boundary.to_crs(raster_crs)
    labels = rasterize(
        ((geometry, position + 1) for position, geometry in enumerate(projected_grid.geometry)),
        out_shape=out_shape, transform=transform, fill=0, dtype="int32", all_touched=False,
    )
    inside = rasterize(
        ((geometry, 1) for geometry in projected_boundary.geometry), out_shape=out_shape,
        transform=transform, fill=0, dtype="uint8", all_touched=False,
    ).astype(bool)
    labels[~inside] = 0
    return labels, projected_grid


def _quantiles(values):
    values = np.asarray(values, dtype="float64")
    values = values[np.isfinite(values)]
    if not values.size:
        return {name: None for name in ("min", "p05", "p25", "median", "p75", "p95", "max")}
    q = np.quantile(values, [0, .05, .25, .5, .75, .95, 1])
    return dict(zip(("min", "p05", "p25", "median", "p75", "p95", "max"), map(float, q)))


def run_pilot(index_path, grid_path, boundary_path, config):
    import geopandas as gpd
    import rasterio

    grid, boundary = gpd.read_file(grid_path), gpd.read_file(boundary_path)
    with rasterio.open(index_path) as src:
        if (src.count != 1 or src.crs is None or src.crs.to_string() != config["expected_crs"]
                or src.dtypes[0] != "float32"):
            raise RuntimeError("Pilot index schema differs from the approved contract")
        labels, ordered_grid = build_cell_labels(
            grid, boundary, out_shape=(src.height, src.width), transform=src.transform,
            raster_crs=src.crs, expected_cells=config["expected_cells"],
        )
        values = src.read(1)
        nodata = src.nodata
        raster_header = {"crs": src.crs.to_string(), "width": src.width,
                         "height": src.height, "dtype": src.dtypes[0], "nodata": nodata,
                         "transform": list(src.transform)[:6], "bounds": list(src.bounds)}
    candidate_total = int(np.count_nonzero(labels))
    if candidate_total <= 0:
        raise RuntimeError("Pilot produced no AOI candidate pixels")
    result = aggregate_labeled_values(values, labels, config["expected_cells"], nodata=nodata)
    validate_index_aggregation(result, expected_cells=config["expected_cells"],
                               candidate_total=candidate_total)
    means = result["filtered_mean"]
    finite_means = means[np.isfinite(means)]
    if finite_means.size and ((finite_means < -1.000001).any() or (finite_means > 1.000001).any()):
        raise RuntimeError("Filtered pilot means escaped the approved index range")
    usable = result["usable_pixel_count"]
    lowest = np.argsort(result["usable_fraction_of_aoi_pixels"], kind="stable")[:20]
    return {
        "status": "pilot_passed_pending_support_policy_review",
        "part": "4.2b-pilot", "contract_version": config["contract_version"],
        "epoch": config["index"]["epoch"], "role": config["index"]["role"],
        "grid_cells": config["expected_cells"], "unique_grid_ids": int(ordered_grid["grid_id"].nunique()),
        "candidate_pixels": candidate_total,
        "input_valid_pixels": int(result["input_valid_pixel_count"].sum()),
        "nodata_pixels": int(result["nodata_pixel_count"].sum()),
        "out_of_range_excluded_pixels": int(result["out_of_range_excluded_pixel_count"].sum()),
        "usable_pixels": int(usable.sum()), "cells_with_usable_pixels": int(np.count_nonzero(usable)),
        "cells_without_usable_pixels": int(np.count_nonzero(usable == 0)),
        "usable_fraction_distribution": _quantiles(result["usable_fraction_of_aoi_pixels"]),
        "filtered_mean_distribution": _quantiles(means),
        "lowest_support_cells": [
            {"grid_id": ordered_grid.iloc[int(i)]["grid_id"],
             "aoi_pixel_count": int(result["aoi_pixel_count"][i]),
             "usable_pixel_count": int(usable[i]),
             "usable_fraction": float(result["usable_fraction_of_aoi_pixels"][i])}
            for i in lowest
        ],
        "raster": raster_header, "support_policy_status": "pending_user_approval",
        "b2_writes": 0, "full_aggregation_started": False,
    }


def render_markdown(report):
    return ("# Part 4.2b 2024 NDVI pilot\n\n"
            f"Status: **{report['status']}**.\n\n"
            f"- Grid cells: {report['grid_cells']:,}\n"
            f"- AOI candidate pixels: {report['candidate_pixels']:,}\n"
            f"- Input-valid / nodata: {report['input_valid_pixels']:,} / {report['nodata_pixels']:,}\n"
            f"- Out-of-range exclusions: {report['out_of_range_excluded_pixels']:,}\n"
            f"- Usable pixels: {report['usable_pixels']:,}\n"
            f"- Cells with/without usable pixels: {report['cells_with_usable_pixels']:,} / "
            f"{report['cells_without_usable_pixels']:,}\n"
            "- B2 writes: 0\n- Full aggregation started: no\n"
            "- Support policy: pending user approval\n\n"
            "This pilot does not publish a feature table or choose a support threshold.\n").encode()

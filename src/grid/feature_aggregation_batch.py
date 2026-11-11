"""Full provisional Part 4.2 feature calculation and create-only publication."""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
import math

import numpy as np
import pandas as pd

from src.grid.feature_aggregation import (
    aggregate_continuous, aggregate_labeled_values, slope_degrees,
    validate_feature_frames, validate_index_aggregation,
)
from src.grid.feature_aggregation_pilot import build_cell_labels
from src.storage.archive_publish import _put_and_verify, exact_versions, require_new_keys


MANIFEST = "feature_aggregation_manifest.contract-4.2.0.json"


def _index_result(path, grid, boundary, config):
    import rasterio
    with rasterio.open(path) as src:
        if src.count != 1 or src.crs is None or src.crs.to_string() != config["analysis_crs"]:
            raise RuntimeError("Index schema/CRS differs from batch contract")
        labels, ordered = build_cell_labels(
            grid, boundary, out_shape=(src.height, src.width), transform=src.transform,
            raster_crs=src.crs, expected_cells=config["expected_cells"])
        result = aggregate_labeled_values(src.read(1), labels, config["expected_cells"], nodata=src.nodata)
    candidates = int(np.count_nonzero(labels))
    validate_index_aggregation(result, expected_cells=config["expected_cells"], candidate_total=candidates)
    return ordered, result, candidates


def build_satellite(index_paths, grid, boundary, config):
    rows, summaries, canonical_ids = {}, [], None
    for spec, path in index_paths:
        ordered, result, candidates = _index_result(path, grid, boundary, config)
        ids = ordered["grid_id"].tolist()
        if canonical_ids is None:
            canonical_ids = ids
        elif ids != canonical_ids:
            raise RuntimeError("Grid ordering changed between index rasters")
        epoch, role = int(spec["epoch"]), spec["role"]
        frame = rows.setdefault(epoch, pd.DataFrame({"grid_id": ids, "epoch": epoch}))
        for name, values in result.items():
            frame[f"{role}_{name}"] = values
        summaries.append({
            "epoch": epoch, "role": role, "candidate_pixels": candidates,
            "input_valid_pixels": int(result["input_valid_pixel_count"].sum()),
            "nodata_pixels": int(result["nodata_pixel_count"].sum()),
            "excluded_pixels": int(result["out_of_range_excluded_pixel_count"].sum()),
            "usable_pixels": int(result["usable_pixel_count"].sum()),
            "cells_without_usable": int(np.count_nonzero(result["usable_pixel_count"] == 0)),
            "usable_fraction_p05": float(np.quantile(result["usable_fraction_of_aoi_pixels"], .05)),
            "usable_fraction_median": float(np.median(result["usable_fraction_of_aoi_pixels"])),
        })
    if set(rows) != set(config["epochs"]):
        raise RuntimeError("Batch did not produce every configured epoch")
    return pd.concat([rows[e] for e in config["epochs"]], ignore_index=True), summaries


def build_terrain(dem_paths, grid, boundary, config):
    import rasterio
    from affine import Affine
    from rasterio.merge import merge
    from rasterio.warp import Resampling, reproject

    metric_grid = grid.to_crs(config["analysis_crs"]).sort_values("grid_id").reset_index(drop=True)
    metric_boundary = boundary.to_crs(config["analysis_crs"])
    resolution = float(config["terrain_resolution_m"])
    minx, miny, maxx, maxy = metric_grid.total_bounds
    left, bottom = math.floor(minx/resolution)*resolution, math.floor(miny/resolution)*resolution
    right, top = math.ceil(maxx/resolution)*resolution, math.ceil(maxy/resolution)*resolution
    width, height = int(round((right-left)/resolution)), int(round((top-bottom)/resolution))
    transform = Affine(resolution, 0, left, 0, -resolution, top)
    sources = [rasterio.open(path) for path in dem_paths]
    try:
        if (len(sources) != 2 or sources[0].crs != sources[1].crs
                or sources[0].dtypes[0] != sources[1].dtypes[0]
                or sources[0].res != sources[1].res):
            raise RuntimeError("Native DEM tiles do not share the validated mosaic schema")
        native, native_transform = merge(sources, nodata=np.nan, dtype="float32", method="first")
        native_crs = sources[0].crs
    finally:
        for source in sources:
            source.close()
    if native.shape[0] != 1 or not np.isfinite(native[0]).any():
        raise RuntimeError("Native DEM mosaic is empty or has an unexpected band count")
    mosaic = np.full((height, width), np.nan, dtype="float32")
    reproject(source=native[0], destination=mosaic,
              src_transform=native_transform, src_crs=native_crs, src_nodata=np.nan,
              dst_transform=transform, dst_crs=config["analysis_crs"], dst_nodata=np.nan,
              resampling=Resampling.bilinear, init_dest_nodata=True)
    labels, ordered = build_cell_labels(metric_grid, metric_boundary, out_shape=mosaic.shape,
                                        transform=transform, raster_crs=config["analysis_crs"],
                                        expected_cells=config["expected_cells"])
    elevation = aggregate_continuous(mosaic, labels, config["expected_cells"])
    slope_array = slope_degrees(mosaic, resolution, np.isfinite(mosaic))
    slope = aggregate_continuous(slope_array, labels, config["expected_cells"])
    frame = pd.DataFrame({
        "grid_id": ordered["grid_id"],
        "elevation_aoi_pixel_count": elevation["aoi_pixel_count"],
        "elevation_valid_pixel_count": elevation["valid_pixel_count"],
        "elevation_nodata_pixel_count": elevation["nodata_pixel_count"],
        "elevation_valid_fraction": elevation["valid_fraction"],
        "elevation_mean_m": elevation["mean"],
        "slope_valid_pixel_count": slope["valid_pixel_count"],
        "slope_valid_fraction": slope["valid_fraction"],
        "slope_mean_degrees": slope["mean"],
    })
    finite_elev, finite_slope = frame.elevation_mean_m.dropna(), frame.slope_mean_degrees.dropna()
    if (finite_elev.empty or finite_slope.empty or finite_elev.min() < -500 or finite_elev.max() > 9000
            or finite_slope.min() < 0 or finite_slope.max() > 90):
        raise RuntimeError("Terrain feature ranges are implausible")
    summary = {"cells_without_elevation": int(frame.elevation_mean_m.isna().sum()),
               "elevation_min_m": float(finite_elev.min()), "elevation_max_m": float(finite_elev.max()),
               "slope_min_degrees": float(finite_slope.min()), "slope_max_degrees": float(finite_slope.max())}
    return frame, summary


def _parquet_bytes(frame):
    stream = BytesIO(); frame.to_parquet(stream, index=False, compression="zstd")
    return stream.getvalue()


def build_payloads(satellite, terrain, summaries, terrain_summary, grid, config):
    import matplotlib.pyplot as plt
    validate_feature_frames(satellite, terrain, expected_cells=config["expected_cells"],
                            epochs=config["epochs"], roles=config["roles"])
    summary = {"status": "provisional_pending_support_policy_review",
               "contract_version": config["contract_version"], "grid_cells": config["expected_cells"],
               "satellite_rows": len(satellite), "terrain_rows": len(terrain),
               "support_policy_status": config["support_policy_status"],
               "satellite": summaries, "terrain": terrain_summary}
    summary_json = (json.dumps(summary, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    summary_csv = pd.DataFrame(summaries).to_csv(index=False).encode()
    plot_grid = grid.sort_values("grid_id").reset_index(drop=True).copy()
    fig, axes = plt.subplots(2, 2, figsize=(12, 10), constrained_layout=True)
    for epoch, axis in zip(config["epochs"], axes.ravel()):
        frame = satellite[satellite.epoch == epoch].set_index("grid_id")
        fractions = pd.concat([frame[f"{r}_usable_fraction_of_aoi_pixels"] for r in config["roles"]], axis=1).min(axis=1)
        plot_grid["minimum_usable_fraction"] = plot_grid.grid_id.map(fractions)
        plot_grid.plot(column="minimum_usable_fraction", vmin=0, vmax=1, cmap="viridis", ax=axis,
                       legend=True, missing_kwds={"color": "lightgrey"})
        axis.set_title(f"{epoch}: minimum usable fraction across five indices"); axis.set_axis_off()
    stream = BytesIO(); fig.savefig(stream, format="png", dpi=160); plt.close(fig)
    payloads = {"satellite_cell_features.parquet": _parquet_bytes(satellite),
                "terrain_cell_features.parquet": _parquet_bytes(terrain),
                "support_summary.json": summary_json, "support_summary.csv": summary_csv,
                "support_maps.png": stream.getvalue()}
    for name, body in payloads.items():
        if not body or len(body) > config["file_caps"][name]:
            raise RuntimeError(f"Feature output exceeds cap: {name}")
    if sum(map(len, payloads.values())) + config["file_caps"][MANIFEST] > config["maximum_new_bytes"]:
        raise RuntimeError("Feature outputs exceed combined publication cap")
    return payloads, summary


def publish_payloads(client, bucket, payloads, config):
    keys = list(config["outputs"].values())
    require_new_keys(client, bucket, keys)
    verified = []
    for name, body in payloads.items():
        verified.append({"name": name, **_put_and_verify(
            client, bucket, config["outputs"][name], body, config["contract_version"])})
    record = {"status": "provisional_pending_support_policy_review", "part": "4.2b",
              "contract_version": config["contract_version"], "support_policy_status": config["support_policy_status"],
              "outputs": verified, "source_outputs_overwritten": False}
    body = (json.dumps(record, sort_keys=True, separators=(",", ":"))+"\n").encode()
    if len(body) > config["file_caps"][MANIFEST]:
        raise RuntimeError("Feature manifest exceeds cap")
    manifest = _put_and_verify(client, bucket, config["outputs"][MANIFEST], body, config["contract_version"])
    verified.append({"name": MANIFEST, **manifest})
    for item in verified:
        versions = exact_versions(client, bucket, item["key"])
        if len(versions) != 1 or versions[0].get("VersionId") != item["version_id"]:
            raise RuntimeError("Published feature version history changed")
    return {"status": record["status"], "outputs": verified,
            "new_bytes": sum(item["bytes"] for item in verified), "b2_writes": len(verified)}

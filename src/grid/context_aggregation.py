"""Per-cell population and historical OSM context aggregation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def aggregate_population(grid, raster_path, year: int):
    import rasterio
    from rasterio.features import rasterize

    with rasterio.open(raster_path) as src:
        aligned = grid.to_crs(src.crs)
        labels = rasterize(((geom, index + 1) for index, geom in enumerate(aligned.geometry)),
                           out_shape=(src.height, src.width), transform=src.transform,
                           fill=0, dtype="int32")
        values = src.read(1, masked=True)
    valid = (~np.ma.getmaskarray(values)) & (labels > 0) & np.isfinite(values.data) & (values.data >= 0)
    totals = np.bincount(labels[valid], weights=values.data[valid],
                         minlength=len(grid)+1)[1:]
    return pd.DataFrame({"grid_id": grid["grid_id"].to_numpy(), "epoch": int(year),
                         "population_total": totals,
                         "population_density_per_km2": totals/(grid["aoi_area_m2"].to_numpy()/1e6)})


def aggregate_osm(grid, roads, amenities, year: int):
    import geopandas as gpd

    metric_grid = grid.to_crs("EPSG:32644")
    roads = roads.to_crs(metric_grid.crs)
    amenities = amenities.to_crs(metric_grid.crs)
    pieces = gpd.overlay(roads[[roads.geometry.name]].rename_geometry("geometry"),
                         metric_grid[["grid_id", "geometry"]], how="intersection",
                         keep_geom_type=False)
    lengths = pieces.assign(length_m=pieces.length).groupby("grid_id")["length_m"].sum()
    points = amenities.copy()
    points[points.geometry.name] = points.geometry.representative_point()
    joined = gpd.sjoin(points[[points.geometry.name]].rename_geometry("geometry"),
                       metric_grid[["grid_id", "geometry"]], predicate="within", how="left")
    counts = joined.groupby("grid_id").size()
    centroids = metric_grid[["grid_id", "geometry"]].copy()
    centroids["geometry"] = centroids.geometry.centroid
    nearest = gpd.sjoin_nearest(centroids, points[[points.geometry.name]].rename_geometry("geometry"),
                                how="left", distance_col="nearest_amenity_distance_m")
    distances = nearest.groupby("grid_id")["nearest_amenity_distance_m"].min()
    frame = pd.DataFrame({"grid_id": metric_grid["grid_id"], "epoch": int(year),
                          "aoi_fraction": metric_grid["aoi_fraction"].to_numpy()})
    frame["road_length_m"] = frame["grid_id"].map(lengths).fillna(0.0)
    frame["road_density_km_per_km2"] = (frame["road_length_m"]/1000)/(metric_grid["cell_area_m2"].to_numpy()/1e6)
    frame["amenity_count"] = frame["grid_id"].map(counts).fillna(0).astype("int64")
    frame["nearest_amenity_distance_m"] = frame["grid_id"].map(distances)
    return frame


def validate_context_frame(frame, config):
    expected = config["expected_cells"] * len(config["years"])
    if len(frame) != expected or frame[["grid_id", "epoch"]].duplicated().any():
        raise RuntimeError("Context table row count or uniqueness differs from contract")
    if set(frame["epoch"]) != set(config["years"]):
        raise RuntimeError("Context table epoch coverage differs from contract")
    numeric = ["aoi_fraction", "population_total", "population_density_per_km2", "road_length_m",
               "road_density_km_per_km2", "amenity_count", "nearest_amenity_distance_m"]
    if frame[numeric].isna().any().any() or not np.isfinite(frame[numeric]).all().all():
        raise RuntimeError("Context table contains missing/nonfinite metrics")
    if (frame[numeric] < 0).any().any():
        raise RuntimeError("Context table contains negative metrics")
    if (frame["aoi_fraction"] <= 0).any() or (frame["aoi_fraction"] > 1).any():
        raise RuntimeError("Context table AOI fractions are outside (0,1]")
    if any(frame.loc[frame.epoch == year, "grid_id"].nunique() != config["expected_cells"]
           for year in config["years"]):
        raise RuntimeError("Context table lost a grid cell")


def summarize(frame):
    fields = [name for name in frame.columns if name not in {"grid_id", "epoch"}]
    return {"rows": len(frame), "unique_cells": int(frame.grid_id.nunique()),
            "years": sorted(map(int, frame.epoch.unique())),
            "by_year": {str(year): {field: {"min": float(group[field].min()),
                                              "mean": float(group[field].mean()),
                                              "max": float(group[field].max())}
                                    for field in fields}
                        for year, group in frame.groupby("epoch")}}

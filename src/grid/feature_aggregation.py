"""Pure calculation primitives for guarded Part 4.2 feature aggregation."""
from __future__ import annotations

import numpy as np


def aggregate_labeled_values(values, labels, cell_count, *, nodata=None,
                             nominal_min=-1.0, nominal_max=1.0, tolerance=1e-6):
    """Aggregate one raster band where labels are 0 outside AOI and 1..N per cell."""
    values = np.asarray(values)
    labels = np.asarray(labels)
    if values.shape != labels.shape or cell_count <= 0:
        raise ValueError("Values/labels shape or cell count is invalid")
    flat_labels, flat_values = labels.ravel(), values.ravel()
    candidates = (flat_labels > 0) & (flat_labels <= cell_count)
    candidate_labels = flat_labels[candidates].astype("int64", copy=False)
    candidate_values = flat_values[candidates]
    aoi = np.bincount(candidate_labels, minlength=cell_count + 1)[1:]

    finite = np.isfinite(candidate_values)
    if nodata is not None and np.isfinite(nodata):
        finite &= candidate_values != nodata
    valid_labels = candidate_labels[finite]
    valid_values = candidate_values[finite].astype("float64", copy=False)
    input_valid = np.bincount(valid_labels, minlength=cell_count + 1)[1:]
    nodata_count = aoi - input_valid

    in_range = ((valid_values >= nominal_min - tolerance)
                & (valid_values <= nominal_max + tolerance))
    usable_labels, usable_values = valid_labels[in_range], valid_values[in_range]
    usable = np.bincount(usable_labels, minlength=cell_count + 1)[1:]
    excluded = input_valid - usable
    raw_sum = np.bincount(valid_labels, weights=valid_values,
                          minlength=cell_count + 1)[1:]
    filtered_sum = np.bincount(usable_labels, weights=usable_values,
                               minlength=cell_count + 1)[1:]

    raw_mean = np.full(cell_count, np.nan, dtype="float64")
    filtered_mean = np.full(cell_count, np.nan, dtype="float64")
    np.divide(raw_sum, input_valid, out=raw_mean, where=input_valid > 0)
    np.divide(filtered_sum, usable, out=filtered_mean, where=usable > 0)
    usable_fraction = np.zeros(cell_count, dtype="float64")
    exclusion_fraction = np.zeros(cell_count, dtype="float64")
    np.divide(usable, aoi, out=usable_fraction, where=aoi > 0)
    np.divide(excluded, input_valid, out=exclusion_fraction, where=input_valid > 0)
    return {
        "aoi_pixel_count": aoi,
        "input_valid_pixel_count": input_valid,
        "nodata_pixel_count": nodata_count,
        "out_of_range_excluded_pixel_count": excluded,
        "usable_pixel_count": usable,
        "usable_fraction_of_aoi_pixels": usable_fraction,
        "exclusion_fraction_of_input_valid_pixels": exclusion_fraction,
        "unfiltered_mean_diagnostic": raw_mean,
        "filtered_mean": filtered_mean,
    }


def validate_index_aggregation(result, *, expected_cells, candidate_total):
    required = {
        "aoi_pixel_count", "input_valid_pixel_count", "nodata_pixel_count",
        "out_of_range_excluded_pixel_count", "usable_pixel_count",
        "usable_fraction_of_aoi_pixels", "exclusion_fraction_of_input_valid_pixels",
        "unfiltered_mean_diagnostic", "filtered_mean",
    }
    if set(result) != required or any(len(value) != expected_cells for value in result.values()):
        raise RuntimeError("Index aggregation fields/cell count differ from contract")
    aoi, valid = result["aoi_pixel_count"], result["input_valid_pixel_count"]
    nodata, excluded = result["nodata_pixel_count"], result["out_of_range_excluded_pixel_count"]
    usable = result["usable_pixel_count"]
    if (int(aoi.sum()) != candidate_total or not np.array_equal(valid + nodata, aoi)
            or not np.array_equal(usable + excluded, valid)):
        raise RuntimeError("Index aggregation pixel counts do not reconcile")
    for field in ("usable_fraction_of_aoi_pixels", "exclusion_fraction_of_input_valid_pixels"):
        values = result[field]
        if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
            raise RuntimeError("Index aggregation fraction is outside [0,1]")


def slope_degrees(elevation, pixel_size_m, valid_mask=None):
    """Return Horn-style central-gradient slope in degrees for a metric DEM array."""
    elevation = np.asarray(elevation, dtype="float64")
    if elevation.ndim != 2 or min(elevation.shape) < 2 or pixel_size_m <= 0:
        raise ValueError("Elevation array/pixel size is invalid")
    dy, dx = np.gradient(elevation, pixel_size_m, pixel_size_m)
    slope = np.degrees(np.arctan(np.hypot(dx, dy)))
    if valid_mask is not None:
        valid_mask = np.asarray(valid_mask, dtype=bool)
        if valid_mask.shape != slope.shape:
            raise ValueError("Slope mask shape differs from elevation")
        slope[~valid_mask] = np.nan
    return slope


def aggregate_continuous(values, labels, cell_count, *, nodata=None):
    """Aggregate a continuous terrain field while preserving empty cells as NaN."""
    result = aggregate_labeled_values(
        values, labels, cell_count, nodata=nodata,
        nominal_min=-np.inf, nominal_max=np.inf, tolerance=0.0,
    )
    if int(result["out_of_range_excluded_pixel_count"].sum()) != 0:
        raise RuntimeError("Continuous aggregation unexpectedly excluded finite values")
    return {
        "aoi_pixel_count": result["aoi_pixel_count"],
        "valid_pixel_count": result["usable_pixel_count"],
        "nodata_pixel_count": result["nodata_pixel_count"],
        "valid_fraction": result["usable_fraction_of_aoi_pixels"],
        "mean": result["filtered_mean"],
    }


def validate_feature_frames(satellite, terrain, *, expected_cells, epochs, roles):
    """Fail closed before any provisional feature payload may be published."""
    expected_satellite_rows = expected_cells * len(epochs)
    if len(satellite) != expected_satellite_rows:
        raise RuntimeError("Satellite feature table row count differs from contract")
    if satellite[["grid_id", "epoch"]].duplicated().any():
        raise RuntimeError("Satellite feature table contains duplicate grid/year rows")
    if set(satellite["epoch"].unique()) != set(epochs):
        raise RuntimeError("Satellite feature table epoch set differs from contract")
    if any(satellite.loc[satellite["epoch"] == epoch, "grid_id"].nunique() != expected_cells
           for epoch in epochs):
        raise RuntimeError("Satellite feature table lost a grid cell")
    for role in roles:
        required = [f"{role}_{name}" for name in (
            "aoi_pixel_count", "input_valid_pixel_count", "nodata_pixel_count",
            "out_of_range_excluded_pixel_count", "usable_pixel_count",
            "usable_fraction_of_aoi_pixels", "exclusion_fraction_of_input_valid_pixels",
            "unfiltered_mean_diagnostic", "filtered_mean")]
        if any(column not in satellite for column in required):
            raise RuntimeError(f"Satellite table lacks required {role} diagnostics")
        if not np.array_equal(
                satellite[f"{role}_input_valid_pixel_count"] + satellite[f"{role}_nodata_pixel_count"],
                satellite[f"{role}_aoi_pixel_count"]):
            raise RuntimeError(f"Satellite {role} valid/nodata counts do not reconcile")
        if not np.array_equal(
                satellite[f"{role}_usable_pixel_count"] + satellite[f"{role}_out_of_range_excluded_pixel_count"],
                satellite[f"{role}_input_valid_pixel_count"]):
            raise RuntimeError(f"Satellite {role} usable/excluded counts do not reconcile")
    if (len(terrain) != expected_cells or terrain["grid_id"].nunique() != expected_cells
            or terrain["grid_id"].duplicated().any()):
        raise RuntimeError("Terrain feature table does not contain every grid cell exactly once")
    if set(terrain["grid_id"]) != set(satellite["grid_id"]):
        raise RuntimeError("Satellite and terrain grid identities differ")
    for field in ("elevation_mean_m", "slope_mean_degrees"):
        finite = terrain[field].dropna().to_numpy()
        if not np.isfinite(finite).all():
            raise RuntimeError(f"Terrain field {field} contains nonfinite stored values")

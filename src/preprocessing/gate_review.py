"""Native-resolution QC measurements and explicitly display-only previews."""
from __future__ import annotations

from contextlib import ExitStack
import heapq
import io
import math

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window

from src.preprocessing.indices import BAND_NAMES, INDEX_FORMULAS, compute_indices


def index_terms(values):
    blue, green, red, nir, swir, _ = values.astype("float64")
    return {"ndvi": (nir, red), "ndbi": (swir, nir), "ndwi": (green, nir),
            "mndwi": (green, swir), "bsi": (swir + red, nir + blue)}


def _merge(total, block):
    for name, values in block.items():
        if name not in total:
            total[name] = dict(values)
            continue
        for key, value in values.items():
            if key == "minimum":
                if value is not None:
                    total[name][key] = value if total[name][key] is None else min(total[name][key], value)
            elif key == "maximum":
                if value is not None:
                    total[name][key] = value if total[name][key] is None else max(total[name][key], value)
            else:
                total[name][key] += value


def _add_hits(target, mask, top, left, stride):
    rr, cc = np.nonzero(mask)
    np.add.at(target, ((rr + top) // stride, (cc + left) // stride), 1)


def review_epoch(paths, *, geometry, policy, config, expected_statistics=None):
    """Audit all native pixels; preserve originals and bounded extreme samples.

    Outlier maps count every flagged native pixel in each preview bin. They do
    not rely on averaged COG overviews, which could hide rare extreme pixels.
    Range-restricted means are diagnostics, not an approved exclusion policy.
    """
    names = tuple(INDEX_FORMULAS)
    if set(paths) != {"composite", "valid_obs_count", *names}:
        raise ValueError("QC requires composite, count and all five indices")
    from pyproj import Transformer
    with ExitStack() as stack:
        datasets = {name: stack.enter_context(rasterio.open(path)) for name, path in paths.items()}
        source, counts = datasets["composite"], datasets["valid_obs_count"]
        if (source.count != 6 or source.dtypes != ("float32",) * 6
                or source.nodata != policy.output_nodata or source.descriptions != BAND_NAMES):
            raise RuntimeError("Invalid QC composite schema/band order")
        for name, ds in datasets.items():
            if ds.crs != source.crs or ds.transform != source.transform or ds.shape != source.shape:
                raise RuntimeError(f"QC raster grid mismatch: {name}")
        if counts.count != 1 or counts.dtypes != ("uint8",) or counts.nodata != 255:
            raise RuntimeError("Invalid observation-count schema")
        for name in names:
            ds = datasets[name]
            if (ds.count != 1 or ds.dtypes != ("float32",) or ds.nodata != policy.output_nodata
                    or ds.descriptions != (name.upper(),)):
                raise RuntimeError(f"Invalid QC index schema: {name}")

        stride = max(1, math.ceil(max(source.shape) / config["preview_max_side"]))
        preview_shape = (math.ceil(source.height / stride), math.ceil(source.width / stride))
        hits = {name: np.zeros(preview_shape, dtype="uint32") for name in names}
        union_hits = np.zeros(preview_shape, dtype="uint32")
        statistics, diagnostics = {}, {}
        heaps = {name: [] for name in names}
        negatives = np.zeros(6, dtype="int64")
        aoi_pixels = valid_source_pixels = unique_outliers = 0
        histogram = np.zeros(9, dtype="int64")
        transformer = Transformer.from_crs(source.crs, "EPSG:4326", always_xy=True)
        chunk = config["chunk_size_pixels"]
        for top in range(0, source.height, chunk):
            for left in range(0, source.width, chunk):
                window = Window(left, top, min(chunk, source.width-left), min(chunk, source.height-top))
                values = source.read(window=window)
                count = counts.read(1, window=window)
                inside = geometry_mask([geometry], out_shape=count.shape,
                                       transform=source.window_transform(window), invert=True)
                aoi_pixels += int(inside.sum())
                if np.any(count[~inside] != 255) or np.any(count[inside] > 8):
                    raise RuntimeError("Observation counts violate AOI/classes")
                histogram += np.bincount(count[inside], minlength=9)
                source_valid = np.all(np.isfinite(values) & (values != source.nodata), axis=0)
                if not np.array_equal(source_valid, inside & (count >= config["minimum_valid_observations"])):
                    raise RuntimeError("Count/composite validity disagreement")
                valid_source_pixels += int(source_valid.sum())
                negatives += ((values < 0) & source_valid[None, :, :]).sum(axis=(1, 2))
                expected, block_stats = compute_indices(values, policy=policy, input_nodata=source.nodata)
                _merge(statistics, block_stats)
                terms = index_terms(values)
                union = np.zeros(count.shape, dtype=bool)
                for name in names:
                    actual = datasets[name].read(1, window=window)
                    if not np.array_equal(actual, expected[name]):
                        raise RuntimeError(f"Published index/native formula mismatch: {name}")
                    valid = actual != policy.output_nodata
                    flagged = valid & ((actual < policy.nominal_min-policy.range_tolerance)
                                       | (actual > policy.nominal_max+policy.range_tolerance))
                    union |= flagged
                    _add_hits(hits[name], flagged, top, left, stride)
                    d = diagnostics.setdefault(name, {"sum_all_valid": 0.0, "sum_nominal_only": 0.0,
                        "nominal_pixels": 0, "negative_term_outliers": 0, "negative_denominator_outliers": 0,
                        "absolute_denominators": [], "cancellation_ratios": []})
                    nominal = valid & ~flagged
                    d["sum_all_valid"] += float(actual[valid].sum(dtype="float64"))
                    d["sum_nominal_only"] += float(actual[nominal].sum(dtype="float64"))
                    d["nominal_pixels"] += int(nominal.sum())
                    aa, bb = terms[name]
                    den = aa + bb
                    scale = np.abs(aa) + np.abs(bb)
                    rr, cc = np.nonzero(flagged)
                    if expected_statistics and statistics[name]["out_of_range_pixels"] > expected_statistics[name]["out_of_range_pixels"]:
                        raise RuntimeError(f"Outlier count exceeds pinned prior QC: {name}")
                    if rr.size:
                        ratios = np.abs(den[flagged]) / scale[flagged]
                        d["absolute_denominators"].extend(np.abs(den[flagged]).tolist())
                        d["cancellation_ratios"].extend(ratios.tolist())
                        d["negative_term_outliers"] += int(((aa[flagged] < 0) | (bb[flagged] < 0)).sum())
                        d["negative_denominator_outliers"] += int((den[flagged] < 0).sum())
                        for r, c in zip(rr, cc):
                            row, col = int(r+top), int(c+left)
                            value = float(actual[r, c])
                            rank = (abs(value), -row, -col)
                            heap = heaps[name]
                            if len(heap) >= config["samples_per_index"] and rank <= heap[0][:3]:
                                continue
                            x, y = source.transform @ (col + 0.5, row + 0.5)
                            lon, lat = transformer.transform(x, y)
                            sample = {"index": name, "row": row, "col": col, "value": value,
                                "observations": int(count[r, c]), "easting_m": x, "northing_m": y,
                                "longitude": lon, "latitude": lat,
                                "left_term": float(aa[r, c]), "right_term": float(bb[r, c]),
                                "denominator": float(den[r, c]),
                                "cancellation_ratio": float(abs(den[r, c])/scale[r, c]),
                                "bands": {band: float(values[i, r, c]) for i, band in enumerate(BAND_NAMES)}}
                            entry = (*rank, sample)
                            if len(heap) < config["samples_per_index"]:
                                heapq.heappush(heap, entry)
                            else:
                                heapq.heapreplace(heap, entry)
                unique_outliers += int(union.sum())
                _add_hits(union_hits, union, top, left, stride)

        if aoi_pixels != config["expected_aoi_pixels"] or not aoi_pixels:
            raise RuntimeError("QC AOI pixel count differs from the approved boundary/grid")
        coverage = valid_source_pixels / aoi_pixels
        if coverage < config["minimum_aoi_coverage_fraction"]:
            raise RuntimeError("QC coverage falls below the approved gate")
        if expected_statistics:
            for name in names:
                for key, value in expected_statistics[name].items():
                    if statistics[name].get(key) != value:
                        raise RuntimeError(f"QC differs from pinned index statistics: {name}/{key}")
        for name, d in diagnostics.items():
            if not statistics[name]["valid_pixels"]:
                raise RuntimeError(f"QC index has no valid pixels: {name}")
            for key in ("absolute_denominators", "cancellation_ratios"):
                array = np.asarray(d.pop(key), dtype="float64")
                d[key] = {"minimum": float(array.min()), "median": float(np.median(array)),
                          "maximum": float(array.max())} if array.size else None
            d["mean_all_valid"] = d.pop("sum_all_valid") / statistics[name]["valid_pixels"]
            d["mean_nominal_only_diagnostic"] = (d.pop("sum_nominal_only") / d["nominal_pixels"]
                                                       if d["nominal_pixels"] else None)
        summary = {"aoi_pixels": aoi_pixels, "valid_composite_pixels": valid_source_pixels,
            "coverage_fraction": coverage, "observation_histogram": histogram.tolist(),
            "unique_outlier_pixels": unique_outliers,
            "negative_reflectance_pixels_by_band": dict(zip(BAND_NAMES, map(int, negatives))),
            "statistics": statistics, "diagnostics": diagnostics,
            "samples": [entry[3] for name in names for entry in sorted(heaps[name], reverse=True)],
            "sampling_rule": "up to configured count per index, largest absolute values; not representative",
            "native_formula_and_mask_checks": True, "prior_statistics_match": expected_statistics is not None}
        from rasterio.enums import Resampling
        previews = {"stride": stride, "hits": hits, "union_hits": union_hits,
                    "bounds": tuple(source.bounds), "crs": source.crs.to_string()}
        for name, ds in datasets.items():
            if name == "composite":
                previews[name] = ds.read([3, 2, 1], out_shape=(3, *preview_shape),
                                         masked=True, resampling=Resampling.nearest)
            else:
                previews[name] = ds.read(1, out_shape=preview_shape, masked=True,
                                         resampling=Resampling.nearest)
    return summary, previews


def render_epoch_png(epoch, summary, previews, *, geometry, config):
    """Return a compact review figure; color limits affect display only."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    left, bottom, right, top = previews["bounds"]
    extent = (left/1000, right/1000, bottom/1000, top/1000)
    fig, axes = plt.subplots(3, 3, figsize=(15, 13), constrained_layout=True)
    axes = axes.ravel()
    outlines = [geometry.boundary] if geometry.boundary.geom_type == "LineString" else list(geometry.boundary.geoms)
    for ax in axes[:8]:
        ax.set_facecolor("#e5e7eb")
        for outline in outlines:
            coords = np.asarray(outline.coords)
            ax.plot(coords[:, 0]/1000, coords[:, 1]/1000, color="#222222", linewidth=0.45)
        ax.set_xlim(extent[:2]); ax.set_ylim(extent[2:])
        ax.set_xlabel("Easting (km)", fontsize=8); ax.set_ylabel("Northing (km)", fontsize=8)
        ax.tick_params(labelsize=7)
    rgb = previews["composite"]
    rgb_data = np.moveaxis(rgb.filled(0), 0, -1)
    rgb_data = np.clip((rgb_data-config["rgb_display_min"]) /
                       (config["rgb_display_max"]-config["rgb_display_min"]), 0, 1)
    alpha = ~np.any(np.ma.getmaskarray(rgb), axis=0)
    axes[0].imshow(np.dstack([rgb_data, alpha]), extent=extent, origin="upper")
    axes[0].set_title("True colour RGB (display stretch only)", fontsize=10)
    image = axes[1].imshow(previews["valid_obs_count"], extent=extent, vmin=0, vmax=8,
                           cmap="viridis", origin="upper")
    fig.colorbar(image, ax=axes[1], shrink=.75, ticks=[0, 4, 8])
    axes[1].set_title("Clear-observation count (0–8)", fontsize=10)
    labels = {"ndvi": "vegetation signal", "ndbi": "built-surface signal",
              "ndwi": "water contrast", "mndwi": "modified water contrast", "bsi": "bare-soil signal"}
    for position, name in enumerate(INDEX_FORMULAS, start=2):
        image = axes[position].imshow(previews[name], extent=extent, origin="upper",
                                      vmin=-1, vmax=1, cmap="RdYlGn" if name == "ndvi" else "RdBu")
        fig.colorbar(image, ax=axes[position], shrink=.75, ticks=[-1, 0, 1])
        n = summary["statistics"][name]["out_of_range_pixels"]
        axes[position].set_title(f"{name.upper()} — {labels[name]}\nNative out-of-range pixels: {n:,}", fontsize=9)
    flagged = np.ma.masked_equal(previews["union_hits"], 0)
    if flagged.count():
        image = axes[7].imshow(flagged, extent=extent, origin="upper", cmap="magma",
                               norm=LogNorm(vmin=1, vmax=max(2, int(flagged.max()))))
        fig.colorbar(image, ax=axes[7], shrink=.75)
    axes[7].set_title("Outlier locations — native pixels per preview bin", fontsize=9)
    axes[8].axis("off")
    text = (f"YEAR {epoch} — REVIEW PENDING\n\n"
            f"AOI pixels: {summary['aoi_pixels']:,}\n"
            f"At least 4 observations: {summary['coverage_fraction']:.4%}\n"
            f"Unique outlier pixels: {summary['unique_outlier_pixels']:,}\n\n"
            "Indices are continuous signals, not land-cover labels.\n"
            "Index colour bars saturate outside [-1, 1] for display.\n"
            "All values remain unchanged in source files.\n"
            "Previews may use existing overviews.\n"
            "Counts, masks, formulas and flags are audited natively.\n"
            "No predictions or model accuracy are shown.\n\n"
            f"Grid: {previews['crs']}; axes in km.\n"
            "Black outline: verified buffered study boundary.\n"
            "Grey: no usable/displayed data; not zero reflectance.")
    axes[8].text(0, 1, text, va="top", fontsize=10, linespacing=1.5)
    fig.suptitle(f"Visakhapatnam — Phase 3 quality review — {epoch}", fontsize=16)
    output = io.BytesIO()
    fig.savefig(output, format="png", dpi=config["figure_dpi"])
    plt.close(fig)
    return output.getvalue()

"""Fetches the real GVMC boundary from OpenStreetMap (Nominatim), reprojects,
buffers, and validates it.

Never estimates or fabricates boundary geometry — per project rule, all
Visakhapatnam geographic data must come from a verified, checkable source.
`fetch_osm_boundary`'s HTTP call is injectable (`http_get`) so tests never
hit the live network; the real run uses the actual Nominatim API.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from shapely.geometry import shape
from shapely.validation import make_valid

from src.utils.io import load_config, resolve_path

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "vizag-geoai-research/0.1 (https://github.com/Sreecharan03/Vizag-population-gowth-pred)"

# OSM place types that plausibly represent a municipal administrative
# boundary — used to reject an unrelated match (e.g. a POI with a similar
# name) even though the query string already targets the right name.
_PLAUSIBLE_ADMIN_TYPES = {"local_authority", "administrative", "city", "municipality", "town"}


class BoundaryError(Exception):
    """Raised for any failure fetching, validating, or sanity-checking the boundary."""


HttpGet = Callable[..., Any]


def fetch_osm_boundary(query: str, *, http_get: HttpGet | None = None, timeout: float = 30.0) -> dict[str, Any]:
    """Query Nominatim for `query`; return the matched feature's geometry +
    identifying metadata. Raises BoundaryError if nothing matched, the
    match has no polygon, or it doesn't look like an administrative
    boundary.
    """
    http_get = http_get or requests.get
    params = {"q": query, "format": "geojson", "polygon_geojson": 1, "limit": 1}
    headers = {"User-Agent": USER_AGENT}

    try:
        resp = http_get(NOMINATIM_URL, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        raise BoundaryError(f"OpenStreetMap/Nominatim request failed: {e}") from e

    features = data.get("features", [])
    if not features:
        raise BoundaryError(f"OpenStreetMap/Nominatim returned no match for query: {query!r}")

    feature = features[0]
    geometry = feature.get("geometry")
    if geometry is None or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        got = geometry.get("type") if geometry else None
        raise BoundaryError(
            f"OpenStreetMap/Nominatim match for {query!r} has no polygon geometry (got: {got})"
        )

    props = feature.get("properties", {})
    place_type = props.get("type") or props.get("addresstype")
    category = props.get("category")
    if category != "boundary" or place_type not in _PLAUSIBLE_ADMIN_TYPES:
        raise BoundaryError(
            f"OpenStreetMap/Nominatim match for {query!r} doesn't look like an administrative "
            f"boundary (category={category!r}, type={place_type!r}) — refusing to use it as the "
            "study boundary without manual confirmation."
        )

    return {
        "geometry": geometry,
        "osm_type": props.get("osm_type"),
        "osm_id": props.get("osm_id"),
        "display_name": props.get("display_name"),
    }


def _as_validated_gdf(osm_result: dict[str, Any]) -> gpd.GeoDataFrame:
    geom = shape(osm_result["geometry"])
    if not geom.is_valid:
        geom = make_valid(geom)
    return gpd.GeoDataFrame(
        {
            "osm_type": [osm_result["osm_type"]],
            "osm_id": [osm_result["osm_id"]],
            "display_name": [osm_result["display_name"]],
        },
        geometry=[geom],
        crs="EPSG:4326",
    )


def reproject_and_buffer(
    gdf: gpd.GeoDataFrame, target_crs: str, buffer_distance_m: float
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    if buffer_distance_m <= 0:
        raise BoundaryError(f"buffer_distance_m must be > 0, got {buffer_distance_m}")

    reprojected = gdf.to_crs(target_crs)
    buffered = reprojected.copy()
    buffered["geometry"] = reprojected.geometry.buffer(buffer_distance_m)
    return reprojected, buffered


def check_area_sanity(gdf: gpd.GeoDataFrame, *, min_km2: float, max_km2: float) -> float:
    area_km2 = float(gdf.geometry.area.sum() / 1e6)
    if not (min_km2 <= area_km2 <= max_km2):
        raise BoundaryError(
            f"Boundary area {area_km2:.1f} km² is outside the sane range [{min_km2}, {max_km2}] "
            "km² — likely the wrong OSM entity was matched."
        )
    return area_km2


def cross_check_against_existing(
    local_gdf: gpd.GeoDataFrame, backend, key: str
) -> dict[str, Any] | None:
    """Downloads an existing boundary file from a backend (read-only) and
    compares it against the freshly-fetched OSM boundary — area, and
    intersection-over-union. Never treats the existing file as ground
    truth; just reports agreement/disagreement. Returns None if `key`
    doesn't exist on the backend.
    """
    if not backend.exists(key):
        return None

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "existing_boundary.geojson"
        backend.download(key, tmp_path)
        existing_gdf = gpd.read_file(tmp_path)

    if existing_gdf.crs is None:
        existing_gdf = existing_gdf.set_crs("EPSG:4326")
    existing_gdf = existing_gdf.to_crs(local_gdf.crs)

    local_union = local_gdf.geometry.union_all()
    existing_union = existing_gdf.geometry.union_all()

    intersection_area = local_union.intersection(existing_union).area
    union_area = local_union.union(existing_union).area
    iou = intersection_area / union_area if union_area else 0.0

    return {
        "existing_area_km2": existing_union.area / 1e6,
        "fetched_area_km2": local_union.area / 1e6,
        "iou": iou,
        "agrees": iou > 0.5,
    }


def plot_boundary_check(
    boundary_gdf: gpd.GeoDataFrame, buffered_gdf: gpd.GeoDataFrame, output_path: Path
) -> Path:
    """Saves a quick PNG of the buffered boundary over the unbuffered one —
    the Phase 1 Gate artifact the user visually confirms before Phase 2.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 8))
    buffered_gdf.plot(ax=ax, facecolor="none", edgecolor="tab:orange", linewidth=1.5, label="Buffered")
    boundary_gdf.plot(ax=ax, facecolor="tab:blue", edgecolor="tab:blue", alpha=0.4, label="GVMC boundary")
    ax.set_title("GVMC boundary + buffer (Phase 1 Gate check)")
    ax.set_xlabel(f"Easting ({boundary_gdf.crs})")
    ax.set_ylabel("Northing")
    ax.legend()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def build_gvmc_boundary(
    boundary_config: dict[str, Any] | None = None, *, http_get: HttpGet | None = None
) -> dict[str, Any]:
    """Orchestrates fetch -> validate -> reproject -> buffer -> sanity-check
    -> write. Writes configs/boundary.yaml's retrieval metadata is the
    caller's responsibility (kept here read-only w.r.t. that file so
    config-writing stays explicit).
    """
    config = boundary_config if boundary_config is not None else load_config("boundary")

    osm_result = fetch_osm_boundary(config["source"]["query"], http_get=http_get)
    gdf = _as_validated_gdf(osm_result)

    reprojected, buffered = reproject_and_buffer(gdf, config["crs"], config["buffer_distance_m"])
    area_km2 = check_area_sanity(
        reprojected,
        min_km2=config["sanity"]["min_area_km2"],
        max_km2=config["sanity"]["max_area_km2"],
    )

    boundaries_dir = resolve_path("data.boundaries")
    boundaries_dir.mkdir(parents=True, exist_ok=True)
    boundary_path = boundaries_dir / "gvmc_boundary.geojson"
    buffered_path = boundaries_dir / "gvmc_boundary_buffered.geojson"
    reprojected.to_file(boundary_path, driver="GeoJSON")
    buffered.to_file(buffered_path, driver="GeoJSON")

    return {
        "osm_type": osm_result["osm_type"],
        "osm_id": osm_result["osm_id"],
        "display_name": osm_result["display_name"],
        "area_km2": area_km2,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "boundary_path": boundary_path,
        "buffered_path": buffered_path,
        "boundary_gdf": reprojected,
        "buffered_gdf": buffered,
    }

"""OSM source: roads and amenities (hospitals, schools) within the buffered
study boundary, fetched live via the Overpass API through osmnx — never a
regional extract (keeps the fetch genuinely small and scoped to the AOI).
Used later by Phase 4's accessibility features (distance-to-road,
road density, distance-to-hospital, distance-to-school).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd

AMENITY_TAGS = {"amenity": ["hospital", "clinic", "school", "college", "university"]}


def fetch_osm_roads(buffered_gdf: gpd.GeoDataFrame):
    """Returns a GeoDataFrame of road edges within the buffered boundary."""
    import osmnx as ox

    polygon = buffered_gdf.to_crs("EPSG:4326").geometry.union_all()
    graph = ox.graph_from_polygon(polygon, network_type="drive", simplify=True)
    _, edges = ox.graph_to_gdfs(graph, nodes=True, edges=True)
    return edges


def fetch_osm_amenities(buffered_gdf: gpd.GeoDataFrame, tags: dict[str, Any] | None = None):
    """Returns a GeoDataFrame of amenity points/polygons (hospitals,
    schools, etc.) within the buffered boundary.
    """
    import osmnx as ox

    polygon = buffered_gdf.to_crs("EPSG:4326").geometry.union_all()
    return ox.features_from_polygon(polygon, tags=tags or AMENITY_TAGS)


def fetch_osm_data(buffered_gdf: gpd.GeoDataFrame, dest_dir: Path) -> dict[str, Path]:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    roads = fetch_osm_roads(buffered_gdf)
    roads_path = dest_dir / "roads.gpkg"
    # GeoPackage can't store list/dict-typed columns OSM sometimes returns.
    roads_clean = roads.copy()
    for col in roads_clean.columns:
        if roads_clean[col].apply(lambda v: isinstance(v, (list, dict))).any():
            roads_clean[col] = roads_clean[col].astype(str)
    roads_clean.to_file(roads_path, driver="GPKG")

    amenities = fetch_osm_amenities(buffered_gdf)
    amenities_path = dest_dir / "amenities.gpkg"
    amenities_clean = amenities.copy()
    for col in amenities_clean.columns:
        if amenities_clean[col].apply(lambda v: isinstance(v, (list, dict))).any():
            amenities_clean[col] = amenities_clean[col].astype(str)
    amenities_clean.to_file(amenities_path, driver="GPKG")

    return {"roads": roads_path, "amenities": amenities_path}


def verify_osm_file(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        return {"status": "FAILED", "reason": "file missing or empty"}

    try:
        gdf = gpd.read_file(path)
        if len(gdf) == 0:
            return {"status": "FAILED", "reason": "no features"}
        if not gdf.geometry.is_valid.all():
            return {"status": "FAILED", "reason": "contains invalid geometries"}
        return {"status": "OK", "feature_count": len(gdf), "size_bytes": path.stat().st_size}
    except Exception as e:
        return {"status": "FAILED", "reason": f"could not open as vector file: {e}"}

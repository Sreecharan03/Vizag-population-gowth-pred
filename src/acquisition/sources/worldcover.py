"""WorldCover source: ESA WorldCover 10 m land cover (v200, 2021), public
AWS Open Data bucket, no credentials needed.

https://registry.opendata.aws/esa-worldcover-vito/
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import geopandas as gpd

BUCKET = "esa-worldcover"
REGION = "eu-central-1"
VERSION = "v200"
YEAR = "2021"
TILE_SIZE_DEG = 3


def _unsigned_s3_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name=REGION)


def required_worldcover_tiles(buffered_gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Returns the 3-degree WorldCover tiles overlapping the buffered
    boundary's bounding box — computed from the real geometry.
    """
    wgs84 = buffered_gdf.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = wgs84.total_bounds

    def _tile_origin(value: float) -> int:
        return math.floor(value / TILE_SIZE_DEG) * TILE_SIZE_DEG

    lat_origins = sorted({_tile_origin(miny), _tile_origin(maxy)})
    lon_origins = sorted({_tile_origin(minx), _tile_origin(maxx)})

    tiles = []
    for lat in lat_origins:
        for lon in lon_origins:
            ns = f"N{lat:02d}" if lat >= 0 else f"S{abs(lat):02d}"
            ew = f"E{lon:03d}" if lon >= 0 else f"W{abs(lon):03d}"
            tile_id = f"{ns}{ew}"
            filename = f"ESA_WorldCover_10m_{YEAR}_{VERSION}_{tile_id}_Map.tif"
            tiles.append({"tile_id": tile_id, "key": f"{VERSION}/{YEAR}/map/{filename}", "filename": filename})
    return tiles


def estimate_worldcover_sizes(tiles: list[dict[str, Any]]) -> dict[str, int]:
    client = _unsigned_s3_client()
    sizes = {}
    for tile in tiles:
        resp = client.head_object(Bucket=BUCKET, Key=tile["key"])
        sizes[tile["tile_id"]] = resp["ContentLength"]
    return sizes


def fetch_worldcover_tiles(tiles: list[dict[str, Any]], dest_dir: Path) -> list[Path]:
    client = _unsigned_s3_client()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for tile in tiles:
        dest = dest_dir / tile["filename"]
        client.download_file(BUCKET, tile["key"], str(dest))
        paths.append(dest)
    return paths


def verify_worldcover_file(path: Path) -> dict[str, Any]:
    import rasterio

    path = Path(path)
    if not path.is_file() or path.stat().st_size < 1024:
        return {"status": "FAILED", "reason": "file missing or implausibly small"}

    try:
        with rasterio.open(path) as src:
            if src.crs is None:
                return {"status": "FAILED", "reason": "no CRS"}
            if src.count < 1:
                return {"status": "FAILED", "reason": "no raster bands"}
            return {
                "status": "OK",
                "crs": str(src.crs),
                "shape": (src.height, src.width),
                "size_bytes": path.stat().st_size,
            }
    except Exception as e:
        return {"status": "FAILED", "reason": f"could not open as raster: {e}"}

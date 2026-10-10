"""DEM source: Copernicus GLO-30 (30 m global DEM), public AWS Open Data
bucket, no credentials needed. Verified, documented source — never a
fabricated or guessed elevation value.

https://registry.opendata.aws/copernicus-dem/
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import geopandas as gpd

BUCKET = "copernicus-dem-30m"
REGION = "eu-central-1"


def _unsigned_s3_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client("s3", config=Config(signature_version=UNSIGNED), region_name=REGION)


def required_dem_tiles(buffered_gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Returns the 1-degree Copernicus DEM tiles overlapping the buffered
    boundary's bounding box — computed from the real geometry, not assumed.
    """
    wgs84 = buffered_gdf.to_crs("EPSG:4326")
    minx, miny, maxx, maxy = wgs84.total_bounds

    tiles = []
    for lat in range(math.floor(miny), math.floor(maxy) + 1):
        for lon in range(math.floor(minx), math.floor(maxx) + 1):
            ns = f"N{lat:02d}" if lat >= 0 else f"S{abs(lat):02d}"
            ew = f"E{lon:03d}" if lon >= 0 else f"W{abs(lon):03d}"
            tile_name = f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"
            tiles.append(
                {
                    "tile_id": f"{ns}_00_{ew}_00",
                    "key": f"{tile_name}/{tile_name}.tif",
                    "filename": f"{tile_name}.tif",
                }
            )
    return tiles


def estimate_dem_sizes(tiles: list[dict[str, Any]]) -> dict[str, int]:
    """Returns {tile_id: size_bytes} via head_object — no download."""
    client = _unsigned_s3_client()
    sizes = {}
    for tile in tiles:
        resp = client.head_object(Bucket=BUCKET, Key=tile["key"])
        sizes[tile["tile_id"]] = resp["ContentLength"]
    return sizes


def fetch_dem_tiles(tiles: list[dict[str, Any]], dest_dir: Path) -> list[Path]:
    """Downloads each tile's DEM GeoTIFF (only the DEM, not the auxiliary
    quality-mask/preview files) to dest_dir. Returns the local paths.
    """
    client = _unsigned_s3_client()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for tile in tiles:
        dest = dest_dir / tile["filename"]
        client.download_file(BUCKET, tile["key"], str(dest))
        paths.append(dest)
    return paths


def verify_dem_file(path: Path) -> dict[str, Any]:
    """Cheap verification: file exists, non-trivial size, opens as a valid
    single-band GeoTIFF with a real CRS — never trusts a download blindly.
    """
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

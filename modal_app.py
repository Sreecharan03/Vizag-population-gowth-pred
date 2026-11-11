"""Modal compute entrypoints for Vizag GeoAI.

The local process is control-plane only. Decorated functions execute in Modal,
and persistent project artifacts belong in Backblaze B2.
"""

from __future__ import annotations

import modal

APP_NAME = "vizag-geoai"
B2_SECRET_NAME = "vizag-b2"

REMOTE_DEPENDENCIES = (
    "numpy>=2.0,<3.0", "pandas>=2.3,<3.0", "geopandas>=1.2,<2.0",
    "shapely>=2.2,<3.0", "pyproj>=3.8,<4.0", "rasterio>=1.5,<2.0",
    "rioxarray>=0.23,<1.0", "xarray>=2026.1,<2027.0",
    "scikit-learn>=1.9,<2.0", "xgboost>=2.1,<3.0",
    "lightgbm>=4.7,<5.0", "shap>=0.53,<1.0",
    "osmnx>=2.1,<3.0", "pysal>=26.0,<27.0",
    "matplotlib>=3.11,<4.0",
    "dask>=2026.1,<2027.0", "pyarrow>=26.0,<27.0",
    "rio-cogeo>=7.0,<8.0", "boto3>=1.43,<2.0",
    "python-dotenv>=1.0,<2.0", "mgrs>=1.5,<2.0",
    "pytest>=8.0,<9.0", "pyyaml>=6.0,<7.0",
)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install(*REMOTE_DEPENDENCIES)
    .add_local_dir("src", remote_path="/root/vizag/src", copy=True)
    .add_local_dir("tests", remote_path="/root/vizag/tests", copy=True)
    .add_local_dir("configs", remote_path="/root/vizag/configs", copy=True)
    .add_local_file("pyproject.toml", remote_path="/root/vizag/pyproject.toml", copy=True)
    .env({"PYTHONPATH": "/root/vizag"})
)

app = modal.App(APP_NAME, image=image)
b2_secret = modal.Secret.from_name(
    B2_SECRET_NAME,
    environment_name="main",
    required_keys=["B2_KEY_ID", "B2_APPLICATION_KEY"],
)
manifest_recovery_checkpoints = modal.Dict.from_name(
    "vizag-phase3-manifest-recovery-3-3-2", create_if_missing=True
)


@app.function(secrets=[b2_secret], timeout=300)
def verify_remote_environment() -> dict[str, str | bool]:
    """Verify imports and secret presence without reading or writing B2."""
    import os
    import platform
    import boto3
    import geopandas
    import rasterio

    result = {
        "python": platform.python_version(),
        "boto3": boto3.__version__,
        "geopandas": geopandas.__version__,
        "rasterio": rasterio.__version__,
        "b2_credentials_present": bool(
            os.environ.get("B2_KEY_ID") and os.environ.get("B2_APPLICATION_KEY")
        ),
        "modal_remote": os.environ.get("MODAL_IS_REMOTE") == "1",
    }
    print(result)
    return result


@app.function(timeout=1800)
def run_regression_tests() -> int:
    """Run the repository test suite remotely inside the Modal image."""
    import os
    import pytest

    os.chdir("/root/vizag")
    exit_code = pytest.main(["tests", "-q"])
    if exit_code != 0:
        raise RuntimeError(f"Remote regression suite failed with exit code {exit_code}")
    return exit_code


@app.function(secrets=[b2_secret], timeout=600)
def run_phase3_part1(dry_run: bool = True) -> dict:
    """Build the scene catalogue from B2 and optionally write two new objects.

    The write path refuses to overwrite either destination. No pixel object is
    opened; only the Phase 2 inventory manifest is read.
    """
    import os

    import boto3
    from botocore.exceptions import ClientError

    from src.preprocessing.catalogue import (
        assess_epoch_feasibility,
        build_scene_catalogue,
        catalogue_jsonl,
        generate_feasibility_report,
        load_inventory_jsonl,
    )
    from src.utils.io import load_config

    b2_config = load_config("b2")
    compute_config = load_config("compute")
    temporal_config = load_config("temporal")
    requirements_config = load_config("data_requirements")

    bucket = b2_config["bucket"]
    inventory_key = f"{b2_config['prefixes']['manifests_backup']}b2_inventory.jsonl"
    output_prefixes = compute_config["b2_output_prefixes"]
    catalogue_key = f"{output_prefixes['manifests']}scene_catalogue.jsonl"
    report_key = f"{output_prefixes['results']}epoch_feasibility.md"

    client = boto3.client(
        "s3",
        endpoint_url=b2_config["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    )
    inventory_body = client.get_object(Bucket=bucket, Key=inventory_key)["Body"].read()
    inventory = load_inventory_jsonl(inventory_body)
    required_tiles = requirements_config["sentinel2"]["required_tiles"]
    epochs = temporal_config["epochs"]
    scenes = build_scene_catalogue(inventory, required_tiles=required_tiles)
    summaries = assess_epoch_feasibility(scenes, epochs=epochs, required_tiles=required_tiles)
    catalogue_content = catalogue_jsonl(scenes).encode("utf-8")
    report_content = generate_feasibility_report(summaries).encode("utf-8")

    result = {
        "dry_run": dry_run,
        "source": {"key": inventory_key, "bytes": len(inventory_body)},
        "destinations": [
            {"key": catalogue_key, "bytes": len(catalogue_content)},
            {"key": report_key, "bytes": len(report_content)},
        ],
        "scene_records": len(scenes),
        "epoch_summaries": summaries,
    }
    if dry_run:
        print(result)
        return result

    for key in (catalogue_key, report_key):
        try:
            client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            raise FileExistsError(f"Refusing to overwrite existing B2 object: {key}")

    client.put_object(Bucket=bucket, Key=catalogue_key, Body=catalogue_content, ContentType="application/x-ndjson")
    client.put_object(Bucket=bucket, Key=report_key, Body=report_content, ContentType="text/markdown")
    verified_sizes = {
        catalogue_key: client.head_object(Bucket=bucket, Key=catalogue_key)["ContentLength"],
        report_key: client.head_object(Bucket=bucket, Key=report_key)["ContentLength"],
    }
    expected_sizes = {catalogue_key: len(catalogue_content), report_key: len(report_content)}
    if verified_sizes != expected_sizes:
        raise RuntimeError(f"B2 post-write size verification failed: {verified_sizes} != {expected_sizes}")
    result["written"] = True
    result["verified_sizes"] = verified_sizes
    print(result)
    return result


@app.function(secrets=[b2_secret], timeout=7200, cpu=4.0, memory=8192)
def run_phase3_part2() -> dict:
    """Run complete real SCL triage and write two non-overwriting B2 outputs."""
    import io
    import json
    import os

    import boto3
    import geopandas as gpd
    import rasterio
    from botocore.exceptions import ClientError
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds

    from src.preprocessing.catalogue import SceneRecord
    from src.preprocessing.read_strategy import (
        build_vsizip_vsis3_path,
        find_band_inner_paths,
        vsis3_credentials,
    )
    from src.preprocessing.triage import cloud_triage_csv, selected_scenes_jsonl, triage_scenes
    from src.storage.backends import B2Backend
    from src.utils.io import load_config

    b2_config = load_config("b2")
    compute_config = load_config("compute")
    temporal_config = load_config("temporal")
    preprocessing_config = load_config("preprocessing")["triage"]
    bucket = b2_config["bucket"]
    key_id = os.environ["B2_KEY_ID"]
    application_key = os.environ["B2_APPLICATION_KEY"]
    endpoint = b2_config["endpoint_url"]

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=application_key,
    )
    backend = B2Backend(endpoint, bucket, key_id=key_id, application_key=application_key, client=client)

    output_prefixes = compute_config["b2_output_prefixes"]
    catalogue_key = f"{output_prefixes['manifests']}scene_catalogue.jsonl"
    boundary_key = "vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson"
    selected_key = f"{output_prefixes['manifests']}selected_scenes.jsonl"
    triage_key = f"{output_prefixes['results']}cloud_triage.csv"

    for key in (selected_key, triage_key):
        try:
            client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            raise FileExistsError(f"Refusing to overwrite existing B2 object: {key}")

    catalogue_body = client.get_object(Bucket=bucket, Key=catalogue_key)["Body"].read()
    scenes = [SceneRecord(**json.loads(line)) for line in catalogue_body.decode("utf-8").splitlines() if line]
    boundary_body = client.get_object(Bucket=bucket, Key=boundary_key)["Body"].read()
    boundary = gpd.read_file(io.BytesIO(boundary_body))

    def read_scl(scene: SceneRecord):
        info = backend.stat(scene.object_key)
        scl_path = find_band_inner_paths(backend, scene.object_key, info.size_bytes).get("SCL")
        if not scl_path:
            raise FileNotFoundError(f"SCL band missing from archive: {scene.object_key}")
        vsi_path = build_vsizip_vsis3_path(bucket, scene.object_key, scl_path)
        with vsis3_credentials(key_id, application_key, endpoint):
            with rasterio.open(vsi_path) as src:
                projected = boundary.to_crs(src.crs)
                raw_window = from_bounds(*projected.total_bounds, transform=src.transform)
                window = raw_window.round_offsets().round_lengths().intersection(
                    Window(0, 0, src.width, src.height)
                )
                data = src.read(1, window=window)
                mask = geometry_mask(
                    projected.geometry,
                    out_shape=data.shape,
                    transform=src.window_transform(window),
                    invert=True,
                )
        return data, mask

    classes = preprocessing_config["scl_classes"]
    records = triage_scenes(
        scenes,
        read_scl=read_scl,
        top_k_per_epoch=preprocessing_config["top_k_per_epoch"],
        start_month_day=temporal_config["dry_season_window"]["start_month_day"],
        end_month_day=temporal_config["dry_season_window"]["end_month_day"],
        nodata_classes=classes["nodata_or_defective"],
        shadow_classes=classes["shadow"],
        cloud_classes=classes["cloud_or_snow"],
    )
    selected_content = selected_scenes_jsonl(records).encode("utf-8")
    triage_content = cloud_triage_csv(records).encode("utf-8")
    client.put_object(Bucket=bucket, Key=selected_key, Body=selected_content, ContentType="application/x-ndjson")
    client.put_object(Bucket=bucket, Key=triage_key, Body=triage_content, ContentType="text/csv")

    expected = {selected_key: len(selected_content), triage_key: len(triage_content)}
    verified = {key: client.head_object(Bucket=bucket, Key=key)["ContentLength"] for key in expected}
    if verified != expected:
        raise RuntimeError(f"B2 post-write size verification failed: {verified} != {expected}")
    summary = {
        "triaged_scenes": len(records),
        "selected_scenes": sum(record.selected for record in records),
        "selected_by_epoch": {
            epoch: sum(record.selected and record.epoch == epoch for record in records)
            for epoch in temporal_config["epochs"]
        },
        "verified_sizes": verified,
    }
    print(summary)
    return summary


@app.function(secrets=[b2_secret], timeout=300)
def review_phase3_part2() -> dict:
    """Read the selected-scene manifest and summarize its quality for review."""
    import json
    import os
    from collections import defaultdict
    from statistics import mean

    import boto3

    from src.utils.io import load_config

    b2_config = load_config("b2")
    compute_config = load_config("compute")
    key = f"{compute_config['b2_output_prefixes']['manifests']}selected_scenes.jsonl"
    client = boto3.client(
        "s3",
        endpoint_url=b2_config["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    )
    body = client.get_object(Bucket=b2_config["bucket"], Key=key)["Body"].read()
    records = [json.loads(line) for line in body.decode("utf-8").splitlines() if line]
    grouped = defaultdict(list)
    for record in records:
        grouped[int(record["epoch"])].append(record)

    epochs = {}
    for epoch, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: row["selection_rank"])
        epochs[epoch] = {
            "count": len(ordered),
            "dates": [row["sensing_date"][:8] for row in ordered],
            "mean_cloud_pct": round(mean(row["cloud_fraction"] for row in ordered) * 100, 3),
            "max_cloud_pct": round(max(row["cloud_fraction"] for row in ordered) * 100, 3),
            "mean_shadow_pct": round(mean(row["shadow_fraction"] for row in ordered) * 100, 3),
            "mean_nodata_pct": round(mean(row["nodata_fraction"] for row in ordered) * 100, 3),
            "mean_usable_pct": round(mean(row["usable_fraction"] for row in ordered) * 100, 3),
        }
    result = {"source_key": key, "bytes_read": len(body), "epochs": epochs}
    print(result)
    return result


@app.function(secrets=[b2_secret], timeout=3600)
def probe_phase3_part3_metadata(all_scenes: bool = False) -> dict:
    """Probe approved real scenes' XML and raster headers only.

    This is the Part 3.3.1 verification gate. It performs no pixel extraction
    and writes no B2 object.
    """
    import io
    import json
    import os
    import zipfile

    import boto3
    import rasterio

    from src.preprocessing.radiometry import parse_l2a_radiometry_metadata
    from src.preprocessing.read_strategy import (
        REQUIRED_BAND_CODES,
        build_vsizip_vsis3_path,
        find_band_inner_paths,
        vsis3_credentials,
    )
    from src.storage.backends import B2Backend, RangeReadFile
    from src.utils.io import load_config

    b2_config = load_config("b2")
    compute_config = load_config("compute")
    bucket = b2_config["bucket"]
    endpoint = b2_config["endpoint_url"]
    key_id = os.environ["B2_KEY_ID"]
    application_key = os.environ["B2_APPLICATION_KEY"]
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key_id,
        aws_secret_access_key=application_key,
    )
    backend = B2Backend(endpoint, bucket, key_id=key_id, application_key=application_key, client=client)

    selected_key = f"{compute_config['b2_output_prefixes']['manifests']}selected_scenes.jsonl"
    selected_body = client.get_object(Bucket=bucket, Key=selected_key)["Body"].read()
    records = [json.loads(line) for line in selected_body.decode("utf-8").splitlines() if line]
    approved = [row for row in records if row.get("selected", True)]
    if not approved:
        raise RuntimeError("No approved scene exists in selected_scenes.jsonl")
    ordered = sorted(approved, key=lambda row: (int(row["epoch"]), int(row.get("selection_rank", 0))))
    targets = ordered if all_scenes else ordered[:1]
    object_keys = [row["object_key"] for row in targets]
    if len(object_keys) != len(set(object_keys)):
        raise RuntimeError("Selected-scene manifest contains duplicate object keys")

    expected_origin = (699960.0, 2000040.0)
    required_reflectance = {"B02", "B03", "B04", "B08", "B11", "B12"}
    scene_results = []
    for scene in targets:
        object_key = scene["object_key"]
        info = backend.stat(object_key)
        remote_file = RangeReadFile(backend, object_key, info.size_bytes)
        with zipfile.ZipFile(remote_file) as archive:
            metadata_paths = [name for name in archive.namelist() if name.endswith("/MTD_MSIL2A.xml")]
            if len(metadata_paths) != 1:
                raise RuntimeError(f"{object_key}: expected one MTD_MSIL2A.xml, found {len(metadata_paths)}")
            metadata_path = metadata_paths[0]
            metadata_xml = archive.read(metadata_path)
        radiometry = parse_l2a_radiometry_metadata(metadata_xml)

        physical_ids = {physical: band_id for band_id, physical in radiometry.physical_band_by_id.items()}
        missing_metadata_bands = sorted(required_reflectance - set(physical_ids))
        if missing_metadata_bands:
            raise RuntimeError(f"{object_key}: metadata mapping missing {missing_metadata_bands}")
        baseline_number = float(radiometry.processing_baseline)
        if baseline_number >= 4.0:
            missing_offsets = sorted(
                band for band in required_reflectance if physical_ids[band] not in radiometry.offsets_by_band_id
            )
            if missing_offsets:
                raise RuntimeError(f"{object_key}: offset-era product missing offsets for {missing_offsets}")

        inner_paths = find_band_inner_paths(backend, object_key, info.size_bytes)
        missing = sorted(set(REQUIRED_BAND_CODES) - set(inner_paths))
        if missing:
            raise RuntimeError(f"{object_key}: required bands missing: {missing}")

        headers = {}
        with vsis3_credentials(key_id, application_key, endpoint):
            for band in REQUIRED_BAND_CODES:
                vsi_path = build_vsizip_vsis3_path(bucket, object_key, inner_paths[band])
                with rasterio.open(vsi_path) as src:
                    crs = src.crs.to_string() if src.crs else None
                    transform = list(src.transform)[:6]
                    resolution = [abs(src.transform.a), abs(src.transform.e)]
                    expected_resolution = [10.0, 10.0] if band in {"B02", "B03", "B04", "B08"} else [20.0, 20.0]
                    if crs != "EPSG:32644":
                        raise RuntimeError(f"{object_key}/{band}: unexpected CRS {crs}")
                    if resolution != expected_resolution:
                        raise RuntimeError(f"{object_key}/{band}: resolution {resolution} != {expected_resolution}")
                    if (transform[2], transform[5]) != expected_origin:
                        raise RuntimeError(
                            f"{object_key}/{band}: origin {(transform[2], transform[5])} != {expected_origin}"
                        )
                    headers[band] = {
                        "crs": crs,
                        "transform": transform,
                        "width": src.width,
                        "height": src.height,
                        "resolution": resolution,
                        "dtype": src.dtypes[0],
                        "nodata": src.nodata,
                    }

        scene_results.append({
            "epoch": int(scene["epoch"]),
            "scene_id": scene.get("scene_id") or scene.get("product_id"),
            "object_key": object_key,
            "object_size_bytes": info.size_bytes,
            "etag": info.etag,
            "metadata_inner_path": metadata_path,
            "metadata_bytes": len(metadata_xml),
            "radiometry": radiometry.as_dict(),
            "band_headers": headers,
        })

    baselines = {}
    epochs = {}
    header_nodata_values = set()
    for row in scene_results:
        baseline = row["radiometry"]["processing_baseline"]
        baselines[baseline] = baselines.get(baseline, 0) + 1
        epoch = str(row["epoch"])
        epochs[epoch] = epochs.get(epoch, 0) + 1
        header_nodata_values.update(header["nodata"] for header in row["band_headers"].values())
    result = {
        "read_only": True,
        "scope": "all-approved-scenes" if all_scenes else "one-approved-scene",
        "scene_count": len(scene_results),
        "epoch_counts": epochs,
        "processing_baseline_counts": baselines,
        "header_nodata_values": sorted(header_nodata_values, key=lambda value: str(value)),
        "scenes": scene_results,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


@app.function(secrets=[b2_secret], timeout=7200, cpu=4.0, memory=8192)
def validate_phase3_part3_nodata(epoch: int | None = None) -> dict:
    """Measure DN=0 versus SCL=0 over all approved scenes, read-only."""
    import io
    import json
    import os
    from collections import defaultdict

    import boto3
    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.features import geometry_mask
    from rasterio.warp import reproject
    from rasterio.windows import Window, from_bounds

    from src.preprocessing.nodata import compare_dn_zero_to_scl_zero
    from src.preprocessing.read_strategy import (
        build_vsizip_vsis3_path,
        find_band_inner_paths,
        vsis3_credentials,
    )
    from src.storage.backends import B2Backend
    from src.utils.io import load_config

    b2_config = load_config("b2")
    compute_config = load_config("compute")
    bucket = b2_config["bucket"]
    endpoint = b2_config["endpoint_url"]
    key_id = os.environ["B2_KEY_ID"]
    application_key = os.environ["B2_APPLICATION_KEY"]
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=key_id, aws_secret_access_key=application_key,
    )
    backend = B2Backend(endpoint, bucket, key_id=key_id, application_key=application_key, client=client)
    prefixes = compute_config["b2_output_prefixes"]
    selected_key = f"{prefixes['manifests']}selected_scenes.jsonl"
    boundary_key = "vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson"
    selected_body = client.get_object(Bucket=bucket, Key=selected_key)["Body"].read()
    rows = [json.loads(line) for line in selected_body.decode("utf-8").splitlines() if line]
    rows = sorted((row for row in rows if row.get("selected", True)), key=lambda row: (row["epoch"], row["selection_rank"]))
    if len(rows) != 32:
        raise RuntimeError(f"Expected 32 approved scenes, found {len(rows)}")
    if epoch is not None:
        rows = [row for row in rows if int(row["epoch"]) == epoch]
        if len(rows) != 8:
            raise RuntimeError(f"Expected 8 approved scenes for epoch {epoch}, found {len(rows)}")
    boundary_body = client.get_object(Bucket=bucket, Key=boundary_key)["Body"].read()
    boundary = gpd.read_file(io.BytesIO(boundary_body))
    bands = ("B02", "B03", "B04", "B08", "B11", "B12")
    scene_results = []

    for index, scene in enumerate(rows, start=1):
        object_key = scene["object_key"]
        info = backend.stat(object_key)
        paths = find_band_inner_paths(backend, object_key, info.size_bytes)
        missing = sorted(set((*bands, "SCL")) - set(paths))
        if missing:
            raise RuntimeError(f"{object_key}: missing required assets {missing}")

        with vsis3_credentials(key_id, application_key, endpoint):
            scl_vsi = build_vsizip_vsis3_path(bucket, object_key, paths["SCL"])
            with rasterio.open(scl_vsi) as scl_src:
                projected = boundary.to_crs(scl_src.crs)
                scl_window = from_bounds(*projected.total_bounds, transform=scl_src.transform)
                scl_window = scl_window.round_offsets().round_lengths().intersection(
                    Window(0, 0, scl_src.width, scl_src.height)
                )
                scl = scl_src.read(1, window=scl_window)
                scl_transform = scl_src.window_transform(scl_window)
                scl_crs = scl_src.crs

            band_results = {}
            for band in bands:
                band_vsi = build_vsizip_vsis3_path(bucket, object_key, paths[band])
                with rasterio.open(band_vsi) as band_src:
                    projected = boundary.to_crs(band_src.crs)
                    band_window = from_bounds(*projected.total_bounds, transform=band_src.transform)
                    band_window = band_window.round_offsets().round_lengths().intersection(
                        Window(0, 0, band_src.width, band_src.height)
                    )
                    dn = band_src.read(1, window=band_window)
                    band_transform = band_src.window_transform(band_window)
                    inside = geometry_mask(
                        projected.geometry,
                        out_shape=dn.shape,
                        transform=band_transform,
                        invert=True,
                    )
                    scl_on_band_grid = np.zeros(dn.shape, dtype="uint8")
                    reproject(
                        source=scl,
                        destination=scl_on_band_grid,
                        src_transform=scl_transform,
                        src_crs=scl_crs,
                        dst_transform=band_transform,
                        dst_crs=band_src.crs,
                        src_nodata=None,
                        dst_nodata=0,
                        resampling=Resampling.nearest,
                    )
                    band_results[band] = compare_dn_zero_to_scl_zero(dn, scl_on_band_grid, inside)

        scene_result = {
            "epoch": int(scene["epoch"]),
            "scene_id": scene.get("scene_id") or scene.get("product_id"),
            "object_key": object_key,
            "bands": band_results,
        }
        scene_results.append(scene_result)
        print(json.dumps({"progress": f"{index}/{len(rows)}", "scene_id": scene_result["scene_id"]}))

    aggregate = defaultdict(lambda: defaultdict(int))
    for scene in scene_results:
        for band, values in scene["bands"].items():
            key = f"{scene['epoch']}:{band}"
            for metric in (
                "inside_pixels", "dn_zero_pixels", "scl_zero_pixels", "both_zero_pixels",
                "dn_zero_scl_valid_pixels", "scl_zero_dn_nonzero_pixels", "mismatch_pixels",
            ):
                aggregate[key][metric] += int(values[metric])
    aggregate_result = {}
    for key, values in sorted(aggregate.items()):
        union = values["both_zero_pixels"] + values["dn_zero_scl_valid_pixels"] + values["scl_zero_dn_nonzero_pixels"]
        aggregate_result[key] = {
            **dict(values),
            "mismatch_fraction_of_union": values["mismatch_pixels"] / union if union else 0.0,
        }
    result = {
        "read_only": True,
        "epoch_scope": epoch,
        "scene_count": len(scene_results),
        "bands_per_scene": len(bands),
        "aggregate_by_epoch_band": aggregate_result,
        "scenes_with_mismatch": sum(
            any(values["mismatch_pixels"] for values in scene["bands"].values()) for scene in scene_results
        ),
        "scene_results": scene_results,
    }
    print(json.dumps({key: value for key, value in result.items() if key != "scene_results"}, indent=2))
    return result


@app.function(secrets=[b2_secret], timeout=7200, cpu=4.0, memory=8192)
def validate_phase3_part3_radiometry(epoch: int) -> dict:
    """Calculate read-only real-pixel radiometric QC for one complete epoch."""
    import io
    import json
    import os
    import zipfile
    from collections import defaultdict

    import boto3
    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds

    from src.preprocessing.radiometry import (
        convert_dn_to_reflectance,
        parameters_for_band,
        parse_l2a_radiometry_metadata,
        reflectance_statistics,
    )
    from src.preprocessing.read_strategy import build_vsizip_vsis3_path, find_band_inner_paths, vsis3_credentials
    from src.storage.backends import B2Backend, RangeReadFile
    from src.utils.io import load_config

    b2 = load_config("b2")
    compute = load_config("compute")
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    key_id, app_key = os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"]
    client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key)
    backend = B2Backend(endpoint, bucket, key_id=key_id, application_key=app_key, client=client)
    selected_key = f"{compute['b2_output_prefixes']['manifests']}selected_scenes.jsonl"
    rows = [json.loads(line) for line in client.get_object(Bucket=bucket, Key=selected_key)["Body"].read().decode().splitlines() if line]
    rows = sorted([row for row in rows if row.get("selected", True) and int(row["epoch"]) == epoch], key=lambda r: r["selection_rank"])
    if len(rows) != 8:
        raise RuntimeError(f"Expected 8 approved scenes for {epoch}, found {len(rows)}")
    boundary = gpd.read_file(io.BytesIO(client.get_object(Bucket=bucket, Key="vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson")["Body"].read()))
    bands = ("B02", "B03", "B04", "B08", "B11", "B12")
    scene_results = []
    parameter_profiles = set()

    for index, scene in enumerate(rows, 1):
        key = scene["object_key"]
        info = backend.stat(key)
        with zipfile.ZipFile(RangeReadFile(backend, key, info.size_bytes)) as archive:
            metadata_names = [name for name in archive.namelist() if name.endswith("/MTD_MSIL2A.xml")]
            if len(metadata_names) != 1:
                raise RuntimeError(f"{key}: expected exactly one product metadata XML")
            metadata = parse_l2a_radiometry_metadata(archive.read(metadata_names[0]))
        paths = find_band_inner_paths(backend, key, info.size_bytes)
        band_stats = {}
        with vsis3_credentials(key_id, app_key, endpoint):
            for band in bands:
                offset, quantification = parameters_for_band(metadata, band)
                parameter_profiles.add((metadata.processing_baseline, band, offset, quantification))
                with rasterio.open(build_vsizip_vsis3_path(bucket, key, paths[band])) as src:
                    projected = boundary.to_crs(src.crs)
                    window = from_bounds(*projected.total_bounds, transform=src.transform)
                    window = window.round_offsets().round_lengths().intersection(Window(0, 0, src.width, src.height))
                    dn = src.read(1, window=window)
                    inside = geometry_mask(projected.geometry, out_shape=dn.shape, transform=src.window_transform(window), invert=True)
                reflectance, source_valid = convert_dn_to_reflectance(
                    dn, offset=offset, quantification_value=quantification, output_nodata=-9999.0
                )
                valid = source_valid & inside
                stats = reflectance_statistics(reflectance, valid)
                stats["nodata_inside_boundary"] = int((inside & ~source_valid).sum())
                stats["offset"] = offset
                stats["quantification_value"] = quantification
                band_stats[band] = stats
        scene_results.append({"scene_id": scene.get("scene_id"), "baseline": metadata.processing_baseline, "bands": band_stats})
        print(json.dumps({"progress": f"{index}/8", "epoch": epoch, "scene_id": scene.get("scene_id")}))

    aggregate = {}
    for band in bands:
        rows_for_band = [scene["bands"][band] for scene in scene_results]
        aggregate[band] = {
            "valid_pixels": sum(row["valid_pixels"] for row in rows_for_band),
            "nodata_inside_boundary": sum(row["nodata_inside_boundary"] for row in rows_for_band),
            "negative_pixels": sum(row["negative_pixels"] for row in rows_for_band),
            "above_one_pixels": sum(row["above_one_pixels"] for row in rows_for_band),
            "minimum": min(row["minimum"] for row in rows_for_band),
            "median_of_scene_medians": float(np.median([row["median"] for row in rows_for_band])),
            "maximum": max(row["maximum"] for row in rows_for_band),
        }
    result = {
        "read_only": True,
        "epoch": epoch,
        "scene_count": 8,
        "parameter_profiles": [list(profile) for profile in sorted(parameter_profiles)],
        "aggregate": aggregate,
        "scenes": scene_results,
    }
    print(json.dumps({key: value for key, value in result.items() if key != "scenes"}, indent=2))
    return result


@app.function(secrets=[b2_secret], timeout=7200, cpu=4.0, memory=8192)
def validate_phase3_part3_spatial(epoch: int) -> dict:
    """Validate real window equivalence and 20 m -> 10 m resampling."""
    import io, json, os, zipfile
    import boto3
    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.windows import Window, from_bounds

    from src.preprocessing.radiometry import convert_dn_to_reflectance, parameters_for_band, parse_l2a_radiometry_metadata
    from src.preprocessing.read_strategy import build_vsizip_vsis3_path, find_band_inner_paths, vsis3_credentials
    from src.preprocessing.spatial import grid_from_bounds, resample_array, snap_bounds_outward
    from src.storage.backends import B2Backend, RangeReadFile
    from src.utils.io import load_config

    b2, compute = load_config("b2"), load_config("compute")
    preprocessing = load_config("preprocessing")["extraction"]
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    key_id, app_key = os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"]
    client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key)
    backend = B2Backend(endpoint, bucket, key_id=key_id, application_key=app_key, client=client)
    key = f"{compute['b2_output_prefixes']['manifests']}selected_scenes.jsonl"
    rows = [json.loads(line) for line in client.get_object(Bucket=bucket, Key=key)["Body"].read().decode().splitlines() if line]
    rows = sorted([row for row in rows if row.get("selected", True) and int(row["epoch"]) == epoch], key=lambda r: r["selection_rank"])
    if len(rows) != 8:
        raise RuntimeError(f"Expected 8 approved scenes for {epoch}, found {len(rows)}")
    boundary = gpd.read_file(io.BytesIO(client.get_object(Bucket=bucket, Key="vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson")["Body"].read())).to_crs("EPSG:32644")
    target_bounds = snap_bounds_outward(tuple(boundary.total_bounds), origin_x=699960, origin_y=2000040, pixel_size=10)
    target_transform, target_width, target_height = grid_from_bounds(target_bounds, 10)
    target_shape = (target_height, target_width)
    results = []

    for index, scene in enumerate(rows, 1):
        object_key = scene["object_key"]
        info = backend.stat(object_key)
        paths = find_band_inner_paths(backend, object_key, info.size_bytes)
        with zipfile.ZipFile(RangeReadFile(backend, object_key, info.size_bytes)) as archive:
            names = [name for name in archive.namelist() if name.endswith("/MTD_MSIL2A.xml")]
            metadata = parse_l2a_radiometry_metadata(archive.read(names[0]))
        scene_result = {"baseline": metadata.processing_baseline, "bands": {}}

        with vsis3_credentials(key_id, app_key, endpoint):
            b02_path = build_vsizip_vsis3_path(bucket, object_key, paths["B02"])
            with rasterio.open(b02_path) as src:
                window = from_bounds(*target_bounds, transform=src.transform).round_offsets().round_lengths()
                if src.window_transform(window) != target_transform or (int(window.height), int(window.width)) != target_shape:
                    raise RuntimeError(f"{object_key}: canonical 10 m window is misaligned")
                direct = src.read(1, window=window)
                padded_window = Window(window.col_off - 1, window.row_off - 1, window.width + 2, window.height + 2)
                padded = src.read(1, window=padded_window)
                if padded.shape[0] != direct.shape[0] + 2 or padded.shape[1] != direct.shape[1] + 2:
                    raise RuntimeError(f"{object_key}: reference window cannot surround direct window")
                if not np.array_equal(direct, padded[1:-1, 1:-1]):
                    raise RuntimeError(f"{object_key}: direct window differs from larger reference-window clip")

            for band, method, dtype, dst_nodata in (
                ("B11", "bilinear", "float32", -9999.0),
                ("B12", "bilinear", "float32", -9999.0),
                ("SCL", "nearest", "uint8", 0),
            ):
                path = build_vsizip_vsis3_path(bucket, object_key, paths[band])
                with rasterio.open(path) as src:
                    source_window = from_bounds(*target_bounds, transform=src.transform).round_offsets().round_lengths()
                    source = src.read(1, window=source_window)
                    source_transform = src.window_transform(source_window)
                    source_classes = set(np.unique(source).tolist()) if band == "SCL" else None
                    src_crs = src.crs
                if band == "SCL":
                    converted, src_nodata = source, 0
                else:
                    offset, quantification = parameters_for_band(metadata, band)
                    converted, _ = convert_dn_to_reflectance(source, offset=offset, quantification_value=quantification)
                    src_nodata = -9999.0
                output = resample_array(
                    converted, src_transform=source_transform, src_crs=src_crs,
                    dst_transform=target_transform, dst_crs="EPSG:32644", dst_shape=target_shape,
                    method=method, src_nodata=src_nodata, dst_nodata=dst_nodata, dst_dtype=dtype,
                )
                if output.shape != target_shape:
                    raise RuntimeError(f"{object_key}/{band}: wrong output shape")
                if band == "SCL":
                    new_classes = set(np.unique(output).tolist()) - source_classes - {0}
                    if new_classes:
                        raise RuntimeError(f"{object_key}/SCL: nearest created classes {new_classes}")
                    scene_result["bands"][band] = {"classes": sorted(np.unique(output).tolist())}
                else:
                    valid = output != -9999.0
                    if np.any(output[valid] < -1.0):
                        raise RuntimeError(f"{object_key}/{band}: nodata contaminated valid output")
                    scene_result["bands"][band] = {
                        "valid_pixels": int(valid.sum()), "nodata_pixels": int((~valid).sum()),
                        "minimum": float(output[valid].min()) if valid.any() else None,
                        "maximum": float(output[valid].max()) if valid.any() else None,
                    }
        results.append(scene_result)
        print(json.dumps({"progress": f"{index}/8", "epoch": epoch}))

    summary = {
        "read_only": True, "epoch": epoch, "scene_count": len(results),
        "target_bounds": target_bounds, "target_shape": target_shape,
        "target_transform": list(target_transform)[:6],
        "window_equivalence_passed": len(results), "scene_results": results,
    }
    print(json.dumps({key: value for key, value in summary.items() if key != "scene_results"}, indent=2))
    return summary


@app.function(secrets=[b2_secret], timeout=300)
def inspect_phase3_part3_pilot_outputs() -> dict:
    """Read-only existence check for the deterministic pilot output keys."""
    import json, os
    import boto3
    from botocore.exceptions import ClientError

    from src.utils.io import load_config

    b2, compute = load_config("b2"), load_config("compute")
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    )
    selected_key = f"{compute['b2_output_prefixes']['manifests']}selected_scenes.jsonl"
    rows = [
        json.loads(line)
        for line in client.get_object(Bucket=bucket, Key=selected_key)["Body"].read().decode().splitlines()
        if line
    ]
    scene = sorted(
        [row for row in rows if row.get("selected", True)],
        key=lambda row: (int(row["epoch"]), row["selection_rank"]),
    )[0]
    scene_id = scene.get("scene_id") or scene.get("product_id")
    prefix = (
        f"{compute['b2_output_prefixes']['processed']}sentinel2/scene_stacks/"
        f"{int(scene['epoch'])}/"
    )
    outputs = {}
    for name, key in {
        "reflectance": f"{prefix}{scene_id}_reflectance.tif",
        "scl": f"{prefix}{scene_id}_scl.tif",
    }.items():
        try:
            head = client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                raise
            outputs[name] = {"key": key, "exists": False}
        else:
            outputs[name] = {
                "key": key,
                "exists": True,
                "bytes": int(head["ContentLength"]),
                "etag": head.get("ETag", "").strip('"'),
            }
    result = {"scene_id": scene_id, "epoch": int(scene["epoch"]), "outputs": outputs}
    print(json.dumps(result, indent=2))
    return result


@app.function(secrets=[b2_secret], timeout=900)
def preflight_phase3_part3_batch() -> dict:
    """Read-only validation of all selected sources and deterministic outputs."""
    import json, os
    from collections import Counter

    import boto3
    from botocore.exceptions import ClientError

    from src.preprocessing.extraction_batch import (
        classify_output_pair,
        output_keys,
        validate_selected_scenes,
    )
    from src.utils.io import load_config

    b2, compute = load_config("b2"), load_config("compute")
    preprocessing = load_config("preprocessing")["extraction"]
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    )
    prefixes = compute["b2_output_prefixes"]
    selected_key = f"{prefixes['manifests']}selected_scenes.jsonl"
    manifest_key = f"{prefixes['manifests']}scene_extraction_manifest.jsonl"
    rows = [
        json.loads(line)
        for line in client.get_object(Bucket=bucket, Key=selected_key)["Body"].read().decode().splitlines()
        if line
    ]
    scenes = [row for row in rows if row.get("selected", True)]
    validate_selected_scenes(scenes)

    def head_or_none(key: str):
        try:
            return client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    entries = []
    for scene in sorted(scenes, key=lambda row: (int(row["epoch"]), row["selection_rank"])):
        source_head = head_or_none(scene["object_key"])
        if source_head is None:
            raise RuntimeError(f"missing selected source object: {scene['object_key']}")
        keys = output_keys(
            prefixes["processed"], scene,
            contract_version=preprocessing["contract_version"],
        )
        reflectance_head = head_or_none(keys.reflectance)
        scl_head = head_or_none(keys.scl)
        state = classify_output_pair(
            reflectance_exists=reflectance_head is not None,
            scl_exists=scl_head is not None,
        )
        entries.append({
            "scene_id": scene.get("scene_id") or scene.get("product_id"),
            "epoch": int(scene["epoch"]),
            "source": {
                "key": scene["object_key"],
                "bytes": int(source_head["ContentLength"]),
                "etag": source_head.get("ETag", "").strip('"'),
            },
            "output_state": state.value,
            "reflectance_key": keys.reflectance,
            "scl_key": keys.scl,
            "reflectance_bytes": (
                int(reflectance_head["ContentLength"]) if reflectance_head else None
            ),
            "scl_bytes": int(scl_head["ContentLength"]) if scl_head else None,
        })

    manifest_head = head_or_none(manifest_key)
    counts = Counter(entry["output_state"] for entry in entries)
    result = {
        "read_only": True,
        "selected_scene_count": len(entries),
        "epoch_counts": dict(Counter(entry["epoch"] for entry in entries)),
        "output_state_counts": dict(counts),
        "manifest": {
            "key": manifest_key,
            "exists": manifest_head is not None,
            "bytes": int(manifest_head["ContentLength"]) if manifest_head else None,
        },
        "sources_total_bytes": sum(entry["source"]["bytes"] for entry in entries),
        "entries": entries,
    }
    print(json.dumps(result, indent=2))
    return result


@app.function(secrets=[b2_secret], timeout=300)
def load_phase3_part3_batch_scenes() -> list[dict]:
    """Return the canonical approved worklist without modifying B2."""
    import json, os
    import boto3
    from src.preprocessing.extraction_batch import validate_selected_scenes
    from src.utils.io import load_config

    b2, compute = load_config("b2"), load_config("compute")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    )
    key = f"{compute['b2_output_prefixes']['manifests']}selected_scenes.jsonl"
    rows = [
        json.loads(line)
        for line in client.get_object(Bucket=b2["bucket"], Key=key)["Body"].read().decode().splitlines()
        if line
    ]
    scenes = [row for row in rows if row.get("selected", True)]
    validate_selected_scenes(scenes)
    return sorted(scenes, key=lambda row: (int(row["epoch"]), row["selection_rank"]))


@app.function(secrets=[b2_secret], timeout=300)
def publish_phase3_part3_manifest(results: list[dict]) -> dict:
    """Publish once to an absent B2 key, then verify exact remote bytes."""
    import hashlib, os, time
    import boto3
    from botocore.exceptions import (
        ClientError,
        ConnectTimeoutError,
        ConnectionClosedError,
        EndpointConnectionError,
        HTTPClientError,
        ReadTimeoutError,
    )
    from src.preprocessing.extraction_batch import build_extraction_manifest
    from src.utils.io import load_config

    b2, compute = load_config("b2"), load_config("compute")
    key = f"{compute['b2_output_prefixes']['manifests']}scene_extraction_manifest.jsonl"
    body = build_extraction_manifest(results)
    body_sha256 = hashlib.sha256(body).hexdigest()
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    )
    bucket = b2["bucket"]

    transient_types = (
        ConnectTimeoutError, ConnectionClosedError, EndpointConnectionError,
        HTTPClientError, ReadTimeoutError,
    )

    def is_missing(exc: ClientError) -> bool:
        return exc.response.get("Error", {}).get("Code") in {
            "404", "NoSuchKey", "NotFound",
        }

    def read_existing() -> bytes | None:
        try:
            response = client.get_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if is_missing(exc):
                return None
            raise
        remote = response["Body"].read()
        if len(remote) != int(response["ContentLength"]):
            raise RuntimeError("Manifest read-back length mismatch")
        return remote

    existing = read_existing()
    if existing is not None:
        if existing != body:
            raise RuntimeError(
                "Refusing publication: a different extraction manifest already exists"
            )
        return {
            "key": key, "bytes": len(body), "scene_count": 32,
            "created": False, "reconciled": True, "sha256": body_sha256,
        }

    versions = client.list_object_versions(Bucket=bucket, Prefix=key)
    prior_versions = [
        item for group in ("Versions", "DeleteMarkers")
        for item in versions.get(group, []) if item.get("Key") == key
    ]
    if prior_versions:
        raise RuntimeError(
            "Refusing publication: the absent manifest key has prior B2 versions"
        )

    put_response = None
    put_error = None
    try:
        put_response = client.put_object(
            Bucket=bucket, Key=key, Body=body,
            ContentType="application/x-ndjson",
            Metadata={"sha256": body_sha256, "contract-version": "3.3.2"},
        )
    except transient_types as exc:
        # The request outcome is ambiguous. Never issue a second PUT here;
        # reconcile only through reads so B2 cannot gain another version.
        put_error = exc

    last_read_error = None
    for attempt in range(1, 5):
        try:
            existing = read_existing()
            if existing is not None and existing != body:
                raise RuntimeError("Published extraction manifest byte verification failed")
            if existing == body:
                head = client.head_object(Bucket=bucket, Key=key)
                if head.get("Metadata", {}).get("sha256") != body_sha256:
                    raise RuntimeError("Published manifest SHA-256 metadata mismatch")
                return {
                    "key": key, "bytes": len(body), "scene_count": 32,
                    "created": True, "reconciled": put_error is not None,
                    "sha256": body_sha256,
                    "version_id": head.get("VersionId") or (
                        put_response or {}
                    ).get("VersionId"),
                }
        except transient_types as exc:
            last_read_error = exc
        except ClientError as exc:
            if not is_missing(exc):
                raise
            last_read_error = exc
        if attempt < 4:
            time.sleep(2 ** (attempt - 1))
    raise RuntimeError(
        "Single manifest PUT was not visible after four read-only reconciliation attempts; "
        "no second PUT was issued"
    ) from (last_read_error or put_error)


@app.function(
    secrets=[b2_secret], timeout=7200, cpu=1.0, memory=2048,
    max_containers=2,
)
def recover_phase3_part3_manifest_entry(scene: dict) -> dict:
    """Validate and hash one existing output pair without modifying B2."""
    import hashlib, json, math, os

    import boto3
    import rasterio

    from src.preprocessing.extract_scene import REFLECTANCE_BANDS
    from src.preprocessing.extraction_batch import output_keys, recovery_checkpoint_matches
    from src.preprocessing.read_strategy import vsis3_credentials
    from src.preprocessing.spatial import grid_from_bounds
    from src.utils.io import load_config

    b2 = load_config("b2")
    compute = load_config("compute")
    extraction = load_config("preprocessing")["extraction"]
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    key_id, app_key = os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"]
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=key_id, aws_secret_access_key=app_key,
    )
    scene_id = scene.get("scene_id") or scene.get("product_id")
    source_key = scene["object_key"]
    source_head = client.head_object(Bucket=bucket, Key=source_key)
    source_size = int(source_head["ContentLength"])
    source_etag = source_head.get("ETag", "").strip('"')
    keys = output_keys(
        compute["b2_output_prefixes"]["processed"], scene,
        contract_version=extraction["contract_version"],
    )
    output_keys_by_name = {"reflectance": keys.reflectance, "scl": keys.scl}
    heads = {
        name: client.head_object(Bucket=bucket, Key=key)
        for name, key in output_keys_by_name.items()
    }

    expected_transform, expected_width, expected_height = grid_from_bounds(
        tuple(extraction["output_bounds"]), extraction["pixel_size_m"]
    )
    expected_common = {
        "scene_id": scene_id,
        "contract_version": extraction["contract_version"],
        "source_object_key": source_key,
        "source_size_bytes": str(source_size),
        "source_etag": source_etag,
    }
    captured_tags = {}
    with vsis3_credentials(key_id, app_key, endpoint):
        for name, key in output_keys_by_name.items():
            with rasterio.open(f"/vsis3/{bucket}/{key}") as src:
                if src.width != expected_width or src.height != expected_height:
                    raise RuntimeError(f"{scene_id} {name}: grid dimensions mismatch")
                if src.transform != expected_transform or src.crs.to_string() != extraction["output_crs"]:
                    raise RuntimeError(f"{scene_id} {name}: spatial grid mismatch")
                if name == "reflectance":
                    if src.count != 6 or src.dtypes != ("float32",) * 6 or src.nodata != -9999.0:
                        raise RuntimeError(f"{scene_id}: reflectance schema mismatch")
                    if tuple(src.descriptions) != REFLECTANCE_BANDS:
                        raise RuntimeError(f"{scene_id}: reflectance band order mismatch")
                elif src.count != 1 or src.dtypes != ("uint8",) or src.nodata != 0:
                    raise RuntimeError(f"{scene_id}: SCL schema mismatch")
                tags = src.tags()
                for tag, expected in expected_common.items():
                    if tags.get(tag) != expected:
                        raise RuntimeError(f"{scene_id} {name}: provenance mismatch for {tag}")
                captured_tags[name] = tags

    for tag in ("processing_baseline", "quantification_value", "band_offsets"):
        values = {captured_tags[name].get(tag) for name in captured_tags}
        if None in values or len(values) != 1:
            raise RuntimeError(f"{scene_id}: inconsistent or missing {tag}")
    quantification = float(captured_tags["reflectance"]["quantification_value"])
    if not math.isfinite(quantification) or quantification <= 0:
        raise RuntimeError(f"{scene_id}: invalid quantification value")
    offsets = {}
    for item in captured_tags["reflectance"]["band_offsets"].split(","):
        band, value = item.split(":", 1)
        offsets[band] = float(value)
    if set(offsets) != set(REFLECTANCE_BANDS) or not all(math.isfinite(v) for v in offsets.values()):
        raise RuntimeError(f"{scene_id}: invalid band offsets")

    checkpoint_key = f"contract-{extraction['contract_version']}:{scene_id}"
    checkpoint = manifest_recovery_checkpoints.get(checkpoint_key)
    expected_outputs = {
        name: {"key": key, "bytes": int(heads[name]["ContentLength"])}
        for name, key in output_keys_by_name.items()
    }
    if checkpoint is not None:
        if not recovery_checkpoint_matches(
            checkpoint,
            scene_id=scene_id,
            contract_version=extraction["contract_version"],
            source_key=source_key,
            source_size=source_size,
            source_etag=source_etag,
            outputs=expected_outputs,
        ):
            raise RuntimeError(f"{scene_id}: stored recovery checkpoint is stale or invalid")
        print(json.dumps({
            "scene_id": scene_id, "epoch": int(scene["epoch"]),
            "checkpoint_reused": True,
        }))
        return checkpoint

    outputs = {}
    for name, key in output_keys_by_name.items():
        digest = hashlib.sha256()
        byte_count = 0
        body = client.get_object(Bucket=bucket, Key=key)["Body"]
        try:
            for chunk in body.iter_chunks(chunk_size=8 * 1024 * 1024):
                if chunk:
                    digest.update(chunk)
                    byte_count += len(chunk)
        finally:
            body.close()
        expected_bytes = int(heads[name]["ContentLength"])
        if byte_count != expected_bytes:
            raise RuntimeError(
                f"{scene_id} {name}: streamed {byte_count} bytes; expected {expected_bytes}"
            )
        outputs[name] = {"key": key, "bytes": byte_count, "sha256": digest.hexdigest()}

    result = {
        "scene_id": scene_id,
        "epoch": int(scene["epoch"]),
        "source_key": source_key,
        "outputs": outputs,
        "remote_reopen_validated": True,
        "resumed_without_overwrite": True,
        "contract_version": extraction["contract_version"],
        "source_identity": {"size_bytes": source_size, "etag": source_etag},
        "radiometry": {
            "processing_baseline": captured_tags["reflectance"]["processing_baseline"],
            "quantification_value": quantification,
            "band_offsets": offsets,
        },
    }
    stored = manifest_recovery_checkpoints.put(
        checkpoint_key, result, skip_if_exists=True
    )
    if not stored:
        concurrent = manifest_recovery_checkpoints.get(checkpoint_key)
        if concurrent != result:
            raise RuntimeError(f"{scene_id}: conflicting recovery checkpoint")
    print(json.dumps({
        "scene_id": scene_id,
        "epoch": int(scene["epoch"]),
        "validated_and_hashed": True,
        "output_bytes": sum(item["bytes"] for item in outputs.values()),
    }))
    return result


@app.function(secrets=[b2_secret], timeout=1800, cpu=2.0, memory=4096)
def validate_phase3_part4_masks() -> dict:
    """Read-only SCL mask-policy validation across all extracted scenes."""
    import io, json, os
    from collections import defaultdict

    import boto3
    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask

    from src.preprocessing.read_strategy import vsis3_credentials
    from src.preprocessing.scl_mask import MaskPolicy, build_valid_mask
    from src.utils.io import load_config

    b2 = load_config("b2")
    compute = load_config("compute")
    preprocessing = load_config("preprocessing")
    policy = MaskPolicy.from_mapping(preprocessing["mask"])
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    key_id, app_key = os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"]
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=key_id, aws_secret_access_key=app_key,
    )
    manifest_key = (
        f"{compute['b2_output_prefixes']['manifests']}scene_extraction_manifest.jsonl"
    )
    rows = [
        json.loads(line)
        for line in client.get_object(Bucket=bucket, Key=manifest_key)["Body"]
        .read().decode().splitlines()
        if line
    ]
    if len(rows) != 32:
        raise RuntimeError(f"expected 32 extraction manifest rows, found {len(rows)}")

    boundary = gpd.read_file(io.BytesIO(client.get_object(
        Bucket=bucket,
        Key="vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson",
    )["Body"].read())).to_crs(preprocessing["extraction"]["output_crs"])
    totals = defaultdict(lambda: defaultdict(int))
    scene_results = []
    total_compressed_bytes = 0
    with vsis3_credentials(key_id, app_key, endpoint):
        for row in sorted(rows, key=lambda item: (int(item["epoch"]), item["scene_id"])):
            scl_output = row["outputs"]["scl"]
            total_compressed_bytes += int(scl_output["bytes"])
            with rasterio.open(f"/vsis3/{bucket}/{scl_output['key']}") as src:
                if src.count != 1 or src.dtypes != ("uint8",) or src.nodata != 0:
                    raise RuntimeError(f"{row['scene_id']}: invalid SCL schema")
                scl = src.read(1)
                inside = geometry_mask(
                    boundary.geometry, out_shape=src.shape,
                    transform=src.transform, invert=True,
                )
            valid, stats = build_valid_mask(scl, policy, aoi_mask=inside)
            no_dilation_policy = MaskPolicy(
                valid_classes=policy.valid_classes,
                invalid_classes=policy.invalid_classes,
                dark_class_2_valid=policy.dark_class_2_valid,
                dilate_classes=policy.dilate_classes,
                dilation_radius_pixels=0,
                unknown_classes_invalid=policy.unknown_classes_invalid,
            )
            valid_without_dilation, _ = build_valid_mask(
                scl, no_dilation_policy, aoi_mask=inside
            )
            epoch = int(row["epoch"])
            considered = int(stats["considered_pixels"])
            class_two = int(((scl == 2) & inside).sum())
            dilation_loss = int((valid_without_dilation & ~valid).sum())
            totals[epoch]["considered_pixels"] += considered
            totals[epoch]["valid_pixels"] += int(stats["valid_pixels"])
            totals[epoch]["class_2_pixels"] += class_two
            totals[epoch]["dilation_loss_pixels"] += dilation_loss
            totals[epoch]["unknown_pixels"] += int(stats["unknown_pixels"])
            scene_results.append({
                "scene_id": row["scene_id"], "epoch": epoch,
                "valid_fraction": stats["valid_fraction"],
                "class_2_fraction": class_two / considered if considered else 0.0,
                "dilation_loss_fraction": dilation_loss / considered if considered else 0.0,
                "unknown_pixels": stats["unknown_pixels"],
            })

    epochs = {}
    for epoch, values in sorted(totals.items()):
        considered = values["considered_pixels"]
        epochs[str(epoch)] = {
            **dict(values),
            "valid_fraction": values["valid_pixels"] / considered,
            "class_2_fraction": values["class_2_pixels"] / considered,
            "dilation_loss_fraction": values["dilation_loss_pixels"] / considered,
        }
    result = {
        "read_only": True,
        "scene_count": len(scene_results),
        "scl_compressed_bytes": total_compressed_bytes,
        "policy": preprocessing["mask"],
        "epochs": epochs,
        "max_scene_class_2_fraction": max(
            item["class_2_fraction"] for item in scene_results
        ),
        "max_scene_dilation_loss_fraction": max(
            item["dilation_loss_fraction"] for item in scene_results
        ),
        "unknown_pixels": sum(item["unknown_pixels"] for item in scene_results),
        "scenes": scene_results,
    }
    print(json.dumps(result, indent=2))
    return result


@app.function(secrets=[b2_secret], timeout=300)
def plan_phase3_part5_composites() -> dict:
    """Manifest-only source sizing and output collision preflight for Part 3.5."""
    import json, os
    from collections import defaultdict

    import boto3
    from botocore.exceptions import ClientError

    from src.utils.io import load_config

    b2 = load_config("b2")
    compute = load_config("compute")
    preprocessing = load_config("preprocessing")
    extraction = preprocessing["extraction"]
    composite = preprocessing["composite"]
    bucket = b2["bucket"]
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    )
    manifest_key = (
        f"{compute['b2_output_prefixes']['manifests']}scene_extraction_manifest.jsonl"
    )
    manifest_body = client.get_object(Bucket=bucket, Key=manifest_key)["Body"].read()
    rows = [json.loads(line) for line in manifest_body.decode().splitlines() if line]
    if len(rows) != 32:
        raise RuntimeError(f"expected 32 extraction rows, found {len(rows)}")

    by_epoch = defaultdict(list)
    for row in rows:
        by_epoch[int(row["epoch"])].append(row)
    if {epoch: len(items) for epoch, items in by_epoch.items()} != {
        2018: 8, 2020: 8, 2022: 8, 2024: 8,
    }:
        raise RuntimeError("extraction manifest does not contain 8 scenes per epoch")

    def object_versions(key: str) -> list[dict]:
        response = client.list_object_versions(Bucket=bucket, Prefix=key)
        return [
            item for group in ("Versions", "DeleteMarkers")
            for item in response.get(group, []) if item.get("Key") == key
        ]

    prefix = compute["b2_output_prefixes"]["processed"]
    epochs = {}
    all_outputs_absent = True
    for epoch, items in sorted(by_epoch.items()):
        root = (
            f"{prefix}sentinel2/composites/contract-"
            f"{composite['contract_version']}/{epoch}/"
        )
        outputs = {
            "composite": f"{root}composite.tif",
            "valid_obs_count": f"{root}valid_obs_count.tif",
        }
        output_states = {}
        for name, key in outputs.items():
            versions = object_versions(key)
            output_states[name] = {
                "key": key,
                "absent": not versions,
                "version_count": len(versions),
            }
            all_outputs_absent &= not versions
        epochs[str(epoch)] = {
            "scene_count": len(items),
            "reflectance_source_bytes": sum(
                int(item["outputs"]["reflectance"]["bytes"]) for item in items
            ),
            "scl_source_bytes": sum(
                int(item["outputs"]["scl"]["bytes"]) for item in items
            ),
            "outputs": output_states,
        }
    raw_composite_bytes = (
        6 * int(extraction["output_width"]) * int(extraction["output_height"]) * 4
    )
    raw_count_bytes = (
        int(extraction["output_width"]) * int(extraction["output_height"])
    )
    result = {
        "read_only": True,
        "manifest_key": manifest_key,
        "manifest_bytes_read": len(manifest_body),
        "all_outputs_absent": all_outputs_absent,
        "coverage_gate_configured": (
            composite["min_valid_observations"] is not None
            and composite["min_aoi_coverage_fraction"] is not None
        ),
        "chunk_size_pixels": composite["chunk_size_pixels"],
        "raw_output_bytes_per_epoch": {
            "composite": raw_composite_bytes,
            "valid_obs_count": raw_count_bytes,
            "total": raw_composite_bytes + raw_count_bytes,
        },
        "epochs": epochs,
    }
    print(json.dumps(result, indent=2))
    return result


@app.function(
    secrets=[b2_secret], timeout=7200, cpu=2.0, memory=4096,
    max_containers=2,
)
def scan_phase3_part5_epoch_coverage(epoch: int) -> dict:
    """Read-only all-band/SCL valid-observation scan for one approved epoch."""
    import io, json, os

    import boto3
    import geopandas as gpd
    import numpy as np
    import rasterio
    from rasterio.features import geometry_mask

    from src.preprocessing.extract_scene import REFLECTANCE_BANDS
    from src.preprocessing.read_strategy import vsis3_credentials
    from src.preprocessing.scl_mask import MaskPolicy, build_valid_mask
    from src.utils.io import load_config

    if epoch not in {2018, 2020, 2022, 2024}:
        raise ValueError(f"unsupported epoch: {epoch}")
    b2 = load_config("b2")
    compute = load_config("compute")
    preprocessing = load_config("preprocessing")
    extraction = preprocessing["extraction"]
    policy = MaskPolicy.from_mapping(preprocessing["mask"])
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    key_id, app_key = os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"]
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=key_id, aws_secret_access_key=app_key,
    )
    manifest_key = (
        f"{compute['b2_output_prefixes']['manifests']}scene_extraction_manifest.jsonl"
    )
    rows = [
        json.loads(line)
        for line in client.get_object(Bucket=bucket, Key=manifest_key)["Body"]
        .read().decode().splitlines()
        if line
    ]
    scenes = sorted(
        [row for row in rows if int(row["epoch"]) == epoch],
        key=lambda row: row["scene_id"],
    )
    if len(scenes) != 8:
        raise RuntimeError(f"epoch {epoch}: expected 8 scenes, found {len(scenes)}")

    boundary = gpd.read_file(io.BytesIO(client.get_object(
        Bucket=bucket,
        Key="vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson",
    )["Body"].read())).to_crs(extraction["output_crs"])
    height, width = int(extraction["output_height"]), int(extraction["output_width"])
    expected_shape = (height, width)
    counts = np.zeros(expected_shape, dtype="uint8")
    inside = None
    compressed_bytes = 0

    with vsis3_credentials(key_id, app_key, endpoint):
        for row in scenes:
            reflectance_output = row["outputs"]["reflectance"]
            scl_output = row["outputs"]["scl"]
            compressed_bytes += int(reflectance_output["bytes"]) + int(scl_output["bytes"])
            reflectance_path = f"/vsis3/{bucket}/{reflectance_output['key']}"
            scl_path = f"/vsis3/{bucket}/{scl_output['key']}"
            with rasterio.open(reflectance_path) as reflectance, rasterio.open(scl_path) as scl:
                if (
                    reflectance.shape != expected_shape
                    or reflectance.count != 6
                    or reflectance.dtypes != ("float32",) * 6
                    or reflectance.nodata != -9999.0
                    or tuple(reflectance.descriptions) != REFLECTANCE_BANDS
                ):
                    raise RuntimeError(f"{row['scene_id']}: reflectance schema mismatch")
                if (
                    scl.shape != expected_shape
                    or scl.count != 1
                    or scl.dtypes != ("uint8",)
                    or scl.nodata != 0
                    or scl.transform != reflectance.transform
                    or scl.crs != reflectance.crs
                ):
                    raise RuntimeError(f"{row['scene_id']}: SCL/grid schema mismatch")
                if inside is None:
                    inside = geometry_mask(
                        boundary.geometry, out_shape=expected_shape,
                        transform=reflectance.transform, invert=True,
                    )
                for _, window in reflectance.block_windows(1):
                    values = reflectance.read(window=window)
                    scl_values = scl.read(1, window=window)
                    row_slice, col_slice = window.toslices()
                    aoi_window = inside[row_slice, col_slice]
                    reflectance_valid = np.all(
                        np.isfinite(values) & (values != reflectance.nodata), axis=0
                    )
                    valid, _ = build_valid_mask(
                        scl_values, policy,
                        reflectance_valid=reflectance_valid,
                        aoi_mask=aoi_window,
                    )
                    counts[row_slice, col_slice] += valid.astype("uint8")

    if inside is None:
        raise RuntimeError(f"epoch {epoch}: no scenes were scanned")
    aoi_counts = counts[inside]
    histogram = {
        str(value): int((aoi_counts == value).sum()) for value in range(9)
    }
    aoi_pixels = int(aoi_counts.size)
    coverage_by_minimum = {
        str(minimum): float((aoi_counts >= minimum).sum() / aoi_pixels)
        for minimum in range(1, 9)
    }
    result = {
        "read_only": True,
        "epoch": epoch,
        "scene_count": 8,
        "compressed_source_bytes": compressed_bytes,
        "aoi_pixels": aoi_pixels,
        "count_histogram": histogram,
        "coverage_by_minimum_observations": coverage_by_minimum,
        "minimum_count": int(aoi_counts.min()),
        "median_count": float(np.median(aoi_counts)),
        "maximum_count": int(aoi_counts.max()),
    }
    print(json.dumps(result, indent=2))
    return result


@app.function(
    secrets=[b2_secret], timeout=10800, cpu=4.0, memory=16384,
    max_containers=2,
)
def build_phase3_part5_epoch_composite(epoch: int) -> dict:
    """Build, validate, and non-overwritingly publish one approved composite pair."""
    import contextlib, hashlib, io, json, os, tempfile, warnings
    from pathlib import Path

    import boto3
    import geopandas as gpd
    import numpy as np
    import rasterio
    from botocore.config import Config
    from rasterio.features import geometry_mask
    from rasterio.windows import Window
    from rio_cogeo.cogeo import cog_translate, cog_validate
    from rio_cogeo.profiles import cog_profiles

    from src.preprocessing.composite import CoverageGate, assess_coverage
    from src.preprocessing.extract_scene import REFLECTANCE_BANDS
    from src.preprocessing.read_strategy import vsis3_credentials
    from src.preprocessing.scl_mask import MaskPolicy, build_valid_mask
    from src.utils.io import load_config

    if epoch not in {2018, 2020, 2022, 2024}:
        raise ValueError(f"unsupported epoch: {epoch}")
    b2 = load_config("b2")
    compute = load_config("compute")
    preprocessing = load_config("preprocessing")
    extraction = preprocessing["extraction"]
    composite_config = preprocessing["composite"]
    gate = CoverageGate.from_mapping(composite_config)
    policy = MaskPolicy.from_mapping(preprocessing["mask"])
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    key_id, app_key = os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"]
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=key_id, aws_secret_access_key=app_key,
        config=Config(retries={"max_attempts": 1, "mode": "standard"}),
    )
    manifest_key = f"{compute['b2_output_prefixes']['manifests']}scene_extraction_manifest.jsonl"
    rows = [json.loads(line) for line in client.get_object(
        Bucket=bucket, Key=manifest_key,
    )["Body"].read().decode().splitlines() if line]
    scenes = sorted(
        [row for row in rows if int(row["epoch"]) == epoch],
        key=lambda row: row["scene_id"],
    )
    if len(scenes) != 8:
        raise RuntimeError(f"epoch {epoch}: expected 8 scenes, found {len(scenes)}")

    root = (
        f"{compute['b2_output_prefixes']['processed']}sentinel2/composites/"
        f"contract-{composite_config['contract_version']}/{epoch}/"
    )
    output_keys = {
        "composite": f"{root}composite.tif",
        "valid_obs_count": f"{root}valid_obs_count.tif",
    }

    def matching_versions(key: str) -> list[dict]:
        response = client.list_object_versions(Bucket=bucket, Prefix=key)
        return [item for group in ("Versions", "DeleteMarkers")
                for item in response.get(group, []) if item.get("Key") == key]

    def require_absent() -> None:
        collisions = {}
        for name, key in output_keys.items():
            versions = matching_versions(key)
            if versions:
                collisions[name] = len(versions)
        if collisions:
            raise FileExistsError(
                f"epoch {epoch}: refusing to overwrite output versions: {collisions}"
            )

    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    require_absent()
    boundary = gpd.read_file(io.BytesIO(client.get_object(
        Bucket=bucket, Key="vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson",
    )["Body"].read())).to_crs(extraction["output_crs"])
    height, width = int(extraction["output_height"]), int(extraction["output_width"])
    expected_shape = (height, width)
    chunk_size = int(composite_config["chunk_size_pixels"])
    dilation_radius = int(policy.dilation_radius_pixels)
    reflectance_nodata = float(composite_config["reflectance_nodata"])
    count_nodata = int(composite_config["valid_obs_nodata"])

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        composite_source = temp_dir / "composite.source.tif"
        count_source = temp_dir / "valid_obs_count.source.tif"
        composite_path = temp_dir / "composite.tif"
        count_path = temp_dir / "valid_obs_count.tif"
        provenance = {
            "contract_version": composite_config["contract_version"],
            "epoch": str(epoch), "scene_count": "8",
            "scene_ids": ",".join(row["scene_id"] for row in scenes),
            "source_manifest_key": manifest_key,
            "minimum_valid_observations": str(gate.min_valid_observations),
            "minimum_aoi_coverage_fraction": format(gate.min_aoi_coverage_fraction, ".15g"),
            "mask_contract": "phase-3.4",
        }
        count_histogram = np.zeros(9, dtype="int64")

        with vsis3_credentials(key_id, app_key, endpoint), contextlib.ExitStack() as stack:
            reflectance_sources, scl_sources = [], []
            for row in scenes:
                reflectance = stack.enter_context(rasterio.open(
                    f"/vsis3/{bucket}/{row['outputs']['reflectance']['key']}"
                ))
                scl = stack.enter_context(rasterio.open(
                    f"/vsis3/{bucket}/{row['outputs']['scl']['key']}"
                ))
                if (reflectance.shape != expected_shape or reflectance.count != 6
                        or reflectance.dtypes != ("float32",) * 6
                        or reflectance.nodata != reflectance_nodata
                        or tuple(reflectance.descriptions) != REFLECTANCE_BANDS):
                    raise RuntimeError(f"{row['scene_id']}: reflectance schema mismatch")
                if (scl.shape != expected_shape or scl.count != 1
                        or scl.dtypes != ("uint8",) or scl.nodata != 0
                        or scl.transform != reflectance.transform or scl.crs != reflectance.crs):
                    raise RuntimeError(f"{row['scene_id']}: SCL/grid schema mismatch")
                if reflectance_sources and (
                    reflectance.transform != reflectance_sources[0].transform
                    or reflectance.crs != reflectance_sources[0].crs
                ):
                    raise RuntimeError(f"{row['scene_id']}: inter-scene grid mismatch")
                reflectance_sources.append(reflectance)
                scl_sources.append(scl)

            reference = reflectance_sources[0]
            inside = geometry_mask(
                boundary.geometry, out_shape=expected_shape,
                transform=reference.transform, invert=True,
            )
            with rasterio.open(
                composite_source, "w", driver="GTiff", width=width, height=height,
                count=6, dtype="float32", crs=reference.crs, transform=reference.transform,
                nodata=reflectance_nodata, tiled=True, blockxsize=chunk_size,
                blockysize=chunk_size, compress="deflate", predictor=3, BIGTIFF="IF_SAFER",
            ) as composite_dst, rasterio.open(
                count_source, "w", driver="GTiff", width=width, height=height,
                count=1, dtype="uint8", crs=reference.crs, transform=reference.transform,
                nodata=count_nodata, tiled=True, blockxsize=chunk_size,
                blockysize=chunk_size, compress="deflate", predictor=2, BIGTIFF="IF_SAFER",
            ) as count_dst:
                composite_dst.descriptions = REFLECTANCE_BANDS
                count_dst.set_band_description(1, "valid_obs_count")
                composite_dst.update_tags(**provenance, units="unitless_BOA_reflectance")
                count_dst.update_tags(**provenance, units="count")

                for row_off in range(0, height, chunk_size):
                    block_height = min(chunk_size, height - row_off)
                    for col_off in range(0, width, chunk_size):
                        block_width = min(chunk_size, width - col_off)
                        window = Window(col_off, row_off, block_width, block_height)
                        exp_col = max(0, col_off - dilation_radius)
                        exp_row = max(0, row_off - dilation_radius)
                        exp_col_end = min(width, col_off + block_width + dilation_radius)
                        exp_row_end = min(height, row_off + block_height + dilation_radius)
                        expanded = Window(
                            exp_col, exp_row, exp_col_end - exp_col, exp_row_end - exp_row
                        )
                        crop_rows = slice(row_off - exp_row, row_off - exp_row + block_height)
                        crop_cols = slice(col_off - exp_col, col_off - exp_col + block_width)
                        aoi_window = inside[row_off:row_off + block_height,
                                            col_off:col_off + block_width]
                        scene_values, scene_valid = [], []
                        for reflectance, scl in zip(reflectance_sources, scl_sources):
                            values = reflectance.read(window=window)
                            expanded_values = reflectance.read(window=expanded)
                            expanded_scl = scl.read(1, window=expanded)
                            reflectance_valid = np.all(
                                np.isfinite(expanded_values)
                                & (expanded_values != reflectance_nodata), axis=0,
                            )
                            valid_expanded, _ = build_valid_mask(
                                expanded_scl, policy, reflectance_valid=reflectance_valid,
                            )
                            scene_values.append(values)
                            scene_valid.append(
                                valid_expanded[crop_rows, crop_cols] & aoi_window
                            )
                        values_stack = np.stack(scene_values)
                        valid_stack = np.stack(scene_valid)
                        counts = valid_stack.sum(axis=0, dtype="uint8")
                        masked = np.where(valid_stack[:, None, :, :], values_stack, np.nan)
                        with warnings.catch_warnings():
                            warnings.filterwarnings("ignore", message="All-NaN slice encountered")
                            median = np.nanmedian(masked, axis=0).astype("float32")
                        sufficient = (counts >= gate.min_valid_observations) & aoi_window
                        median[:, ~sufficient] = reflectance_nodata
                        output_counts = counts.copy()
                        output_counts[~aoi_window] = count_nodata
                        composite_dst.write(median, window=window)
                        count_dst.write(output_counts, 1, window=window)
                        count_histogram += np.bincount(
                            counts[aoi_window], minlength=9
                        )[:9]

        aoi_counts = np.repeat(np.arange(9, dtype="uint8"), count_histogram)
        coverage = assess_coverage(
            aoi_counts.reshape(1, -1),
            np.ones((1, aoi_counts.size), dtype=bool),
            gate,
        )

        profile = cog_profiles.get("deflate")
        profile.update({"blockxsize": chunk_size, "blockysize": chunk_size,
                        "BIGTIFF": "IF_SAFER", "predictor": 3})
        cog_translate(str(composite_source), str(composite_path), profile, quiet=True)
        count_profile = cog_profiles.get("deflate")
        count_profile.update({"blockxsize": chunk_size, "blockysize": chunk_size,
                              "BIGTIFF": "IF_SAFER", "predictor": 2})
        cog_translate(str(count_source), str(count_path), count_profile, quiet=True)
        for path in (composite_path, count_path):
            validation = cog_validate(str(path), strict=True)
            if not (validation[0] if isinstance(validation, tuple) else validation):
                raise RuntimeError(f"strict COG validation failed for {path.name}: {validation}")

        local_outputs = {
            "composite": {"path": composite_path, "bytes": composite_path.stat().st_size,
                          "sha256": sha256_file(composite_path)},
            "valid_obs_count": {"path": count_path, "bytes": count_path.stat().st_size,
                                "sha256": sha256_file(count_path)},
        }
        require_absent()
        published = {}
        for name in ("composite", "valid_obs_count"):
            details = local_outputs[name]
            metadata = {"sha256": details["sha256"],
                        "contract-version": composite_config["contract_version"],
                        "epoch": str(epoch)}
            try:
                client.upload_file(
                    str(details["path"]), bucket, output_keys[name],
                    ExtraArgs={"ContentType": "image/tiff", "Metadata": metadata},
                )
            except Exception:
                # Reconcile an ambiguous response without issuing another PUT.
                head = client.head_object(Bucket=bucket, Key=output_keys[name])
                if (int(head["ContentLength"]) != details["bytes"]
                        or head.get("Metadata", {}).get("sha256") != details["sha256"]):
                    raise
            head = client.head_object(Bucket=bucket, Key=output_keys[name])
            if (int(head["ContentLength"]) != details["bytes"]
                    or head.get("Metadata", {}).get("sha256") != details["sha256"]):
                raise RuntimeError(f"{name}: B2 post-upload identity check failed")
            published[name] = {"key": output_keys[name], "bytes": details["bytes"],
                               "sha256": details["sha256"],
                               "version_id": head.get("VersionId")}

        with vsis3_credentials(key_id, app_key, endpoint):
            with rasterio.open(f"/vsis3/{bucket}/{output_keys['composite']}") as remote:
                if (remote.count != 6 or remote.dtypes != ("float32",) * 6
                        or remote.nodata != reflectance_nodata
                        or tuple(remote.descriptions) != REFLECTANCE_BANDS
                        or remote.shape != expected_shape):
                    raise RuntimeError("remote composite reopen validation failed")
            with rasterio.open(f"/vsis3/{bucket}/{output_keys['valid_obs_count']}") as remote:
                if (remote.count != 1 or remote.dtypes != ("uint8",)
                        or remote.nodata != count_nodata or remote.shape != expected_shape):
                    raise RuntimeError("remote count reopen validation failed")

    result = {
        "epoch": epoch, "scene_count": 8, "coverage": coverage,
        "count_histogram": {str(i): int(value) for i, value in enumerate(count_histogram)},
        "outputs": published, "remote_reopen_validated": True,
    }
    print(json.dumps(result, indent=2))
    return result


@app.function(secrets=[b2_secret], timeout=10800, cpu=2.0, memory=4096)
def audit_phase3_part5_composites() -> dict:
    """Independently audit all published Part 3.5 objects without writing."""
    import hashlib, json, os

    import boto3
    import numpy as np
    import rasterio
    from rio_cogeo.cogeo import cog_validate

    from src.preprocessing.composite import CoverageGate
    from src.preprocessing.extract_scene import REFLECTANCE_BANDS
    from src.preprocessing.read_strategy import vsis3_credentials
    from src.utils.io import load_config

    b2 = load_config("b2")
    compute = load_config("compute")
    preprocessing = load_config("preprocessing")
    extraction = preprocessing["extraction"]
    composite_config = preprocessing["composite"]
    gate = CoverageGate.from_mapping(composite_config)
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    key_id, app_key = os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"]
    client = boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=key_id, aws_secret_access_key=app_key,
    )
    expected_shape = (
        int(extraction["output_height"]), int(extraction["output_width"])
    )
    reflectance_nodata = float(composite_config["reflectance_nodata"])
    count_nodata = int(composite_config["valid_obs_nodata"])
    root = (
        f"{compute['b2_output_prefixes']['processed']}sentinel2/composites/"
        f"contract-{composite_config['contract_version']}/"
    )

    def versions_for(key: str) -> list[dict]:
        response = client.list_object_versions(Bucket=bucket, Prefix=key)
        return [item for group in ("Versions", "DeleteMarkers")
                for item in response.get(group, []) if item.get("Key") == key]

    def remote_sha256(key: str) -> tuple[str, int]:
        response = client.get_object(Bucket=bucket, Key=key)
        digest, byte_count = hashlib.sha256(), 0
        for chunk in iter(lambda: response["Body"].read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            byte_count += len(chunk)
        return digest.hexdigest(), byte_count

    objects, epochs = [], []
    with vsis3_credentials(key_id, app_key, endpoint):
        for epoch in (2018, 2020, 2022, 2024):
            epoch_root = f"{root}{epoch}/"
            keys = {
                "composite": f"{epoch_root}composite.tif",
                "valid_obs_count": f"{epoch_root}valid_obs_count.tif",
            }
            for name, key in keys.items():
                versions = versions_for(key)
                if len(versions) != 1 or not versions[0].get("IsLatest"):
                    raise RuntimeError(
                        f"{key}: expected exactly one current version, found {len(versions)}"
                    )
                head = client.head_object(Bucket=bucket, Key=key)
                digest, byte_count = remote_sha256(key)
                expected_digest = head.get("Metadata", {}).get("sha256")
                if byte_count != int(head["ContentLength"]) or digest != expected_digest:
                    raise RuntimeError(f"{key}: streamed identity validation failed")
                path = f"/vsis3/{bucket}/{key}"
                cog_result = cog_validate(path, strict=True)
                if not (cog_result[0] if isinstance(cog_result, tuple) else cog_result):
                    raise RuntimeError(f"{key}: strict COG validation failed: {cog_result}")
                objects.append({
                    "epoch": epoch, "kind": name, "key": key,
                    "bytes": byte_count, "sha256": digest,
                    "version_id": versions[0].get("VersionId"),
                    "strict_cog": True,
                })

            with rasterio.open(f"/vsis3/{bucket}/{keys['composite']}") as composite, \
                    rasterio.open(f"/vsis3/{bucket}/{keys['valid_obs_count']}") as counts:
                if (composite.shape != expected_shape or composite.count != 6
                        or composite.dtypes != ("float32",) * 6
                        or composite.nodata != reflectance_nodata
                        or tuple(composite.descriptions) != REFLECTANCE_BANDS):
                    raise RuntimeError(f"epoch {epoch}: composite schema mismatch")
                if (counts.shape != expected_shape or counts.count != 1
                        or counts.dtypes != ("uint8",) or counts.nodata != count_nodata
                        or counts.transform != composite.transform or counts.crs != composite.crs):
                    raise RuntimeError(f"epoch {epoch}: count/grid schema mismatch")
                expected_tags = {
                    "contract_version": composite_config["contract_version"],
                    "epoch": str(epoch), "scene_count": "8",
                    "minimum_valid_observations": str(gate.min_valid_observations),
                    "minimum_aoi_coverage_fraction": format(
                        gate.min_aoi_coverage_fraction, ".15g"
                    ),
                }
                for dataset_name, dataset in (("composite", composite), ("count", counts)):
                    tags = dataset.tags()
                    for tag, value in expected_tags.items():
                        if tags.get(tag) != value:
                            raise RuntimeError(
                                f"epoch {epoch} {dataset_name}: provenance mismatch for {tag}"
                            )

                histogram = np.zeros(9, dtype="int64")
                aoi_pixels = sufficient_pixels = 0
                for _, window in counts.block_windows(1):
                    count_values = counts.read(1, window=window)
                    composite_values = composite.read(window=window)
                    inside = count_values != count_nodata
                    if np.any(count_values[inside] > 8):
                        raise RuntimeError(f"epoch {epoch}: count outside 0..8")
                    sufficient = inside & (count_values >= gate.min_valid_observations)
                    composite_valid = np.all(
                        np.isfinite(composite_values)
                        & (composite_values != reflectance_nodata), axis=0,
                    )
                    if not np.array_equal(composite_valid, sufficient):
                        raise RuntimeError(
                            f"epoch {epoch}: composite/count validity disagreement"
                        )
                    aoi_values = count_values[inside]
                    histogram += np.bincount(aoi_values, minlength=9)[:9]
                    aoi_pixels += int(aoi_values.size)
                    sufficient_pixels += int(sufficient.sum())
                coverage_fraction = sufficient_pixels / aoi_pixels
                if coverage_fraction < gate.min_aoi_coverage_fraction:
                    raise RuntimeError(f"epoch {epoch}: coverage gate no longer passes")
                epochs.append({
                    "epoch": epoch, "aoi_pixels": aoi_pixels,
                    "sufficient_pixels": sufficient_pixels,
                    "coverage_fraction": coverage_fraction,
                    "count_histogram": {
                        str(i): int(value) for i, value in enumerate(histogram)
                    },
                    "schema_grid_provenance_validated": True,
                    "pixel_validity_agreement": True,
                })

    result = {
        "read_only": True, "contract_version": composite_config["contract_version"],
        "object_count": len(objects),
        "total_bytes_hashed": sum(item["bytes"] for item in objects),
        "all_objects_single_version": True,
        "objects": objects, "epochs": epochs,
    }
    print(json.dumps(result, indent=2))
    return result


@app.function(
    secrets=[b2_secret], timeout=7200, cpu=4.0, memory=16384,
    max_containers=2,
)
def run_phase3_part3_pilot(scene_override: dict | None = None) -> dict:
    """Extract, validate, upload, and remotely reopen one approved scene."""
    import io, json, os, tempfile, zipfile
    from pathlib import Path
    import boto3
    import geopandas as gpd
    import numpy as np
    import rasterio
    from botocore.exceptions import ClientError
    from rasterio.features import geometry_mask
    from rasterio.windows import from_bounds

    from src.preprocessing.extract_scene import REFLECTANCE_BANDS, write_scene_cogs
    from src.preprocessing.extraction_batch import output_keys
    from src.preprocessing.radiometry import convert_dn_to_reflectance, parameters_for_band, parse_l2a_radiometry_metadata
    from src.preprocessing.read_strategy import build_vsizip_vsis3_path, find_band_inner_paths, vsis3_credentials
    from src.preprocessing.spatial import grid_from_bounds, resample_array
    from src.storage.backends import B2Backend, RangeReadFile
    from src.utils.io import load_config

    b2, compute, preprocessing = load_config("b2"), load_config("compute"), load_config("preprocessing")["extraction"]
    bucket, endpoint = b2["bucket"], b2["endpoint_url"]
    key_id, app_key = os.environ["B2_KEY_ID"], os.environ["B2_APPLICATION_KEY"]
    client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=key_id, aws_secret_access_key=app_key)
    backend = B2Backend(endpoint, bucket, key_id=key_id, application_key=app_key, client=client)
    selected_key = f"{compute['b2_output_prefixes']['manifests']}selected_scenes.jsonl"
    rows = [json.loads(line) for line in client.get_object(Bucket=bucket, Key=selected_key)["Body"].read().decode().splitlines() if line]
    selected = [row for row in rows if row.get("selected", True)]
    if scene_override is None:
        scene = sorted(selected, key=lambda r: (int(r["epoch"]), r["selection_rank"]))[0]
    else:
        selected_by_key = {row["object_key"]: row for row in selected}
        requested_key = scene_override.get("object_key")
        if requested_key not in selected_by_key:
            raise RuntimeError("Worker input is not in the approved selected-scene manifest")
        scene = selected_by_key[requested_key]
    scene_id = scene.get("scene_id") or scene.get("product_id")
    if not scene_id:
        raise RuntimeError("Selected scene lacks a stable scene identifier")
    object_key = scene["object_key"]
    epoch = int(scene["epoch"])
    info = backend.stat(object_key)
    keys = output_keys(
        compute["b2_output_prefixes"]["processed"], scene,
        contract_version=preprocessing["contract_version"],
    )
    reflectance_key, scl_key = keys.reflectance, keys.scl
    existing = {}
    for output_key in (reflectance_key, scl_key):
        try:
            head = client.head_object(Bucket=bucket, Key=output_key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in {"404", "NoSuchKey", "NotFound"}:
                raise
            existing[output_key] = None
        else:
            existing[output_key] = head

    if any(existing.values()) and not all(existing.values()):
        raise RuntimeError(
            "Pilot has a partial output pair; refusing to overwrite or continue until the "
            f"state is reviewed: {existing}"
        )
    if all(existing.values()):
        target_shape = (
            int(preprocessing["output_height"]),
            int(preprocessing["output_width"]),
        )
        with vsis3_credentials(key_id, app_key, endpoint):
            with rasterio.open(f"/vsis3/{bucket}/{reflectance_key}") as src:
                if src.shape != target_shape or src.count != 6 or src.nodata != -9999.0:
                    raise RuntimeError("Existing remote reflectance COG validation failed")
                if src.tags().get("scene_id") != scene_id:
                    raise RuntimeError("Existing remote reflectance provenance validation failed")
            with rasterio.open(f"/vsis3/{bucket}/{scl_key}") as src:
                if src.shape != target_shape or src.count != 1 or src.nodata != 0:
                    raise RuntimeError("Existing remote SCL COG validation failed")
                if src.tags().get("scene_id") != scene_id:
                    raise RuntimeError("Existing remote SCL provenance validation failed")
        result = {
            "scene_id": scene_id,
            "epoch": epoch,
            "source_key": object_key,
            "outputs": {
                "reflectance": {
                    "key": reflectance_key,
                    "bytes": int(existing[reflectance_key]["ContentLength"]),
                },
                "scl": {
                    "key": scl_key,
                    "bytes": int(existing[scl_key]["ContentLength"]),
                },
            },
            "remote_reopen_validated": True,
            "resumed_without_overwrite": True,
        }
        print(json.dumps(result, indent=2))
        return result

    boundary = gpd.read_file(io.BytesIO(client.get_object(Bucket=bucket, Key="vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson")["Body"].read())).to_crs("EPSG:32644")
    target_bounds = tuple(preprocessing["output_bounds"])
    target_transform, width, height = grid_from_bounds(target_bounds, preprocessing["pixel_size_m"])
    target_shape = (height, width)
    inside = geometry_mask(boundary.geometry, out_shape=target_shape, transform=target_transform, invert=True)
    paths = find_band_inner_paths(backend, object_key, info.size_bytes)
    with zipfile.ZipFile(RangeReadFile(backend, object_key, info.size_bytes)) as archive:
        names = [name for name in archive.namelist() if name.endswith("/MTD_MSIL2A.xml")]
        metadata = parse_l2a_radiometry_metadata(archive.read(names[0]))

    arrays = []
    band_offsets = {}
    with vsis3_credentials(key_id, app_key, endpoint):
        for band in REFLECTANCE_BANDS:
            with rasterio.open(build_vsizip_vsis3_path(bucket, object_key, paths[band])) as src:
                window = from_bounds(*target_bounds, transform=src.transform).round_offsets().round_lengths()
                dn = src.read(1, window=window)
                source_transform, source_crs = src.window_transform(window), src.crs
            offset, quantification = parameters_for_band(metadata, band)
            band_offsets[band] = offset
            converted, _ = convert_dn_to_reflectance(dn, offset=offset, quantification_value=quantification)
            if band in {"B11", "B12"}:
                converted = resample_array(
                    converted, src_transform=source_transform, src_crs=source_crs,
                    dst_transform=target_transform, dst_crs="EPSG:32644", dst_shape=target_shape,
                    method="bilinear", src_nodata=-9999.0, dst_nodata=-9999.0, dst_dtype="float32",
                )
            if converted.shape != target_shape:
                raise RuntimeError(f"{band}: extracted shape {converted.shape} != {target_shape}")
            converted[~inside] = -9999.0
            arrays.append(converted)
        with rasterio.open(build_vsizip_vsis3_path(bucket, object_key, paths["SCL"])) as src:
            window = from_bounds(*target_bounds, transform=src.transform).round_offsets().round_lengths()
            source = src.read(1, window=window)
            scl = resample_array(
                source, src_transform=src.window_transform(window), src_crs=src.crs,
                dst_transform=target_transform, dst_crs="EPSG:32644", dst_shape=target_shape,
                method="nearest", src_nodata=0, dst_nodata=0, dst_dtype="uint8",
            )
    scl[~inside] = 0
    reflectance = np.stack(arrays).astype("float32", copy=False)

    with tempfile.TemporaryDirectory() as temp_dir:
        reflectance_path = Path(temp_dir) / "reflectance.tif"
        scl_path = Path(temp_dir) / "scl.tif"
        validation = write_scene_cogs(
            reflectance, scl, transform=target_transform, crs="EPSG:32644",
            reflectance_path=reflectance_path, scl_path=scl_path, scene_id=scene_id,
            contract_version=preprocessing["contract_version"],
            source_object_key=object_key, source_size_bytes=info.size_bytes,
            source_etag=info.etag or "", processing_baseline=metadata.processing_baseline,
            quantification_value=metadata.quantification_value,
            band_offsets=band_offsets,
        )
        client.upload_file(str(reflectance_path), bucket, reflectance_key)
        client.upload_file(str(scl_path), bucket, scl_key)

    for name, output_key in (("reflectance", reflectance_key), ("scl", scl_key)):
        head = client.head_object(Bucket=bucket, Key=output_key)
        if head["ContentLength"] != validation[name]["bytes"]:
            raise RuntimeError(f"Remote size mismatch for {output_key}")
    with vsis3_credentials(key_id, app_key, endpoint):
        with rasterio.open(f"/vsis3/{bucket}/{reflectance_key}") as src:
            if src.shape != target_shape or src.count != 6 or src.nodata != -9999.0:
                raise RuntimeError("Remote reflectance COG reopen validation failed")
            tags = src.tags()
            if (
                tags.get("scene_id") != scene_id
                or tags.get("contract_version") != preprocessing["contract_version"]
                or tags.get("source_object_key") != object_key
            ):
                raise RuntimeError("Remote reflectance provenance tag validation failed")
        with rasterio.open(f"/vsis3/{bucket}/{scl_key}") as src:
            if src.shape != target_shape or src.count != 1 or src.nodata != 0:
                raise RuntimeError("Remote SCL COG reopen validation failed")
            tags = src.tags()
            if (
                tags.get("scene_id") != scene_id
                or tags.get("contract_version") != preprocessing["contract_version"]
                or tags.get("source_object_key") != object_key
            ):
                raise RuntimeError("Remote SCL provenance tag validation failed")
    result = {
        "scene_id": scene_id, "epoch": epoch, "source_key": object_key,
        "outputs": {"reflectance": {"key": reflectance_key, **validation["reflectance"]},
                    "scl": {"key": scl_key, **validation["scl"]}},
        "remote_reopen_validated": True,
        "contract_version": preprocessing["contract_version"],
        "source_identity": {"size_bytes": info.size_bytes, "etag": info.etag},
        "radiometry": {
            "processing_baseline": metadata.processing_baseline,
            "quantification_value": metadata.quantification_value,
            "band_offsets": band_offsets,
        },
    }
    print(json.dumps(result, indent=2))
    return result


@app.function(secrets=[b2_secret], timeout=300)
def plan_phase3_part6_indices() -> dict:
    """Metadata-only Part 3.6 plan: frozen sources and all-version collision checks."""
    import json
    import os

    import boto3

    from src.preprocessing.indices import INDEX_FORMULAS, IndexPolicy
    from src.utils.io import load_config

    b2, compute = load_config("b2"), load_config("compute")
    preprocessing, temporal = load_config("preprocessing"), load_config("temporal")
    policy_config = preprocessing["indices"]
    IndexPolicy.from_mapping(policy_config)
    epochs = temporal["epochs"]
    if epochs != [2018, 2020, 2022, 2024]:
        raise RuntimeError("Part 3.6 requires the approved four-epoch source contract")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
    )
    bucket = b2["bucket"]

    def versions_for(key: str) -> list[dict]:
        found = []
        for page in client.get_paginator("list_object_versions").paginate(
            Bucket=bucket, Prefix=key
        ):
            found.extend(
                item for group in ("Versions", "DeleteMarkers")
                for item in page.get(group, []) if item.get("Key") == key
            )
        return found

    prefix = compute["b2_output_prefixes"]["processed"]
    report_key = (
        f"{compute['b2_output_prefixes']['manifests']}"
        f"indices_manifest.contract-{policy_config['contract_version']}.jsonl"
    )
    planned_epochs, collisions, source_bytes = [], [], 0
    for epoch in epochs:
        source_key = (
            f"{prefix}sentinel2/composites/contract-"
            f"{policy_config['source_composite_contract']}/{epoch}/composite.tif"
        )
        versions = versions_for(source_key)
        if len(versions) != 1 or not versions[0].get("IsLatest"):
            raise RuntimeError(f"{epoch}: source must have exactly one live version")
        head = client.head_object(Bucket=bucket, Key=source_key)
        expected_hash = policy_config["source_composite_sha256"][epoch]
        if head.get("Metadata", {}).get("sha256") != expected_hash:
            raise RuntimeError(f"{epoch}: source hash metadata differs from audited checkpoint")
        outputs = {}
        for name in INDEX_FORMULAS:
            key = (f"{prefix}sentinel2/indices/contract-"
                   f"{policy_config['contract_version']}/{epoch}/{name}.tif")
            existing = versions_for(key)
            outputs[name] = {"key": key, "version_count": len(existing),
                             "absent": not existing}
            if existing:
                collisions.append(key)
        size = int(head["ContentLength"])
        source_bytes += size
        planned_epochs.append({
            "epoch": epoch,
            "source": {"key": source_key, "bytes": size, "sha256": expected_hash,
                       "version_id": head.get("VersionId")},
            "outputs": outputs,
        })
    manifest_versions = versions_for(report_key)
    if manifest_versions:
        collisions.append(report_key)
    extraction = preprocessing["extraction"]
    raw_bytes = int(extraction["output_width"]) * int(extraction["output_height"]) * 4
    result = {
        "read_only": True, "pixel_data_read": False, "b2_writes": False,
        "source_compressed_bytes": source_bytes,
        "epoch_count": len(epochs), "raster_output_count": len(epochs) * len(INDEX_FORMULAS),
        "raw_output_bytes_per_index": raw_bytes,
        "raw_output_bytes_total": raw_bytes * len(epochs) * len(INDEX_FORMULAS),
        "manifest": {"key": report_key, "absent": not manifest_versions},
        "all_outputs_absent": not collisions,
        "collision_keys": collisions,
        "policy": policy_config,
        "epochs": planned_epochs,
    }
    print(json.dumps(result, indent=2))
    return result


@app.function(secrets=[b2_secret], timeout=7200, cpu=2.0, memory=4096, max_containers=2)
def build_phase3_part6_epoch_indices(item: dict, run_id: str) -> dict:
    """Hash a pinned composite, create/audit five COGs, then publish once."""
    import hashlib
    import json
    import os
    import shutil
    import tempfile

    import boto3
    import rasterio
    from affine import Affine
    from botocore.config import Config

    from src.preprocessing.index_products import (
        object_versions, put_new_object, require_absent,
        sha256_file, validate_index_products, write_index_products,
    )
    from src.preprocessing.indices import INDEX_FORMULAS, IndexPolicy
    from src.storage.guard import check_budget
    from src.utils.io import load_config, resolve_path

    b2, compute = load_config("b2"), load_config("compute")
    preprocessing = load_config("preprocessing")
    config, extraction = preprocessing["indices"], preprocessing["extraction"]
    policy = IndexPolicy.from_mapping(config)
    epoch = int(item["epoch"])
    if epoch not in config["source_composite_sha256"]:
        raise ValueError("unsupported index epoch")
    source = item["source"]
    prefix = compute["b2_output_prefixes"]["processed"]
    expected_source_key = (f"{prefix}sentinel2/composites/contract-"
                           f"{config['source_composite_contract']}/{epoch}/composite.tif")
    if (source["key"] != expected_source_key
            or source["sha256"] != config["source_composite_sha256"][epoch]):
        raise RuntimeError("worker source does not match the approved checkpoint")
    expected_keys = {name: (f"{prefix}sentinel2/indices/contract-"
                            f"{config['contract_version']}/{epoch}/{name}.tif")
                     for name in INDEX_FORMULAS}
    if {name: value["key"] for name, value in item["outputs"].items()} != expected_keys:
        raise RuntimeError("worker output keys differ from the approved namespace")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1, "mode": "standard"},
                      connect_timeout=30, read_timeout=120),
    )
    bucket = b2["bucket"]
    ledger = modal.Dict.from_name("vizag-phase3-indices-3-6-0", create_if_missing=True)
    lock_key = f"epoch:{epoch}"
    if not ledger.put(lock_key, {"status": "running", "run_id": run_id}, skip_if_exists=True):
        raise RuntimeError(f"epoch {epoch}: persistent lock exists; inspect before any retry")

    def check_abort() -> None:
        if ledger.get(f"abort:{run_id}"):
            raise RuntimeError("another epoch failed; batch aborted before further publication")

    try:
        check_abort()
        require_absent(client, bucket, list(expected_keys.values()))
        versions = object_versions(client, bucket, source["key"])
        if (len(versions) != 1 or versions[0].get("VersionId") != source["version_id"]
                or not versions[0].get("IsLatest")):
            raise RuntimeError(f"epoch {epoch}: pinned source version changed")
        pixels = int(extraction["output_width"]) * int(extraction["output_height"])
        # Source TIFFs + two COG copies with overviews + source composite + headroom.
        projected_bytes = int(source["bytes"]) + 5 * pixels * 4 * 4 + 512 * 1024**2
        check_budget(projected_bytes)
        scratch_root = resolve_path("data.staging")
        scratch_root.mkdir(parents=True, exist_ok=True)
        if (projected_bytes > int(compute["execution"]["ephemeral_disk_gb"]) * 1024**3
                or projected_bytes > shutil.disk_usage(scratch_root).free):
            raise RuntimeError("storage guard refused projected index scratch requirement")
        with tempfile.TemporaryDirectory(prefix=f"indices-{epoch}-", dir=scratch_root) as directory:
            from pathlib import Path
            scratch = Path(directory)
            source_path = scratch / "composite.tif"
            response = client.get_object(Bucket=bucket, Key=source["key"], VersionId=source["version_id"])
            digest, downloaded = hashlib.sha256(), 0
            try:
                with source_path.open("xb") as destination:
                    for block in iter(lambda: response["Body"].read(8 * 1024 * 1024), b""):
                        destination.write(block)
                        digest.update(block)
                        downloaded += len(block)
            finally:
                response["Body"].close()
            if downloaded != source["bytes"] or digest.hexdigest() != source["sha256"]:
                raise RuntimeError(f"epoch {epoch}: downloaded source identity mismatch")
            with rasterio.open(source_path) as dataset:
                xmin, _, _, ymax = extraction["output_bounds"]
                resolution = extraction["pixel_size_m"]
                if (dataset.shape != (extraction["output_height"], extraction["output_width"])
                        or dataset.crs.to_string() != extraction["output_crs"]
                        or dataset.transform != Affine(resolution, 0, xmin, 0, -resolution, ymax)
                        or dataset.tags().get("epoch") != str(epoch)
                        or dataset.tags().get("contract_version") != config["source_composite_contract"]
                        or dataset.tags().get("minimum_valid_observations") != str(preprocessing["composite"]["min_valid_observations"])):
                    raise RuntimeError(f"epoch {epoch}: composite grid/provenance mismatch")
            provenance = {
                "contract_version": config["contract_version"], "epoch": str(epoch),
                "source_key": source["key"], "source_sha256": source["sha256"],
                "source_version_id": source["version_id"],
                "source_composite_contract": config["source_composite_contract"],
                "minimum_valid_observations": str(preprocessing["composite"]["min_valid_observations"]),
            }
            paths = {name: scratch / f"{name}.tif" for name in INDEX_FORMULAS}
            identities = write_index_products(
                source_path, paths, policy=policy, provenance=provenance,
                chunk_size=config["chunk_size_pixels"],
            )
            print(json.dumps({"epoch": epoch, "stage": "all_five_local_cogs_validated",
                              "source_sha256_verified": True,
                              "projected_scratch_bytes": projected_bytes}), flush=True)
            check_abort()
            require_absent(client, bucket, list(expected_keys.values()))
            published = {}
            for name in INDEX_FORMULAS:
                check_abort()
                identity, key = identities[name], expected_keys[name]
                with paths[name].open("rb") as body:
                    result = put_new_object(
                        client, bucket, key, body, content_type="image/tiff",
                        metadata={"sha256": identity["sha256"], "contract-version": config["contract_version"],
                                  "epoch": str(epoch), "source-sha256": source["sha256"]},
                    )
                head = client.head_object(Bucket=bucket, Key=key)
                if (head["ContentLength"] != identity["bytes"]
                        or head.get("Metadata", {}).get("sha256") != identity["sha256"]):
                    raise RuntimeError(f"{key}: post-publication metadata identity mismatch")
                version = head.get("VersionId")
                if result.get("VersionId") and version != result["VersionId"]:
                    raise RuntimeError(f"{key}: published version drift")
                published[name] = {"key": key, **identity, "version_id": version}
                print(json.dumps({"epoch": epoch, "index": name, "stage": "published",
                                  "bytes": identity["bytes"]}), flush=True)
            # Download exact published versions, hash bytes, then audit every full-resolution pixel.
            remote_paths = {}
            for name, identity in published.items():
                check_abort()
                versions = object_versions(client, bucket, identity["key"])
                if len(versions) != 1 or versions[0].get("VersionId") != identity["version_id"]:
                    raise RuntimeError(f"{name}: remote audit found a version conflict")
                downloaded_path = scratch / f"{name}.verified.tif"
                remote = client.get_object(Bucket=bucket, Key=identity["key"], VersionId=identity["version_id"])
                try:
                    with downloaded_path.open("xb") as destination:
                        for block in iter(lambda: remote["Body"].read(8 * 1024 * 1024), b""):
                            destination.write(block)
                finally:
                    remote["Body"].close()
                if (downloaded_path.stat().st_size != identity["bytes"]
                        or sha256_file(downloaded_path) != identity["sha256"]):
                    raise RuntimeError(f"{name}: independent published-byte hash mismatch")
                remote_paths[name] = downloaded_path
            pixel_audit = validate_index_products(
                source_path, remote_paths, policy=policy, provenance=provenance,
            )
            for name, counts in pixel_audit.items():
                for metric, value in counts.items():
                    if published[name]["statistics"][metric] != value:
                        raise RuntimeError(f"{name}: published QC mismatch for {metric}")
                published[name]["remote_sha256_verified"] = True
                published[name]["remote_pixel_audit"] = True
            result = {"epoch": epoch, "contract_version": config["contract_version"],
                      "source": source, "source_sha256_verified": True,
                      "outputs": published, "provenance": provenance,
                      "remote_full_resolution_audit": True}
            ledger.put(lock_key, {"status": "complete", "run_id": run_id, "result": result})
            print(json.dumps(result), flush=True)
            return result
    except Exception as error:
        ledger.put(f"abort:{run_id}", {"epoch": epoch, "error_type": type(error).__name__})
        ledger.put(lock_key, {"status": "failed", "run_id": run_id,
                              "error_type": type(error).__name__, "error": str(error)})
        raise


@app.function(secrets=[b2_secret], timeout=600)
def publish_phase3_part6_manifest(results: list[dict]) -> dict:
    """Publish one immutable QC manifest only after all 20 outputs pass audits."""
    import hashlib
    import json
    import os

    import boto3
    from botocore.config import Config

    from src.preprocessing.index_products import object_versions, put_new_object
    from src.preprocessing.indices import INDEX_FORMULAS
    from src.utils.io import load_config

    compute, b2 = load_config("compute"), load_config("b2")
    config = load_config("preprocessing")["indices"]
    if sorted(int(row["epoch"]) for row in results) != [2018, 2020, 2022, 2024]:
        raise RuntimeError("manifest requires one successful result per approved epoch")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1, "mode": "standard"}),
    )
    for row in results:
        if (not row.get("remote_full_resolution_audit")
                or set(row["outputs"]) != set(INDEX_FORMULAS)):
            raise RuntimeError("refusing manifest: incomplete production audits")
        for name, info in row["outputs"].items():
            if not info.get("remote_sha256_verified") or not info.get("remote_pixel_audit"):
                raise RuntimeError(f"{name}: missing production validation flag")
            versions = object_versions(client, b2["bucket"], info["key"])
            if len(versions) != 1 or versions[0].get("VersionId") != info["version_id"]:
                raise RuntimeError(f"{name}: version drift before manifest publication")
    body = ("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":"))
                      for row in sorted(results, key=lambda row: row["epoch"])) + "\n").encode()
    digest = hashlib.sha256(body).hexdigest()
    key = (f"{compute['b2_output_prefixes']['manifests']}"
           f"indices_manifest.contract-{config['contract_version']}.jsonl")
    response = put_new_object(
        client, b2["bucket"], key, body,
        content_type="application/x-ndjson",
        metadata={"sha256": digest, "contract-version": config["contract_version"]},
    )
    readback = client.get_object(Bucket=b2["bucket"], Key=key)
    try:
        received = readback["Body"].read()
    finally:
        readback["Body"].close()
    if received != body:
        raise RuntimeError("published index manifest byte comparison failed")
    versions = object_versions(client, b2["bucket"], key)
    if len(versions) != 1:
        raise RuntimeError("published index manifest has unexpected historical versions")
    result = {"key": key, "bytes": len(body), "sha256": digest,
              "version_id": response.get("VersionId"), "created": True,
              "epoch_count": 4, "index_count": 20,
              "output_bytes": sum(v["bytes"] for row in results for v in row["outputs"].values()),
              "epochs": results}
    print(json.dumps(result), flush=True)
    return result


def _audit_phase3_part7_storage(include_manifest_rows: bool = False) -> dict:
    """Read metadata and two pinned manifests; no raster GET, PUT or eviction."""
    import json
    import os
    import platform

    import boto3
    from botocore.config import Config

    from src.storage.archive_audit import audit_archive, reject_non_read_api
    from src.utils.io import load_config, resolve_path

    if platform.python_version_tuple()[:2] != ("3", "12"):
        raise RuntimeError("Archive audit requires the configured remote Python 3.12")
    b2, compute = load_config("b2"), load_config("compute")
    config, preprocessing = load_config("archive"), load_config("preprocessing")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"],
        aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=45),
    )
    client.meta.events.register("before-call.s3.*", reject_non_read_api)
    prefixes = compute["b2_output_prefixes"]
    manifests = []
    for name in ("extraction", "indices"):
        item = dict(config["manifests"][name])
        item["key"] = prefixes["manifests"] + item.pop("filename")
        manifests.append(item)
    composite_root = (f"{prefixes['processed']}sentinel2/composites/"
                      f"contract-{preprocessing['composite']['contract_version']}/")
    composites = [
        {"key": f"{composite_root}{epoch}/{name}.tif", **identity}
        for epoch, products in config["composites"].items()
        for name, identity in products.items()
    ]
    print(json.dumps({"stage": "read_only_storage_audit_started",
                      "python": platform.python_version(), "raster_bytes_to_download": 0,
                      "manifest_bytes_to_read": sum(i["bytes"] for i in manifests)}), flush=True)
    result = audit_archive(
        client, bucket=b2["bucket"], root=prefixes["root"],
        manifest_specs=manifests, composite_specs=composites,
        expected_epochs=load_config("temporal")["epochs"],
        index_names=preprocessing["indices"]["names"],
        expected_scene_count=config["expected_scene_count"],
        manifest_read_limit_bytes=config["manifest_read_limit_bytes"],
        include_manifest_rows=include_manifest_rows,
    )
    result["remote_python"] = platform.python_version()
    result["audit_container_scratch"] = {}
    for dotted in ("data.staging", "data.processed", "data.derived"):
        path = resolve_path(dotted)
        files = [p for p in path.rglob("*") if p.is_file()] if path.exists() else []
        result["audit_container_scratch"][dotted] = {
            "exists": path.exists(), "files": len(files),
            "bytes": sum(p.stat().st_size for p in files),
        }
    return result


@app.function(secrets=[b2_secret], timeout=600, cpu=0.25, memory=512,
              max_containers=1, retries=0)
def audit_phase3_part7_storage() -> dict:
    return _audit_phase3_part7_storage()


@app.function(secrets=[b2_secret], timeout=600, cpu=0.25, memory=512,
              max_containers=1, retries=0)
def publish_phase3_part7_archive(payloads: list[dict]) -> dict:
    """Publish only the explicitly approved small snapshots; manifest last."""
    import os
    import platform
    import uuid

    import boto3
    from botocore.config import Config

    from src.storage.archive_publish import (
        publish_archive, reject_non_archive_api, validate_payloads,
    )
    from src.utils.io import load_config

    policy = load_config("archive_publication")
    validate_payloads(payloads, policy)
    ledger = modal.Dict.from_name(policy["reservation_name"], create_if_missing=True)
    lock_key, run_id = policy["reservation_key"], uuid.uuid4().hex
    if not ledger.put(lock_key, {"status": "reserved", "run_id": run_id}, skip_if_exists=True):
        raise RuntimeError("Archive reservation already exists; inspect before any retry")

    def checkpoint(state):
        ledger.put(lock_key, {"run_id": run_id, **state})

    try:
        audit = _audit_phase3_part7_storage()
        b2, compute = load_config("b2"), load_config("compute")
        client = boto3.client(
            "s3", endpoint_url=b2["endpoint_url"],
            aws_access_key_id=os.environ["B2_KEY_ID"],
            aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
            config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=45),
        )
        client.meta.events.register("before-call.s3.*", reject_non_archive_api)
        result = publish_archive(
            client, bucket=b2["bucket"], root=compute["b2_output_prefixes"]["root"],
            payloads=payloads, policy=policy, audit=audit, checkpoint=checkpoint,
        )
        result["remote_python"] = platform.python_version()
        ledger.put(lock_key, {"status": "complete", "run_id": run_id, "result": result})
        return result
    except Exception as exc:
        current = ledger.get(lock_key) or {}
        ledger.put(lock_key, {**current, "status": "failed", "error": str(exc)})
        raise


@app.function(secrets=[b2_secret], timeout=1800, cpu=2.0, memory=4096,
              max_containers=1, retries=0)
def run_phase3_gate_review() -> dict:
    """Approved native QC only; no original rewrite and no automatic gate approval."""
    import io
    import json
    import os
    import platform
    import shutil
    import tempfile
    import uuid
    from pathlib import Path

    import boto3
    import geopandas as gpd
    import rasterio
    from botocore.config import Config
    from rio_cogeo.cogeo import cog_validate

    from src.preprocessing.gate_review import review_epoch, render_epoch_png
    from src.preprocessing.gate_review_job import (
        verify_source_pins, output_keys, pin_small_object, download_pinned, reports, publish_review,
    )
    from src.preprocessing.indices import IndexPolicy
    from src.storage.archive_publish import require_new_keys, reject_non_archive_api
    from src.storage.guard import check_budget, current_staging_bytes
    from src.utils.io import load_config, resolve_path

    config, b2 = load_config("gate_review"), load_config("b2")
    preprocessing = load_config("preprocessing")
    policy = IndexPolicy.from_mapping(preprocessing["indices"])
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"], aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=60),
    )
    client.meta.events.register("before-call.s3.*", reject_non_archive_api)
    ledger = modal.Dict.from_name(config["reservation_name"], create_if_missing=True)
    lock_key, run_id = config["reservation_key"], uuid.uuid4().hex
    if not ledger.put(lock_key, {"status": "reserved", "run_id": run_id}, skip_if_exists=True):
        raise RuntimeError("QC reservation exists; inspect before an explicitly approved retry")

    def checkpoint(state):
        ledger.put(lock_key, {"run_id": run_id, **state})

    try:
        audit = _audit_phase3_part7_storage(include_manifest_rows=True)
        verify_source_pins(audit, config)
        require_new_keys(client, b2["bucket"], list(output_keys(config).values()))
        boundary_body, boundary_info = pin_small_object(
            client, b2["bucket"], config["boundary_key"], config["maximum_boundary_bytes"],
        )
        feasibility_body, feasibility_info = pin_small_object(
            client, b2["bucket"], config["feasibility_key"], config["feasibility_bytes"],
            expected_size=config["feasibility_bytes"],
        )
        input_bytes = audit["manifest_bytes_read"] + len(boundary_body) + len(feasibility_body)
        if input_bytes + config["expected_raster_bytes"] > config["maximum_input_bytes"]:
            raise RuntimeError("QC input byte budget exceeded before raster reads")
        boundary = gpd.read_file(io.BytesIO(boundary_body)).to_crs(preprocessing["extraction"]["output_crs"])
        if boundary.empty or not boundary.geometry.is_valid.all():
            raise RuntimeError("Buffered QC boundary is empty or invalid")
        geometry = boundary.geometry.union_all()
        expected = {r["epoch"]: r for r in audit["manifest_rows"][1]}
        staging = resolve_path("data.staging")
        staging.mkdir(parents=True, exist_ok=True)
        blobs, epochs = {}, []
        for epoch in sorted(expected):
            items = [i for i in config["sources"] if i["epoch"] == epoch]
            projected = sum(i["bytes"] for i in items) + config["maximum_new_output_bytes"] + 64*1024*1024
            check_budget(projected)
            scratch_cap = int(load_config("storage")["staging"]["max_gb"] * 1024**3)
            if current_staging_bytes()+projected > scratch_cap or shutil.disk_usage(staging).free < projected:
                raise RuntimeError("QC scratch guard refused; no cleanup is performed to make room")
            with tempfile.TemporaryDirectory(prefix=f"gate-review-{epoch}-", dir=staging) as scratch:
                paths = {}
                for item in items:
                    path = Path(scratch) / f"{item['role']}.tif"
                    input_bytes += download_pinned(client, b2["bucket"], item, path)
                    if input_bytes > config["maximum_input_bytes"]:
                        raise RuntimeError("QC input budget exceeded")
                    valid, errors, warnings = cog_validate(str(path), strict=True, quiet=True)
                    if not valid:
                        raise RuntimeError(f"QC input is not a strict COG: {item['key']}: {errors}")
                    with rasterio.open(path) as ds:
                        grid = preprocessing["extraction"]
                        if (ds.width != grid["output_width"] or ds.height != grid["output_height"]
                                or ds.crs.to_string() != grid["output_crs"]
                                or tuple(ds.bounds) != tuple(grid["output_bounds"])):
                            raise RuntimeError("QC input differs from frozen production grid")
                    paths[item["role"]] = path
                stats = {name: item["statistics"] for name, item in expected[epoch]["outputs"].items()}
                summary, previews = review_epoch(paths, geometry=geometry, policy=policy, config=config,
                                                expected_statistics=stats)
                summary["epoch"] = epoch
                name = f"qc_{epoch}.png"
                image = render_epoch_png(epoch, summary, previews, geometry=geometry, config=config)
                if len(image) > config["file_caps"][name]:
                    raise RuntimeError("QC image exceeds approved output cap")
                blobs[name] = image
                epochs.append(summary)
            checkpoint({"status": "epoch_validated", "epoch": epoch, "input_bytes": input_bytes})
            print(json.dumps({"epoch": epoch, "stage": "native_review_complete",
                              "coverage": summary["coverage_fraction"],
                              "unique_outlier_pixels": summary["unique_outlier_pixels"],
                              "png_bytes": len(image)}), flush=True)
        auxiliary = [*audit["manifests"], boundary_info, feasibility_info]
        blobs.update(reports(epochs, config=config, sources=config["sources"], auxiliary=auxiliary,
                             feasibility_text=feasibility_body.decode("utf-8"), input_bytes=input_bytes))
        result, local_blobs = publish_review(
            client, bucket=b2["bucket"], blobs=blobs, config=config, source_records=config["sources"],
            auxiliary=auxiliary, input_bytes=input_bytes, checkpoint=checkpoint,
        )
        result["remote_python"] = platform.python_version()
        result["epoch_summary"] = [{"epoch": e["epoch"], "coverage": e["coverage_fraction"],
                                     "unique_outlier_pixels": e["unique_outlier_pixels"]} for e in epochs]
        ledger.put(lock_key, {"status": "complete", "run_id": run_id, "result": result})
        return {**result, "local_payloads": local_blobs}
    except Exception as exc:
        current = ledger.get(lock_key) or {}
        ledger.put(lock_key, {**current, "status": "failed", "error": str(exc)})
        raise


@app.function(secrets=[b2_secret], timeout=600, cpu=1.0, memory=2048,
              max_containers=1, retries=0)
def build_phase4_part1_grid() -> dict:
    """Approved geometry-only job. Restore one pinned boundary; never read imagery."""
    import json
    import os
    import platform
    import tempfile
    import uuid
    from pathlib import Path

    import boto3
    from botocore.config import Config

    from src.grid.build_grid import boundary_from_bytes, build_grid, validate_grid, render_preview
    from src.grid.grid_job import restore_boundary, publish_grid
    from src.storage.archive_publish import require_new_keys, reject_non_archive_api
    from src.storage.guard import check_budget
    from src.utils.io import load_config, resolve_path

    config, grid_config, b2 = load_config("grid_build"), load_config("grid"), load_config("b2")
    if grid_config["cell_size_m"] != 500 or grid_config.get("exclusions"):
        raise ValueError("Approved grid requires 500 m cells and no exclusions")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"], aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=60),
    )
    client.meta.events.register("before-call.s3.*", reject_non_archive_api)
    ledger = modal.Dict.from_name(config["reservation_name"], create_if_missing=True)
    lock_key, run_id = config["reservation_key"], uuid.uuid4().hex
    if not ledger.put(lock_key, {"status": "reserved", "run_id": run_id}, skip_if_exists=True):
        raise RuntimeError("Grid reservation exists; inspect before any explicitly approved retry")

    def checkpoint(state):
        ledger.put(lock_key, {"run_id": run_id, **state})

    try:
        require_new_keys(client, b2["bucket"], list(config["outputs"].values()))
        check_budget(config["source"]["bytes"]+config["maximum_new_bytes"])
        staging = resolve_path("data.staging")
        staging.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix="grid-4-1-", dir=staging))
        # Preserve scratch on any failure; there is no explicit delete/cleanup.
        body = restore_boundary(client, b2["bucket"], config["source"], scratch / "boundary.geojson")
        boundary = boundary_from_bytes(body, config["metric_crs"])
        grid, candidates = build_grid(boundary, size=grid_config["cell_size_m"], config=config)
        report, geojson = validate_grid(grid, boundary, size=grid_config["cell_size_m"], config=config)
        report.update({"candidate_squares": candidates, "source_boundary": config["source"],
                       "remote_python": platform.python_version()})
        print("GRID_VALIDATION="+json.dumps(report, sort_keys=True), flush=True)
        blobs = {"analysis_grid.geojson": geojson,
                 "grid_validation.json": (json.dumps(report, indent=2, allow_nan=False)+"\n").encode(),
                 "grid_preview.png": render_preview(grid, boundary)}
        result, payloads = publish_grid(client, bucket=b2["bucket"], config=config,
                                        blobs=blobs, checkpoint=checkpoint)
        result["validation"] = report
        result["remote_python"] = platform.python_version()
        checkpoint({"status": "complete", "result": result})
        return {**result, "local_payloads": payloads}
    except Exception as exc:
        current = ledger.get(lock_key) or {}
        ledger.put(lock_key, {**current, "status": "failed", "error": str(exc)})
        raise


@app.function(secrets=[b2_secret], timeout=300, cpu=0.5, memory=1024,
              max_containers=1, retries=0)
def preflight_phase4_part2_sources() -> dict:
    """Approved 4.2a: small pinned manifests plus metadata, never raster payloads."""
    import json
    import os
    import platform

    import boto3
    from botocore.config import Config

    from src.grid.feature_preflight import (
        read_pinned_small, pin_dem_metadata, validate_manifests, build_report, render_markdown,
    )
    from src.utils.io import load_config

    config, b2 = load_config("feature_preflight"), load_config("b2")
    gate = load_config("gate_review")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"], aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=45),
    )

    def reject_non_preflight_api(model, **kwargs):
        if model.name not in {"ListObjectVersions", "HeadObject", "GetObject"}:
            raise RuntimeError(f"Feature preflight refused API operation: {model.name}")

    client.meta.events.register("before-call.s3.*", reject_non_preflight_api)
    grid_body = read_pinned_small(client, b2["bucket"], config["grid_manifest"])
    index_body = read_pinned_small(client, b2["bucket"], config["index_manifest"])
    read_pinned_small(client, b2["bucket"], config["boundary"])
    index_roles = {"ndvi", "ndbi", "ndwi", "mndwi", "bsi"}
    expected = [item for item in gate["sources"] if item["role"] in index_roles]
    grid_item, index_rows = validate_manifests(grid_body, index_body, expected)
    dem = pin_dem_metadata(client, b2["bucket"], config["dem_sources"])
    report = build_report(config, grid_item, index_rows, dem, platform.python_version())
    json_body = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    markdown_body = render_markdown(report)
    if len(json_body)+len(markdown_body) > config["maximum_local_output_bytes"]:
        raise RuntimeError("Feature preflight local output budget exceeded")
    return {**report, "local_payloads": {
        config["local_outputs"]["json"]: json_body,
        config["local_outputs"]["markdown"]: markdown_body,
    }}


@app.function(secrets=[b2_secret], timeout=600, cpu=1.0, memory=2048,
              max_containers=1, retries=0)
def validate_phase4_dem_sources() -> dict:
    """Approved full-byte hash/header/value gate for only two pinned DEM COGs."""
    import json
    import os
    import platform
    import tempfile
    from pathlib import Path

    import boto3
    from botocore.config import Config

    from src.grid.dem_validation import (
        download_and_hash, inspect_dem, require_expected_hash, validate_pair, render_markdown,
    )
    from src.storage.guard import check_budget
    from src.utils.io import load_config, resolve_path

    config, b2 = load_config("dem_validation"), load_config("b2")
    if sum(item["bytes"] for item in config["sources"]) != config["maximum_input_bytes"]:
        raise RuntimeError("DEM source list differs from approved byte budget")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"], aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=90),
    )

    def reject_non_validation_api(model, **kwargs):
        if model.name not in {"ListObjectVersions", "HeadObject", "GetObject"}:
            raise RuntimeError(f"DEM validation refused API operation: {model.name}")

    client.meta.events.register("before-call.s3.*", reject_non_validation_api)
    check_budget(config["maximum_input_bytes"])
    staging = resolve_path("data.staging")
    staging.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="dem-4-2-gate-", dir=staging))
    records = []
    for position, spec in enumerate(config["sources"]):
        path = scratch/f"dem-{position}.tif"
        digest = download_and_hash(client, b2["bucket"], spec, path)
        record = inspect_dem(path, spec, config)
        record["sha256"] = digest
        require_expected_hash(record, spec)
        records.append(record)
    report = validate_pair(records, config)
    report["remote_python"] = platform.python_version()
    json_body = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    markdown_body = render_markdown(report)
    if len(json_body)+len(markdown_body) > config["maximum_local_output_bytes"]:
        raise RuntimeError("DEM validation local output budget exceeded")
    return {**report, "local_payloads": {
        config["local_outputs"]["json"]: json_body,
        config["local_outputs"]["markdown"]: markdown_body,
    }}


@app.function(secrets=[b2_secret], timeout=600, cpu=1.0, memory=2048,
              max_containers=1, retries=0)
def probe_phase4_dem_headers() -> dict:
    """Evidence-only headers and hashes for the two exact pinned DEM versions."""
    import json
    import os
    import platform
    import tempfile
    from pathlib import Path

    import boto3
    from botocore.config import Config

    from src.grid.dem_validation import (
        download_and_hash, inspect_dem_header, render_header_probe_markdown,
    )
    from src.storage.guard import check_budget
    from src.utils.io import load_config, resolve_path

    config, b2 = load_config("dem_validation"), load_config("b2")
    if sum(item["bytes"] for item in config["sources"]) != config["maximum_input_bytes"]:
        raise RuntimeError("DEM probe source list differs from approved byte budget")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"], aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=90),
    )

    def reject_non_probe_api(model, **kwargs):
        if model.name not in {"ListObjectVersions", "HeadObject", "GetObject"}:
            raise RuntimeError(f"DEM header probe refused API operation: {model.name}")

    client.meta.events.register("before-call.s3.*", reject_non_probe_api)
    check_budget(config["maximum_input_bytes"])
    staging = resolve_path("data.staging")
    staging.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="dem-4-2-header-probe-", dir=staging))
    records = []
    for position, spec in enumerate(config["sources"]):
        path = scratch/f"dem-{position}.tif"
        digest = download_and_hash(client, b2["bucket"], spec, path)
        record = inspect_dem_header(path, spec)
        record["sha256"] = digest
        records.append(record)
    report = {"status": "observed", "part": "4.2-dem-header-probe",
              "contract_version": config["contract_version"],
              "input_bytes": config["maximum_input_bytes"], "b2_writes": 0,
              "part4_2b_started": False, "remote_python": platform.python_version(),
              "sources": records}
    json_body = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    markdown_body = render_header_probe_markdown(report)
    if len(json_body)+len(markdown_body) > config["maximum_local_output_bytes"]:
        raise RuntimeError("DEM header probe local output budget exceeded")
    return {**report, "local_payloads": {
        config["probe_outputs"]["json"]: json_body,
        config["probe_outputs"]["markdown"]: markdown_body,
    }}


@app.function(secrets=[b2_secret], timeout=900, cpu=2.0, memory=8192,
              max_containers=1, retries=0)
def run_phase4_feature_aggregation_pilot() -> dict:
    """One pinned 2024 NDVI raster; local evidence only and no B2 writes."""
    import json
    import os
    import platform
    import tempfile
    from pathlib import Path

    import boto3
    from botocore.config import Config

    from src.grid.dem_validation import download_and_hash
    from src.grid.feature_aggregation_pilot import run_pilot, render_markdown
    from src.storage.guard import check_budget
    from src.utils.io import load_config, resolve_path

    config, b2 = load_config("feature_aggregation_pilot"), load_config("b2")
    specs = [config["index"], config["grid"], config["boundary"]]
    if sum(item["bytes"] for item in specs) != config["maximum_input_bytes"]:
        raise RuntimeError("Pilot source list differs from the approved byte budget")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"], aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=120),
    )

    def reject_non_pilot_api(model, **kwargs):
        if model.name not in {"ListObjectVersions", "HeadObject", "GetObject"}:
            raise RuntimeError(f"Feature pilot refused API operation: {model.name}")

    client.meta.events.register("before-call.s3.*", reject_non_pilot_api)
    check_budget(config["maximum_input_bytes"])
    staging = resolve_path("data.staging")
    staging.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="feature-4-2-pilot-", dir=staging))
    paths, hashes = {}, {}
    for name, spec in (("index", config["index"]), ("grid", config["grid"]),
                       ("boundary", config["boundary"])):
        suffix = ".tif" if name == "index" else ".geojson"
        paths[name] = scratch/f"{name}{suffix}"
        hashes[name] = download_and_hash(client, b2["bucket"], spec, paths[name])
        if hashes[name] != spec["sha256"]:
            raise RuntimeError(f"Pilot source SHA-256 mismatch: {spec['key']}")
    report = run_pilot(paths["index"], paths["grid"], paths["boundary"], config)
    report.update({"input_bytes": config["maximum_input_bytes"], "source_hashes": hashes,
                   "remote_python": platform.python_version()})
    json_body = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    markdown_body = render_markdown(report)
    if len(json_body)+len(markdown_body) > config["maximum_local_output_bytes"]:
        raise RuntimeError("Feature pilot local output budget exceeded")
    return {**report, "local_payloads": {
        config["local_outputs"]["json"]: json_body,
        config["local_outputs"]["markdown"]: markdown_body,
    }}


@app.function(secrets=[b2_secret], timeout=3600, cpu=2.0, memory=8192,
              max_containers=1, retries=0)
def run_phase4_feature_aggregation_batch() -> dict:
    """Full provisional 20-index plus terrain batch; create-only publication."""
    import json
    import os
    import platform
    import tempfile
    import uuid
    from pathlib import Path

    import boto3
    import geopandas as gpd
    from botocore.config import Config

    from src.grid.dem_validation import download_and_hash
    from src.grid.feature_aggregation_batch import (
        build_payloads, build_satellite, build_terrain, publish_payloads,
    )
    from src.storage.archive_publish import require_new_keys
    from src.storage.guard import check_budget
    from src.utils.io import load_config, resolve_path

    config, b2 = load_config("feature_aggregation_batch"), load_config("b2")
    gate, dem, pilot = load_config("gate_review"), load_config("dem_validation"), load_config("feature_aggregation_pilot")
    wanted = set(config["roles"])
    indices = sorted((item for item in gate["sources"] if item.get("role") in wanted),
                     key=lambda item: (int(item["epoch"]), item["role"]))
    if (len(indices) != 20 or {(int(i["epoch"]), i["role"]) for i in indices}
            != {(e, r) for e in config["epochs"] for r in config["roles"]}):
        raise RuntimeError("Full batch does not resolve the exact 20 index identities")
    sources = indices + dem["sources"] + [pilot["grid"], pilot["boundary"]]
    if sum(int(item["bytes"]) for item in sources) != config["maximum_input_bytes"]:
        raise RuntimeError("Full batch source bytes differ from approved cap")

    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"], aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=180),
    )
    allowed = {"ListObjectVersions", "HeadObject", "GetObject", "PutObject"}
    def reject_non_batch_api(model, **kwargs):
        if model.name not in allowed:
            raise RuntimeError(f"Feature batch refused API operation: {model.name}")
    client.meta.events.register("before-call.s3.*", reject_non_batch_api)

    ledger = modal.Dict.from_name(config["reservation_name"], create_if_missing=True)
    run_id = uuid.uuid4().hex
    existing = ledger.get(config["reservation_key"])
    allowed_failure = (existing and existing.get("status") == "failed"
                       and existing.get("error_type") == "RuntimeError"
                       and existing.get("error") == "Reprojected DEM seam disagreement exceeds 1 metre")
    if existing and not allowed_failure:
        raise RuntimeError("Feature batch reservation exists; inspect before any retry")
    if allowed_failure:
        ledger.put(config["reservation_key"], {"run_id": run_id, "status": "controlled_resume",
                                               "previous_run_id": existing.get("run_id"),
                                               "previous_error": existing.get("error")})
    elif not ledger.put(config["reservation_key"], {"run_id": run_id, "status": "reserved"}, skip_if_exists=True):
        raise RuntimeError("Feature batch reservation was concurrently created")
    def checkpoint(status, **extra):
        ledger[config["reservation_key"]] = {"run_id": run_id, "status": status, **extra}

    try:
        require_new_keys(client, b2["bucket"], list(config["outputs"].values()))
        check_budget(config["maximum_input_bytes"])
        staging = resolve_path("data.staging"); staging.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix="feature-4-2-full-", dir=staging))
        index_paths, source_hashes = [], {}
        for position, spec in enumerate(indices):
            path = scratch/f"index-{position:02d}.tif"
            digest = download_and_hash(client, b2["bucket"], spec, path)
            if digest != spec["sha256"]:
                raise RuntimeError(f"Index SHA-256 mismatch: {spec['key']}")
            source_hashes[spec["key"]] = digest; index_paths.append((spec, path))
            checkpoint("index_downloaded", completed_indices=position+1)
        dem_paths = []
        for position, spec in enumerate(dem["sources"]):
            path = scratch/f"dem-{position}.tif"; digest = download_and_hash(client, b2["bucket"], spec, path)
            if digest != spec["sha256"]:
                raise RuntimeError(f"DEM SHA-256 mismatch: {spec['key']}")
            source_hashes[spec["key"]] = digest; dem_paths.append(path)
        small_paths = {}
        for name, spec in (("grid", pilot["grid"]), ("boundary", pilot["boundary"])):
            path = scratch/f"{name}.geojson"; digest = download_and_hash(client, b2["bucket"], spec, path)
            if digest != spec["sha256"]:
                raise RuntimeError(f"Small source SHA-256 mismatch: {spec['key']}")
            source_hashes[spec["key"]] = digest; small_paths[name] = path
        checkpoint("sources_verified", source_count=len(sources))
        grid, boundary = gpd.read_file(small_paths["grid"]), gpd.read_file(small_paths["boundary"])
        satellite, summaries = build_satellite(index_paths, grid, boundary, config)
        terrain, terrain_summary = build_terrain(dem_paths, grid, boundary, config)
        payloads, scientific_summary = build_payloads(satellite, terrain, summaries, terrain_summary, grid, config)
        checkpoint("calculated_and_validated", payload_bytes=sum(map(len, payloads.values())))
        result = publish_payloads(client, b2["bucket"], payloads, config)
        result.update({"input_bytes": config["maximum_input_bytes"], "source_count": len(sources),
                       "source_hashes_verified": len(source_hashes), "remote_python": platform.python_version(),
                       "scientific_summary": scientific_summary})
        checkpoint("complete", result=result)
        return result
    except Exception as exc:
        checkpoint("failed", error_type=type(exc).__name__, error=str(exc))
        raise


@app.function(secrets=[b2_secret], timeout=600, cpu=1.0, memory=4096,
              max_containers=1, retries=0)
def review_phase4_feature_aggregation_batch() -> dict:
    """Exact-version read-only scientific review of the completed provisional batch."""
    import hashlib
    import io
    import json
    import os

    import boto3
    import pandas as pd
    from botocore.config import Config

    from src.grid.feature_aggregation import validate_feature_frames
    from src.storage.archive_publish import exact_versions
    from src.utils.io import load_config

    config, b2 = load_config("feature_aggregation_batch"), load_config("b2")
    ledger = modal.Dict.from_name(config["reservation_name"], create_if_missing=False)
    checkpoint = ledger.get(config["reservation_key"])
    if not checkpoint or checkpoint.get("status") != "complete":
        raise RuntimeError("Feature batch completion checkpoint is absent")
    result = checkpoint.get("result", {})
    records = {item["name"]: item for item in result.get("outputs", [])}
    if set(records) != set(config["outputs"]):
        raise RuntimeError("Feature completion checkpoint output set differs from contract")
    client = boto3.client(
        "s3", endpoint_url=b2["endpoint_url"],
        aws_access_key_id=os.environ["B2_KEY_ID"], aws_secret_access_key=os.environ["B2_APPLICATION_KEY"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=20, read_timeout=90),
    )
    def reject_non_review_api(model, **kwargs):
        if model.name not in {"ListObjectVersions", "HeadObject", "GetObject"}:
            raise RuntimeError(f"Feature review refused API operation: {model.name}")
    client.meta.events.register("before-call.s3.*", reject_non_review_api)
    payloads = {}
    for name, record in records.items():
        versions = exact_versions(client, b2["bucket"], record["key"])
        if (len(versions) != 1 or versions[0].get("VersionId") != record["version_id"]
                or not versions[0].get("IsLatest") or int(versions[0].get("Size", -1)) != record["bytes"]):
            raise RuntimeError(f"Feature review version identity mismatch: {name}")
        response = client.get_object(Bucket=b2["bucket"], Key=record["key"], VersionId=record["version_id"])
        stream = response["Body"]
        try:
            body = stream.read(record["bytes"]+1)
        finally:
            stream.close()
        if len(body) != record["bytes"] or hashlib.sha256(body).hexdigest() != record["sha256"]:
            raise RuntimeError(f"Feature review payload hash mismatch: {name}")
        payloads[name] = body
    satellite = pd.read_parquet(io.BytesIO(payloads["satellite_cell_features.parquet"]))
    terrain = pd.read_parquet(io.BytesIO(payloads["terrain_cell_features.parquet"]))
    validate_feature_frames(satellite, terrain, expected_cells=config["expected_cells"],
                            epochs=config["epochs"], roles=config["roles"])
    support_columns = [f"{role}_usable_fraction_of_aoi_pixels" for role in config["roles"]]
    satellite["minimum_index_support"] = satellite[support_columns].min(axis=1)
    terrain_ids = set(terrain.loc[terrain["elevation_mean_m"].notna()
                                  & terrain["slope_mean_degrees"].notna(), "grid_id"])
    thresholds = {}
    for threshold in (0.0, 0.5, 0.8, 0.9, 0.95):
        per_epoch = {}
        for epoch in config["epochs"]:
            frame = satellite[satellite["epoch"] == epoch]
            eligible = frame[(frame["minimum_index_support"] >= threshold)
                             & frame["grid_id"].isin(terrain_ids)]
            per_epoch[str(epoch)] = int(len(eligible))
        all_epochs = satellite.groupby("grid_id")["minimum_index_support"].min()
        thresholds[str(threshold)] = {"per_epoch": per_epoch,
                                      "all_epochs_with_terrain": int(((all_epochs >= threshold)
                                                                      & all_epochs.index.isin(terrain_ids)).sum())}
    review = {"status": "scientific_review_passed_policy_pending",
              "contract_version": config["contract_version"], "outputs_hash_verified": len(payloads),
              "satellite_rows": len(satellite), "terrain_rows": len(terrain),
              "cells_without_terrain": int(config["expected_cells"]-len(terrain_ids)),
              "minimum_support_quantiles": {str(q): float(satellite["minimum_index_support"].quantile(q))
                                             for q in (0, .01, .05, .25, .5, .95, 1)},
              "threshold_counts": thresholds, "b2_writes": 0,
              "map_sha256": hashlib.sha256(payloads["support_maps.png"]).hexdigest()}
    review_body = (json.dumps(review, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
    return {**review, "local_payloads": {
        config["review_outputs"]["json"]: review_body,
        config["review_outputs"]["map"]: payloads["support_maps.png"],
    }}


@app.local_entrypoint()
def main(action: str = "verify") -> None:
    """Dispatch a local control-plane command to a remote Modal function."""
    if action == "verify":
        result = verify_remote_environment.remote()
        print(result)
        return
    if action == "test":
        exit_code = run_regression_tests.remote()
        print({"pytest_exit_code": exit_code})
        return
    if action == "part4-grid-build":
        import hashlib
        import json
        from src.utils.io import load_config, resolve_path
        config = load_config("grid_build")
        directory = resolve_path("phase4_grid_review")
        names = [*config["outputs"], config["local_receipt_name"]]
        if any((directory / name).exists() for name in names):
            raise FileExistsError("Local grid evidence exists; refusing overwrite before remote execution")
        result = build_phase4_part1_grid.remote()
        payloads = result.pop("local_payloads")
        if set(payloads) != set(config["outputs"]):
            raise RuntimeError("Local grid payload set differs from approved output names")
        identities = {item["name"]: item for item in result["outputs"]}
        for name, body in payloads.items():
            if len(body) != identities[name]["bytes"] or hashlib.sha256(body).hexdigest() != identities[name]["sha256"]:
                raise RuntimeError("Local grid payload does not match verified remote artifact")
        receipt = (json.dumps(result, indent=2, allow_nan=False)+"\n").encode()
        if (len(receipt) > config["file_caps"]["grid_validation.json"]
                or result["output_payload_bytes"]+len(receipt) > config["maximum_output_transfer_bytes"]):
            raise RuntimeError("Local grid receipt exceeds approved combined output budget")
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in {**payloads, config["local_receipt_name"]: receipt}.items():
            with (directory / name).open("xb") as output:
                output.write(body)
        print("PHASE4_GRID="+json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "part4-feature-preflight":
        import json
        from src.utils.io import load_config, resolve_path
        config = load_config("feature_preflight")
        directory = resolve_path("phase4_feature_review")
        names = list(config["local_outputs"].values())
        if any((directory / name).exists() for name in names):
            raise FileExistsError("Local feature preflight evidence exists; refusing overwrite")
        result = preflight_phase4_part2_sources.remote()
        payloads = result.pop("local_payloads")
        if set(payloads) != set(names) or sum(map(len, payloads.values())) > config["maximum_local_output_bytes"]:
            raise RuntimeError("Feature preflight local payload set/budget mismatch")
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in payloads.items():
            with (directory / name).open("xb") as output:
                output.write(body)
        print("PHASE4_FEATURE_PREFLIGHT="+json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "part4-dem-validate":
        import json
        from src.utils.io import load_config, resolve_path
        config = load_config("dem_validation")
        directory = resolve_path("phase4_feature_review")
        names = list(config["local_outputs"].values())
        if any((directory / name).exists() for name in names):
            raise FileExistsError("Local DEM validation evidence exists; refusing overwrite")
        result = validate_phase4_dem_sources.remote()
        payloads = result.pop("local_payloads")
        if set(payloads) != set(names) or sum(map(len, payloads.values())) > config["maximum_local_output_bytes"]:
            raise RuntimeError("DEM validation local payload set/budget mismatch")
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in payloads.items():
            with (directory/name).open("xb") as output:
                output.write(body)
        print("PHASE4_DEM_VALIDATION="+json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "part4-dem-header-probe":
        import json
        from src.utils.io import load_config, resolve_path
        config = load_config("dem_validation")
        directory = resolve_path("phase4_feature_review")
        names = list(config["probe_outputs"].values())
        if any((directory / name).exists() for name in names):
            raise FileExistsError("Local DEM header-probe evidence exists; refusing overwrite")
        result = probe_phase4_dem_headers.remote()
        payloads = result.pop("local_payloads")
        if set(payloads) != set(names) or sum(map(len, payloads.values())) > config["maximum_local_output_bytes"]:
            raise RuntimeError("DEM header-probe local payload set/budget mismatch")
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in payloads.items():
            with (directory/name).open("xb") as output:
                output.write(body)
        print("PHASE4_DEM_HEADER_PROBE="+json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "part4-feature-pilot":
        import json
        from src.utils.io import load_config, resolve_path
        config = load_config("feature_aggregation_pilot")
        directory = resolve_path("phase4_feature_review")
        names = list(config["local_outputs"].values())
        if any((directory / name).exists() for name in names):
            raise FileExistsError("Local feature-pilot evidence exists; refusing overwrite")
        result = run_phase4_feature_aggregation_pilot.remote()
        payloads = result.pop("local_payloads")
        if set(payloads) != set(names) or sum(map(len, payloads.values())) > config["maximum_local_output_bytes"]:
            raise RuntimeError("Feature-pilot local payload set/budget mismatch")
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in payloads.items():
            with (directory/name).open("xb") as output:
                output.write(body)
        print("PHASE4_FEATURE_PILOT="+json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "part4-feature-batch":
        import json
        from src.utils.io import load_config, resolve_path
        config = load_config("feature_aggregation_batch")
        directory = resolve_path("phase4_feature_review")
        receipt = directory/config["local_receipt"]
        if receipt.exists():
            raise FileExistsError("Local full-batch receipt exists; refusing overwrite")
        result = run_phase4_feature_aggregation_batch.remote()
        body = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n").encode()
        if len(body) > config["file_caps"]["feature_aggregation_manifest.contract-4.2.0.json"]:
            raise RuntimeError("Local full-batch receipt exceeds cap")
        directory.mkdir(parents=True, exist_ok=True)
        with receipt.open("xb") as output:
            output.write(body)
        print("PHASE4_FEATURE_BATCH="+json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "part4-feature-review":
        import json
        from src.utils.io import load_config, resolve_path
        config = load_config("feature_aggregation_batch")
        directory = resolve_path("phase4_feature_review")
        names = list(config["review_outputs"].values())
        if any((directory/name).exists() for name in names):
            raise FileExistsError("Local scientific-review evidence exists; refusing overwrite")
        result = review_phase4_feature_aggregation_batch.remote()
        payloads = result.pop("local_payloads")
        if set(payloads) != set(names) or sum(map(len, payloads.values())) > 2*1024*1024:
            raise RuntimeError("Scientific-review payload set/budget mismatch")
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in payloads.items():
            with (directory/name).open("xb") as output:
                output.write(body)
        print("PHASE4_FEATURE_REVIEW="+json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "part3-gate-review":
        import hashlib
        import json
        from src.utils.io import load_config, resolve_path
        config = load_config("gate_review")
        directory = resolve_path("phase3_gate_review")
        names = [*config["file_caps"], config["local_receipt_name"]]
        if any((directory / name).exists() for name in names):
            raise FileExistsError("Local QC output/receipt exists; refusing overwrite before remote execution")
        result = run_phase3_gate_review.remote()
        payloads = result.pop("local_payloads")
        if set(payloads) != set(config["file_caps"]):
            raise RuntimeError("Local QC payload set differs from approved output names")
        identities = {item["name"]: item for item in result["outputs"]}
        for name, body in payloads.items():
            if len(body) != identities[name]["bytes"] or hashlib.sha256(body).hexdigest() != identities[name]["sha256"]:
                raise RuntimeError("Local QC bytes do not match verified remote artifacts")
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in payloads.items():
            with (directory / name).open("xb") as output:
                output.write(body)
        with (directory / config["local_receipt_name"]).open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
            output.write("\n")
        print("PHASE3_GATE_REVIEW=" + json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "catalogue-dry-run":
        print(run_phase3_part1.remote(dry_run=True))
        return
    if action == "catalogue-write":
        print(run_phase3_part1.remote(dry_run=False))
        return
    if action == "triage-write":
        print(run_phase3_part2.remote())
        return
    if action == "triage-review":
        print(review_phase3_part2.remote())
        return
    if action == "part3-metadata-probe":
        print(probe_phase3_part3_metadata.remote())
        return
    if action == "part3-metadata-probe-all":
        print(probe_phase3_part3_metadata.remote(all_scenes=True))
        return
    if action == "part3-nodata-validate":
        print(validate_phase3_part3_nodata.remote())
        return
    if action.startswith("part3-nodata-"):
        epoch = int(action.rsplit("-", 1)[-1])
        print(validate_phase3_part3_nodata.remote(epoch=epoch))
        return
    if action.startswith("part3-radiometry-"):
        epoch = int(action.rsplit("-", 1)[-1])
        print(validate_phase3_part3_radiometry.remote(epoch=epoch))
        return
    if action.startswith("part3-spatial-"):
        epoch = int(action.rsplit("-", 1)[-1])
        print(validate_phase3_part3_spatial.remote(epoch=epoch))
        return
    if action == "part3-pilot":
        print(run_phase3_part3_pilot.remote())
        return
    if action == "part3-pilot-status":
        print(inspect_phase3_part3_pilot_outputs.remote())
        return
    if action == "part3-batch-preflight":
        print(preflight_phase3_part3_batch.remote())
        return
    if action == "part3-batch-extract":
        preflight = preflight_phase3_part3_batch.remote()
        if preflight["manifest"]["exists"]:
            raise RuntimeError("Refusing batch run: extraction manifest already exists")
        if preflight["output_state_counts"] != {"ABSENT": 32}:
            raise RuntimeError(
                "Refusing batch run: contract-3.3.2 output namespace is not empty: "
                f"{preflight['output_state_counts']}"
            )
        scenes = load_phase3_part3_batch_scenes.remote()
        results = []
        for result in run_phase3_part3_pilot.map(
            scenes, order_outputs=False, return_exceptions=True
        ):
            if isinstance(result, BaseException):
                raise result
            results.append(result)
            print({"validated_scenes": len(results), "total_scenes": len(scenes)})
        manifest = publish_phase3_part3_manifest.remote(results)
        print({"scene_count": len(results), "manifest": manifest})
        return
    if action == "part3-manifest-recover":
        preflight = preflight_phase3_part3_batch.remote()
        if preflight["manifest"]["exists"]:
            raise RuntimeError("Refusing recovery: extraction manifest already exists")
        if preflight["output_state_counts"] != {"COMPLETE": 32}:
            raise RuntimeError(
                "Refusing recovery: expected 32 complete output pairs: "
                f"{preflight['output_state_counts']}"
            )
        scenes = load_phase3_part3_batch_scenes.remote()
        results = []
        for result in recover_phase3_part3_manifest_entry.map(
            scenes, order_outputs=False, return_exceptions=True
        ):
            if isinstance(result, BaseException):
                raise result
            results.append(result)
            print({"recovered_entries": len(results), "total_scenes": len(scenes)})
        manifest = publish_phase3_part3_manifest.remote(results)
        print({"scene_count": len(results), "manifest": manifest})
        return
    if action == "part3-mask-validate":
        print(validate_phase3_part4_masks.remote())
        return
    if action == "part3-composite-plan":
        print(plan_phase3_part5_composites.remote())
        return
    if action == "part3-composite-coverage-preflight":
        plan = plan_phase3_part5_composites.remote()
        if not plan["all_outputs_absent"]:
            raise RuntimeError("Refusing scan: a proposed composite output key has a version")
        results = []
        for result in scan_phase3_part5_epoch_coverage.map(
            [2018, 2020, 2022, 2024],
            order_outputs=False,
            return_exceptions=True,
        ):
            if isinstance(result, BaseException):
                raise result
            results.append(result)
            print({"validated_epochs": len(results), "total_epochs": 4})
        print({
            "read_only": True,
            "total_source_bytes": sum(
                item["compressed_source_bytes"] for item in results
            ),
            "epochs": sorted(results, key=lambda item: item["epoch"]),
        })
        return
    if action == "part3-composite-build":
        plan = plan_phase3_part5_composites.remote()
        if not plan["all_outputs_absent"]:
            raise RuntimeError("Refusing build: a composite output key has a version")
        if not plan["coverage_gate_configured"]:
            raise RuntimeError("Refusing build: approved coverage gate is not configured")
        results = []
        for result in build_phase3_part5_epoch_composite.map(
            [2018, 2020, 2022, 2024], order_outputs=False, return_exceptions=True,
        ):
            if isinstance(result, BaseException):
                raise result
            results.append(result)
            print({"completed_epochs": len(results), "total_epochs": 4})
        print({"epoch_count": len(results),
               "output_count": sum(len(item["outputs"]) for item in results),
               "epochs": sorted(results, key=lambda item: item["epoch"])})
        return
    if action == "part3-composite-audit":
        print(audit_phase3_part5_composites.remote())
        return
    if action == "part3-storage-audit":
        import json
        print("READ_ONLY_STORAGE_AUDIT=" + json.dumps(audit_phase3_part7_storage.remote(), sort_keys=True))
        return
    if action in {"part3-archive-plan", "part3-archive-publish"}:
        import json
        from src.storage.archive_publish import load_approved_payloads
        from src.utils.io import find_repo_root, load_config
        policy = load_config("archive_publication")
        payloads = load_approved_payloads(find_repo_root(), policy)
        print(json.dumps({"dry_run": action == "part3-archive-plan",
                          "payload_count": len(payloads),
                          "payload_bytes": sum(len(p["body"]) for p in payloads),
                          "maximum_new_bytes": policy["maximum_new_bytes"],
                          "destination_prefix": policy["destination_prefix"],
                          "manifest_key": policy["manifest_key"]}), flush=True)
        if action == "part3-archive-plan":
            return
        result = publish_phase3_part7_archive.remote(payloads)
        print("PHASE3_ARCHIVE_COMPLETION=" + json.dumps(result, sort_keys=True), flush=True)
        return
    if action == "part3-indices-plan":
        print(plan_phase3_part6_indices.remote())
        return
    if action == "part3-indices-build":
        import uuid
        plan = plan_phase3_part6_indices.remote()
        if not plan["all_outputs_absent"]:
            raise RuntimeError("refusing index batch: a destination has a historical/current version")
        run_id = uuid.uuid4().hex
        results = []
        for result in build_phase3_part6_epoch_indices.map(
            plan["epochs"], kwargs={"run_id": run_id}, order_outputs=False,
            return_exceptions=True,
        ):
            if isinstance(result, BaseException):
                raise result
            results.append(result)
            print({"audited_epochs": len(results), "total_epochs": 4}, flush=True)
        publication = publish_phase3_part6_manifest.remote(results)
        print({"completed": True, "manifest": publication}, flush=True)
        return
    raise ValueError("unsupported action")

"""A tiny synthetic bucket listing covering every classification case Part
2.1 must handle: a complete product, an incomplete one (missing a required
derivative), a reprocessed duplicate (same acquisition, different
baseline), a zero-byte file, a boundary file, and junk.

(key, size_bytes) tuples — seed a FakeBackend with these via .seed(key, b"x" * size).
"""

FAKE_BUCKET_OBJECTS = [
    # Complete product: all three derivatives present (tile T44QPE, baseline N0500)
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_refl.tif", 12_641_542),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_scl.tif", 77_222),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_qa.json", 1_256),
    # Incomplete product: missing the _scl.tif derivative (tile T44QQF)
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0500_R076_T44QQF_20230717T103013.SAFE_refl.tif", 856_656),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0500_R076_T44QQF_20230717T103013.SAFE_qa.json", 1_187),
    # Reprocessed duplicate: same mission/sensing_date/orbit/tile as the T44QQE
    # product below, but a later processing baseline (N0511 vs N0500).
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0500_R076_T44QQE_20230717T103013.SAFE_refl.tif", 206_403_248),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0500_R076_T44QQE_20230717T103013.SAFE_scl.tif", 677_748),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0500_R076_T44QQE_20230717T103013.SAFE_qa.json", 1_311),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0511_R076_T44QQE_20231201T090000.SAFE_refl.tif", 207_000_000),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0511_R076_T44QQE_20231201T090000.SAFE_scl.tif", 680_000),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180103T045201_N0511_R076_T44QQE_20231201T090000.SAFE_qa.json", 1_300),
    # Zero-byte / suspect size file (corrupted upload)
    ("vizag-geoai/data/processed/sentinel2/2018/masked/S2A_MSIL2A_20180105T045201_N0500_R076_T44QPF_20230717T103013.SAFE_refl.tif", 0),
    # Boundary files (legitimate, not junk)
    ("vizag-geoai/data/boundaries/gvmc_boundary.geojson", 118_412),
    ("vizag-geoai/data/boundaries/gvmc_boundary_buffered.geojson", 32_768),
    # Junk / non-product files — must be classified "unknown", never flagged for deletion
    ("vizag-geoai/.DS_Store", 6_148),
    ("vizag-geoai/data/processed/sentinel2/2018/masked/Thumbs.db", 10_240),
]

from src.acquisition.product_id import parse_object_key


def test_product_id_parsing_from_processed_derivative_key():
    key = (
        "vizag-geoai/data/processed/sentinel2/2018/masked/"
        "S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_refl.tif"
    )
    parsed = parse_object_key(key)

    assert parsed.source == "sentinel2"
    assert parsed.format == "processed_derivative"
    assert parsed.derivative_kind == "refl"
    assert parsed.mission == "S2A"
    assert parsed.level == "MSIL2A"
    assert parsed.sensing_date == "20180103T045201"
    assert parsed.processing_baseline == "N0500"
    assert parsed.relative_orbit == "R076"
    assert parsed.tile == "T44QPE"
    assert parsed.processing_date == "20230717T103013"


def test_product_id_parsing_scl_and_qa_kinds():
    base = "S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_"
    assert parse_object_key(base + "scl.tif").derivative_kind == "scl"
    assert parse_object_key(base + "qa.json").derivative_kind == "qa"


def test_product_id_parsing_from_zip_name():
    key = "raw/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.zip"
    parsed = parse_object_key(key)
    assert parsed.source == "sentinel2"
    assert parsed.format == "zip"
    assert parsed.tile == "T44QPE"


def test_product_id_parsing_from_safe_dot_zip_name():
    # The real bucket's raw archive naming: "<product_id>.SAFE.zip", not
    # plain ".zip" — a whole zipped SAFE archive, not a derivative.
    key = "data/raw/sentinel2/2018/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE.zip"
    parsed = parse_object_key(key)
    assert parsed.source == "sentinel2"
    assert parsed.format == "zip"
    assert parsed.tile == "T44QPE"


def test_mosaic_derivative_parsing():
    parsed = parse_object_key("vizag-geoai/data/processed/sentinel2/2018/mosaic/S2A_20180103T045201_R076_refl.tif")
    assert parsed.source == "sentinel2"
    assert parsed.format == "mosaic_derivative"
    assert parsed.derivative_kind == "refl"
    assert parsed.mission == "S2A"
    assert parsed.relative_orbit == "R076"
    assert parsed.tile is None


def test_product_id_parsing_from_safe_folder():
    key = "raw/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE/GRANULE/L2A_T44QPE/IMG_DATA/R10m/T44QPE_20180103T045201_B02_10m.jp2"
    parsed = parse_object_key(key)
    assert parsed.source == "sentinel2"
    assert parsed.format == "SAFE"
    assert parsed.tile == "T44QPE"
    assert parsed.mission == "S2A"


def test_boundary_file_classified_correctly():
    parsed = parse_object_key("vizag-geoai/data/boundaries/gvmc_boundary.geojson")
    assert parsed.source == "boundary"


def test_ds_store_classified_as_unknown_not_other():
    parsed = parse_object_key("vizag-geoai/.DS_Store")
    assert parsed.source == "unknown"


def test_thumbs_db_classified_as_unknown():
    parsed = parse_object_key("vizag-geoai/some/dir/Thumbs.db")
    assert parsed.source == "unknown"


def test_unrecognized_file_with_extension_classified_other():
    parsed = parse_object_key("vizag-geoai/data/raw_small/osm/vizag_roads.gpkg")
    assert parsed.source == "other"


def test_file_with_no_extension_and_no_dot_classified_unknown():
    parsed = parse_object_key("vizag-geoai/somefile")
    assert parsed.source == "unknown"


def test_duplicate_group_key_ignores_baseline_and_processing_date():
    a = parse_object_key(
        "x/S2A_MSIL2A_20180103T045201_N0500_R076_T44QQE_20230717T103013.SAFE_refl.tif"
    )
    b = parse_object_key(
        "x/S2A_MSIL2A_20180103T045201_N0511_R076_T44QQE_20231201T090000.SAFE_refl.tif"
    )
    assert a.duplicate_group_key == b.duplicate_group_key
    assert a.product_id != b.product_id


def test_duplicate_group_key_differs_for_different_tile():
    a = parse_object_key(
        "x/S2A_MSIL2A_20180103T045201_N0500_R076_T44QQE_20230717T103013.SAFE_refl.tif"
    )
    b = parse_object_key(
        "x/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_refl.tif"
    )
    assert a.duplicate_group_key != b.duplicate_group_key


def test_matching_is_by_product_id_not_exact_key():
    # Same product under two different prefixes must parse to the same product_id.
    a = parse_object_key(
        "prefix-one/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_refl.tif"
    )
    b = parse_object_key(
        "prefix-two/deep/nested/S2A_MSIL2A_20180103T045201_N0500_R076_T44QPE_20230717T103013.SAFE_refl.tif"
    )
    assert a.key != b.key
    assert a.product_id == b.product_id

import pytest

from src.utils.env_check import (
    MissingDriverError,
    NoCredentialsError,
    check_b2_credentials_present,
    check_jp2_driver_available,
)


def test_check_jp2_driver_available_passes_with_real_gdal():
    # This Studio's rasterio/GDAL build was verified (Part 0.4) to include
    # JP2OpenJPEG via an actual write+read round-trip — this just confirms
    # the check function agrees with that real environment.
    check_jp2_driver_available()


def test_check_jp2_driver_detects_missing_driver():
    def fake_extensions():
        return {"tif": "GTiff"}  # no "jp2" entry at all

    with pytest.raises(MissingDriverError, match="JP2OpenJPEG"):
        check_jp2_driver_available(extensions_provider=fake_extensions)


def test_check_jp2_driver_detects_wrong_driver_mapped():
    def fake_extensions():
        return {"jp2": "SomeOtherDriver"}

    with pytest.raises(MissingDriverError, match="JP2OpenJPEG"):
        check_jp2_driver_available(extensions_provider=fake_extensions)


def test_check_b2_credentials_present_passes_when_set():
    env = {"Backbaze-keyID": "abc", "Backbaze-applicationKey": "def"}
    check_b2_credentials_present(env)


def test_check_b2_credentials_present_raises_when_missing():
    env = {"Backbaze-keyID": "abc"}  # applicationKey missing
    with pytest.raises(NoCredentialsError, match="Backbaze-applicationKey"):
        check_b2_credentials_present(env)


def test_check_b2_credentials_present_raises_when_both_missing():
    with pytest.raises(NoCredentialsError, match="Backbaze-keyID"):
        check_b2_credentials_present({})

import numpy as np
import pytest

from src.preprocessing.radiometry import (
    RadiometryMetadata,
    RadiometryMetadataError,
    convert_dn_to_reflectance,
    parameters_for_band,
    parse_l2a_radiometry_metadata,
    reflectance_statistics,
)


def test_parse_namespaced_l2a_radiometry_metadata():
    xml = b"""<n1:Level-2A_User_Product xmlns:n1="urn:test">
      <n1:PROCESSING_BASELINE>05.11</n1:PROCESSING_BASELINE>
      <n1:BOA_QUANTIFICATION_VALUE unit="none">10000</n1:BOA_QUANTIFICATION_VALUE>
      <n1:BOA_ADD_OFFSET_VALUES_LIST>
        <n1:BOA_ADD_OFFSET band_id="1">-1000</n1:BOA_ADD_OFFSET>
        <n1:BOA_ADD_OFFSET band_id="11">-1000</n1:BOA_ADD_OFFSET>
      </n1:BOA_ADD_OFFSET_VALUES_LIST>
      <n1:Spectral_Information_List>
        <n1:Spectral_Information bandId="1" physicalBand="B2" />
        <n1:Spectral_Information bandId="11" physicalBand="B11" />
      </n1:Spectral_Information_List>
    </n1:Level-2A_User_Product>"""
    result = parse_l2a_radiometry_metadata(xml)
    assert result.processing_baseline == "05.11"
    assert result.quantification_value == 10000
    assert result.offsets_by_band_id == {"1": -1000, "11": -1000}
    assert result.physical_band_by_id == {"1": "B02", "11": "B11"}


def test_pre_offset_product_may_have_no_offset_list():
    xml = """<root><PROCESSING_BASELINE>02.06</PROCESSING_BASELINE>
    <BOA_QUANTIFICATION_VALUE>10000</BOA_QUANTIFICATION_VALUE></root>"""
    result = parse_l2a_radiometry_metadata(xml)
    assert result.offsets_by_band_id == {}


@pytest.mark.parametrize("xml", [
    "<root><PROCESSING_BASELINE>05.11</PROCESSING_BASELINE></root>",
    "<root><PROCESSING_BASELINE>05.11</PROCESSING_BASELINE><BOA_QUANTIFICATION_VALUE>0</BOA_QUANTIFICATION_VALUE></root>",
    "not xml",
])
def test_invalid_radiometry_metadata_fails(xml):
    with pytest.raises(RadiometryMetadataError):
        parse_l2a_radiometry_metadata(xml)


def test_dn_zero_becomes_explicit_nodata_before_offset():
    result, valid = convert_dn_to_reflectance(
        np.array([0, 1, 1000, 2000], dtype="uint16"),
        offset=-1000,
        quantification_value=10000,
    )
    assert result.dtype == np.float32
    assert result[0] == -9999.0
    assert valid.tolist() == [False, True, True, True]
    np.testing.assert_allclose(result[1:], [-0.0999, 0.0, 0.1], atol=1e-7)


def test_conversion_does_not_clip_valid_negative_or_above_one_values():
    result, _ = convert_dn_to_reflectance(
        np.array([1, 12000], dtype="uint16"), offset=-1000, quantification_value=10000
    )
    assert result[0] < 0
    assert result[1] > 1


def test_offset_era_band_parameters_use_physical_mapping_not_position():
    metadata = RadiometryMetadata("05.10", 10000, {"7": -1000}, {"7": "B08"})
    assert parameters_for_band(metadata, "B8") == (-1000, 10000)


def test_offset_era_missing_band_offset_fails_closed():
    metadata = RadiometryMetadata("05.10", 10000, {}, {"7": "B08"})
    with pytest.raises(RadiometryMetadataError, match="lacks BOA_ADD_OFFSET"):
        parameters_for_band(metadata, "B08")


def test_pre_offset_product_uses_zero_offset_when_absent():
    metadata = RadiometryMetadata("02.06", 10000, {}, {"1": "B02"})
    assert parameters_for_band(metadata, "B02") == (0.0, 10000)


def test_conversion_rejects_already_float_input_to_prevent_double_scaling():
    with pytest.raises(TypeError, match="integer dtype"):
        convert_dn_to_reflectance(np.array([0.1], dtype="float32"), offset=-1000, quantification_value=10000)


def test_statistics_exclude_nodata_and_count_out_of_nominal_values():
    values = np.array([-9999, -0.1, 0.2, 1.2], dtype="float32")
    stats = reflectance_statistics(values, np.array([False, True, True, True]))
    assert stats["valid_pixels"] == 3
    assert stats["negative_pixels"] == 1
    assert stats["above_one_pixels"] == 1
    assert stats["minimum"] == pytest.approx(-0.1)
    assert stats["maximum"] == pytest.approx(1.2)


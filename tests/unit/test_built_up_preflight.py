from types import SimpleNamespace

import pytest

from src.labels.built_up_preflight import approved_index_sources, build_preflight_report, pin_worldcover


def _configs():
    config = {"epochs": [2018, 2020, 2022, 2024], "roles": ["ndvi", "ndbi", "ndwi", "mndwi", "bsi"],
              "contract_version": "5.1", "crosscheck_epochs": [2020, 2022],
              "production_writes_allowed": False}
    sources = [{"epoch": e, "role": r, "key": f"{e}/{r}", "bytes": 1,
                "version_id": "v", "sha256": "a"*64}
               for e in config["epochs"] for r in config["roles"]]
    return config, {"sources": sources}


def test_requires_complete_five_index_four_epoch_matrix():
    config, gate = _configs()
    assert len(approved_index_sources(gate, config)) == 20
    gate["sources"].pop()
    with pytest.raises(RuntimeError, match="exactly five"):
        approved_index_sources(gate, config)


class Client:
    def get_paginator(self, operation):
        assert operation == "list_object_versions"
        return SimpleNamespace(paginate=lambda **kwargs: iter([{"Versions": [
            {"Key": kwargs["Prefix"], "Size": 10, "VersionId": "wc-v1", "IsLatest": True}]}]))

    def head_object(self, **kwargs):
        return {"ContentLength": 10, "ETag": '"etag"', "Metadata": {}}


def test_worldcover_pin_and_read_only_report():
    config, gate = _configs()
    wc = pin_worldcover(Client(), "bucket", {"key": "wc", "expected_bytes": 10,
        "product_year": 2021, "product_version": "v200"})
    report = build_preflight_report(config, approved_index_sources(gate, config), wc)
    assert report["b2_writes"] == 0 and report["pixel_reads"] == 0
    assert report["crosscheck_epochs"] == [2020, 2022]

import numpy as np
from src.labels.built_up_classification import candidate_rules, classify, confusion, metrics, select_rule, valid_index_mask


def test_candidate_classifier_is_multi_index_and_nodata_safe():
    config = {"pilot": {"ndbi_thresholds": [0], "ndvi_caps": [.3], "mndwi_caps": [0], "require_ndbi_gt_ndvi": True}}
    rule = candidate_rules(config)[0]
    arrays = {"ndbi": np.array([[.2, .2, -9999.]]), "ndvi": np.array([[.1, .4, .1]]),
              "mndwi": np.array([[-.1, -.1, -.1]])}
    valid = valid_index_mask(arrays, {key: -9999. for key in arrays})
    assert classify(arrays, rule, valid).tolist() == [[True, False, False]]


def test_confusion_metrics_and_worst_year_selection():
    pred = np.array([True, True, False, False]); ref = np.array([True, False, True, False])
    result = metrics(confusion(pred, ref, np.ones(4, dtype=bool)))
    assert result["tp"] == result["tn"] == result["fp"] == result["fn"] == 1
    assert result["balanced_accuracy"] == .5
    rules = {"stable": {2020: {"balanced_accuracy": .7, "f1": .6, "predicted_built_fraction": .2},
                         2022: {"balanced_accuracy": .7, "f1": .6, "predicted_built_fraction": .21}},
             "fragile": {2020: {"balanced_accuracy": .9, "f1": .8, "predicted_built_fraction": .2},
                          2022: {"balanced_accuracy": .6, "f1": .8, "predicted_built_fraction": .4}}}
    assert select_rule(rules)["name"] == "stable"

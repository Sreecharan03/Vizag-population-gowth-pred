"""Planning and overwrite-safety primitives for Phase 3.3 batch extraction."""

from __future__ import annotations

import json
import string
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class OutputPairState(str, Enum):
    ABSENT = "ABSENT"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class SceneOutputKeys:
    reflectance: str
    scl: str


def scene_identifier(scene: Mapping) -> str:
    """Return the immutable scene identifier or fail closed."""
    value = scene.get("scene_id") or scene.get("product_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("selected scene lacks a stable scene_id/product_id")
    return value.strip()


def output_keys(
    processed_prefix: str, scene: Mapping, *, contract_version: str
) -> SceneOutputKeys:
    """Build the two versioned final keys for one selected scene."""
    if not processed_prefix.endswith("/"):
        raise ValueError("processed_prefix must end with '/'")
    if not contract_version or "/" in contract_version or "\\" in contract_version:
        raise ValueError("contract_version must be a non-empty path-safe value")
    try:
        epoch = int(scene["epoch"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("selected scene has an invalid epoch") from exc
    if epoch < 2000 or epoch > 2100:
        raise ValueError(f"selected scene epoch is implausible: {epoch}")
    identifier = scene_identifier(scene)
    root = (
        f"{processed_prefix}sentinel2/scene_stacks/contract-{contract_version}/"
        f"{epoch}/{identifier}"
    )
    return SceneOutputKeys(
        reflectance=f"{root}_reflectance.tif",
        scl=f"{root}_scl.tif",
    )


def classify_output_pair(*, reflectance_exists: bool, scl_exists: bool) -> OutputPairState:
    """Classify an output pair without treating partial publication as resumable."""
    if reflectance_exists and scl_exists:
        return OutputPairState.COMPLETE
    if reflectance_exists or scl_exists:
        return OutputPairState.PARTIAL
    return OutputPairState.ABSENT


def validate_selected_scenes(scenes: list[Mapping], *, expected_count: int = 32) -> None:
    """Validate batch identity invariants before any worker can be scheduled."""
    if len(scenes) != expected_count:
        raise ValueError(f"expected {expected_count} selected scenes, found {len(scenes)}")
    identifiers: set[str] = set()
    source_keys: set[str] = set()
    epoch_counts: dict[int, int] = {}
    for scene in scenes:
        identifier = scene_identifier(scene)
        source_key = scene.get("object_key")
        if not isinstance(source_key, str) or not source_key.endswith(".SAFE.zip"):
            raise ValueError(f"{identifier}: invalid source object_key")
        if identifier in identifiers:
            raise ValueError(f"duplicate scene identifier: {identifier}")
        if source_key in source_keys:
            raise ValueError(f"duplicate source object key: {source_key}")
        identifiers.add(identifier)
        source_keys.add(source_key)
        epoch = int(scene["epoch"])
        epoch_counts[epoch] = epoch_counts.get(epoch, 0) + 1
    expected_epochs = {2018: 8, 2020: 8, 2022: 8, 2024: 8}
    if epoch_counts != expected_epochs:
        raise ValueError(f"unexpected selected-scene epoch counts: {epoch_counts}")


def build_extraction_manifest(results: list[Mapping], *, expected_count: int = 32) -> bytes:
    """Build a deterministic JSONL manifest after validating result identities."""
    if len(results) != expected_count:
        raise ValueError(
            f"expected {expected_count} extraction results, found {len(results)}"
        )
    identifiers = [result.get("scene_id") for result in results]
    if any(not isinstance(value, str) or not value for value in identifiers):
        raise ValueError("manifest results contain a missing scene identifier")
    if len(set(identifiers)) != expected_count:
        raise ValueError("manifest results contain duplicate scene identifiers")
    for result in results:
        if not result.get("remote_reopen_validated"):
            raise ValueError(f"{result.get('scene_id')}: remote validation is incomplete")
        outputs = result.get("outputs")
        if not isinstance(outputs, Mapping) or set(outputs) != {"reflectance", "scl"}:
            raise ValueError(f"{result.get('scene_id')}: output pair is incomplete")
        for output in outputs.values():
            if not output.get("sha256") or not output.get("bytes"):
                raise ValueError(f"{result.get('scene_id')}: output identity is incomplete")
    return "".join(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
        for result in sorted(
            results, key=lambda item: (int(item["epoch"]), item["scene_id"])
        )
    ).encode("utf-8")


def recovery_checkpoint_matches(
    checkpoint: Mapping,
    *,
    scene_id: str,
    contract_version: str,
    source_key: str,
    source_size: int,
    source_etag: str,
    outputs: Mapping[str, Mapping],
) -> bool:
    """Return whether a persisted hash result still matches current identities."""
    if (
        checkpoint.get("scene_id") != scene_id
        or checkpoint.get("contract_version") != contract_version
        or checkpoint.get("source_key") != source_key
        or checkpoint.get("source_identity")
        != {"size_bytes": source_size, "etag": source_etag}
        or checkpoint.get("remote_reopen_validated") is not True
    ):
        return False
    actual_outputs = checkpoint.get("outputs")
    if not isinstance(actual_outputs, Mapping) or set(actual_outputs) != set(outputs):
        return False
    for name, expected in outputs.items():
        actual = actual_outputs.get(name)
        if not isinstance(actual, Mapping):
            return False
        digest = actual.get("sha256")
        if (
            actual.get("key") != expected.get("key")
            or actual.get("bytes") != expected.get("bytes")
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in string.hexdigits for character in digest)
        ):
            return False
    return True


"""Deterministic manifests for the v1 contract's unordered collections."""

import hashlib
import json
import math
from typing import Any, Literal

from packages.contracts.operational import OperationalInputs
from packages.contracts.run_manifest import EngineConfiguration, RunManifest
from packages.domain.inputs.validation import validate_operational_inputs

CANONICALIZATION: Literal["operational.canonical.v1"] = "operational.canonical.v1"


def canonical_bytes(value: Any) -> bytes:
    """All arrays in operational v1 are sets; ordered geometry/events live in pinned artifacts.

    Do not reuse this rule for ordered future event streams, routes or polygon coordinates.
    """
    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("canonical object keys must be strings")
            return {key: normalize(child) for key, child in item.items()}
        if isinstance(item, (tuple, list)):
            children = [normalize(child) for child in item]
            return sorted(children, key=lambda child: json.dumps(
                child, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
            ))
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("canonical values must be finite")
            return 0.0 if item == 0 else item
        if item is None or type(item) in (str, int, bool):
            return item
        raise ValueError(f"unsupported canonical type: {type(item).__name__}")

    return json.dumps(normalize(value), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_run_manifest(inputs: OperationalInputs, config: EngineConfiguration) -> RunManifest:
    validated = validate_operational_inputs(inputs)
    config = EngineConfiguration.model_validate_json(config.model_dump_json())
    content = validated.model_dump(mode="json")
    twin = {key: value for key, value in content.items() if key != "scenario"}
    run_sha256 = digest({
        "schema_version": "run.manifest.v1", "canonicalization_version": CANONICALIZATION,
        "inputs": content, "configuration": config.model_dump(mode="json"),
    })
    return RunManifest(
        schema_version="run.manifest.v1", canonicalization_version=CANONICALIZATION,
        inputs=validated, configuration=config, twin_sha256=digest(twin),
        scenario_sha256=digest(content["scenario"]), input_sha256=digest(content),
        run_sha256=run_sha256,
    )


def verify_run_manifest(manifest: RunManifest) -> RunManifest:
    expected = build_run_manifest(manifest.inputs, manifest.configuration)
    for field in ("schema_version", "canonicalization_version", "twin_sha256",
                  "scenario_sha256", "input_sha256", "run_sha256"):
        if getattr(manifest, field) != getattr(expected, field):
            raise ValueError(f"manifest mismatch: {field}")
    return expected

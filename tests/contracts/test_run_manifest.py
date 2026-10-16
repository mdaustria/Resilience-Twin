"""Pinned-input hashes are deterministic, sensitive to material changes and tamper evident."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from packages.contracts.run_manifest import EngineConfiguration, RunManifest
from packages.domain.inputs import (
    build_run_manifest,
    parse_operational_inputs,
    verify_run_manifest,
)
from packages.domain.inputs.manifest import canonical_bytes
from scripts.generate_client import SCHEMAS, generate_clients, operational_openapi

FIXTURE = Path(__file__).parents[1] / "fixtures/inputs/operational.json"


def config():
    return EngineConfiguration(
        engine_version="synthetic-v1", engine_sha256="a"*64,
        policy_version="synthetic-policy-v1", policy_sha256="b"*64,
        runtime_version="CPython-3.13.16", iteration_budget=10, response_mode="deterministic",
    )


def test_reordering_objects_and_collections_preserves_canonical_manifest():
    original = json.loads(FIXTURE.read_text())

    def reverse(value):
        if isinstance(value, dict):
            return {key: reverse(item) for key, item in reversed(list(value.items()))}
        if isinstance(value, list):
            return [reverse(item) for item in reversed(value)]
        return value

    first = build_run_manifest(parse_operational_inputs(original), config())
    second = build_run_manifest(parse_operational_inputs(reverse(original)), config())
    assert first.run_sha256 == second.run_sha256
    assert canonical_bytes(first.model_dump(mode="json")) == canonical_bytes(second.model_dump(mode="json"))
    assert verify_run_manifest(RunManifest.model_validate_json(first.model_dump_json())) == first


@pytest.mark.parametrize("mutate", [
    lambda d: d["shelters"][0].update(initial_water_ml=1),
    lambda d: d["vehicles"][0].update(distance_budget_mm=0),
    lambda d: d["scope"]["exclusions"].append("Additional excluded area"),
    lambda d: d["scope"]["boundary"].update(sha256="7"*64),
    lambda d: d["assumptions"][0].update(rationale="Changed applicability decision"),
    lambda d: d["graph"]["artifact"].update(sha256="8"*64),
    lambda d: d["scenario"].update(seed=1),
    lambda d: d["scenario"].update(horizon_seconds=3601),
    lambda d: d["scenario"]["exogenous_scenario"].update(sha256="9"*64),
    lambda d: d["shelters"][0].update(cost_centavos=0),
])
def test_material_values_scope_and_assumptions_change_hash(mutate):
    data = json.loads(FIXTURE.read_text())
    first = build_run_manifest(parse_operational_inputs(data), config())
    mutate(data)
    second = build_run_manifest(parse_operational_inputs(data), config())
    assert second.input_sha256 != first.input_sha256
    assert second.run_sha256 != first.run_sha256


def test_engine_policy_and_budget_are_pinned_without_changing_input_hash():
    inputs = parse_operational_inputs(FIXTURE.read_bytes())
    first = build_run_manifest(inputs, config())
    changed = config().model_copy(update={"iteration_budget":11, "policy_sha256":"f"*64})
    second = build_run_manifest(inputs, changed)
    assert first.input_sha256 == second.input_sha256
    assert first.run_sha256 != second.run_sha256


def test_manifest_tampering_and_validation_bypass_fail():
    inputs = parse_operational_inputs(FIXTURE.read_bytes())
    manifest = build_run_manifest(inputs, config())
    with pytest.raises(ValueError, match="manifest mismatch"):
        verify_run_manifest(manifest.model_copy(update={"run_sha256":"0"*64}))
    invalid = inputs.model_copy(update={"cohorts":inputs.cohorts + inputs.cohorts})
    with pytest.raises(ValueError, match="duplicate record IDs"):
        build_run_manifest(invalid, config())
    changed = manifest.model_dump(mode="json")
    changed["configuration"]["iteration_budget"] += 1
    with pytest.raises(ValueError, match="run_sha256"):
        verify_run_manifest(RunManifest.model_validate(changed))
    changed["duration_seconds"] = 10
    with pytest.raises(ValueError):
        RunManifest.model_validate(changed)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object()])
def test_canonicalization_rejects_nonfinite_and_executable_objects(value):
    with pytest.raises(ValueError):
        canonical_bytes({"value":value})


def test_operational_schema_change_requires_regeneration(monkeypatch):
    changed = deepcopy(operational_openapi())
    changed["components"]["schemas"]["Vehicle"]["properties"]["new_required_resource"] = {"type":"integer"}
    changed["components"]["schemas"]["Vehicle"]["required"].append("new_required_resource")
    monkeypatch.setattr("scripts.generate_client.operational_openapi", lambda: changed)
    with pytest.raises(SystemExit, match="Generated operational client differs"):
        generate_clients(check=True, schemas=(SCHEMAS[2],))

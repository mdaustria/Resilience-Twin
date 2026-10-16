"""Pinned run inputs/configuration; runtime duration and wall-clock metadata are excluded."""

from typing import Literal

from packages.contracts.operational import (
    Contract,
    Count,
    OperationalInputs,
    Sha256,
    Text,
)


class EngineConfiguration(Contract):
    engine_version: Text
    engine_sha256: Sha256
    policy_version: Text
    policy_sha256: Sha256
    runtime_version: Text
    iteration_budget: Count
    response_mode: Literal["deterministic"]


class RunManifest(Contract):
    schema_version: Literal["run.manifest.v1"]
    canonicalization_version: Literal["operational.canonical.v1"]
    inputs: OperationalInputs
    configuration: EngineConfiguration
    twin_sha256: Sha256
    scenario_sha256: Sha256
    input_sha256: Sha256
    run_sha256: Sha256

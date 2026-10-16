# Task 2.2 synthetic operational inputs

`operational.json` describes a fictional study area with 100 people: 20 initial shelter occupants, 40 waiting, and 40 not requested. Initial occupants have one cohort identity and consume from the shelter's stock. Waiting/transit provision points explicitly to a zero-stock store; missing provision is not assumed zero. Deadlines after the horizon remain valid input, to be reported as pending by later engine tasks.

Every operational field is supported by the explicit synthetic assumption. Artifact hashes are synthetic identifiers for contract tests, not files purporting to be real plans, reviewed roads or provider outputs. This fixture is separate from Task 2.1's arithmetic regression-reference cases. It does not validate a disaster model or select the real QC study area.

Contract tests supply additional documentary candidates to exercise source units/ranges, conflicts, proposed/historical statements and geographic applicability. No supplied PDF content is redistributed. Informational procedures cannot become executable effects.

Use `parse_operational_inputs` (or `validate_operational_inputs`) before sealing. Pydantic models alone enforce shape/field constraints; the domain function enforces cross-record references, provenance and population/resource consistency. `build_run_manifest` always revalidates and `verify_run_manifest` detects tampering. All v1 tuple collections are unordered sets for canonicalization; ordered geometry/events must remain in pinned artifacts. Unknown optional costs and staging limits stay `null`; missing required quantities fail validation. Full extraction/readiness, graph topology/restrictions and scenario-event execution remain later tasks.

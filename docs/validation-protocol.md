# Input-based verification protocol — v0.2

Status: **v0.2.0 frozen on 14 October 2026 under the user-selected scope; Task 2.1 complete**. Task 2.1 freezes this engineering protocol and its arithmetic fixtures; Task 3.9 executes and records the complete proof. The machine-readable record is [`release/validation/protocol.json`](../release/validation/protocol.json). Passing the protocol contract test does not complete milestone A.

## Inputs and claim boundary

The required user inputs are a disaster-plan PDF and a textual location for OSM. Resolve the location to a declared study area and pin the OSM source, extent, graph and routing settings. Check each supplied PDF separately against its own pages. No event observations, after-action reports, field measurements, recruited participants, official approvals or independent domain reviewers are required for milestones A–C.

Use what the PDF and OSM actually contain. Preserve missing facts, conflicting values, units and historical/proposed statements. Missing computational inputs can be supplied by visible, versioned modeling assumptions selected by the user, including a bounded scenario, speed/loading defaults, water demand and hypothetical resources. Defaults are never evidence about actual resources or conditions. Keep assumptions in a compact review summary; accept them together before sealing, without requiring an external approver. Additional documents are optional. If an essential value remains unresolved, allow gap review/export and block only its dependent simulation.

Outputs are exploratory results conditional on those inputs and assumptions. They do not establish real-world predictive accuracy, verified facility availability or field travel times. OSM topology checks establish consistency with the pinned map, not current road conditions. Missing PDF annexes need not be obtained to finish a gap review or an assumption-completed scenario.

## Exact arithmetic references

`tests/fixtures/validation/cases.json` contains one development example and two reference examples. These cases and expected values already existed and were visible during development; they are regression references, not blind held-out evidence. Expected values come from the written arithmetic derivations, not from engine output. No reference scoring is claimed by Task 2.1.

| Metric | Definition | Unit | Absolute error allowed |
| --- | --- | --- | ---: |
| Arrival time | Arrival of the referenced cohort within the terminal horizon; `null` when there is no arrival | integer seconds | 0; `null` must match `null` |
| Evacuated population | Unique people arriving within the horizon; unfinished trips excluded | integer people | 0 |
| Water shortfall | Required water minus water used, floored at zero | integer milliliters | 0 |

These are software-correctness tolerances for exact synthetic arithmetic, not empirical tolerances. Check people conservation, capacity, water used ≤ available stock and nonnegative quantities. Missing reference/results are unscored and cannot count as passing. Record signed and absolute errors per applicable metric; all must meet tolerance.

## Procedure

1. Freeze the versioned protocol before reference scoring. Record SHA-256 of fixture bytes and a protocol content hash over canonical UTF-8 JSON (sorted keys, compact separators, excluding `content_sha256`). No signature or reviewer identity is required. Changes to fixtures, tolerances or scope require a new version and dated rationale; retain prior scores and rerun against both old and new thresholds. Never relax a threshold just to hide a failing result.
2. Pin source PDF, textual location, resolved extent, OSM graph, engine, policy, scenario, seed and assumptions for each demonstration. Record PDF/OSM facts separately from assumptions and retain source-only gaps after assumptions make a run possible.
3. Score the exact reference cases through the engine in Task 3.9. Keep boundary/replay checks covering horizon equality, unfinished trips, same-time disruptions, initial occupants, final water intervals, capacities, crew/distance constraints, disconnected routes and exhaustion. A failure is not a zero-valued success.
4. Run bounded travel, loading, demand-timing and water-use sensitivity checks plus the reference policy. Ranges are explicit engineering assumptions; report outcome ranges and rank reversals without probabilities or claims of optimality.
5. Check both full PDFs against page-cited expected facts, with separate extraction denominators and critical-fact checks, including image and split tables. A developer/operator can perform this source inspection. Do not use an extraction model's own output as its only answer key. Complete gap export and assumption-completed baseline → disruption → paired change → export for each PDF and location. No real disaster comparison is required.

Critical failures include conservation errors, impossible modeled routes/allocations, unfinished trips counted as arrivals, hidden water shortages, future-knowledge use, or unsupported factual/safety claims. Document lower-severity discrepancies; unresolved critical failures block acceptance. Findings use versioned provisional priorities and raw metrics, not externally certified severity.

## Supersession and remaining work

ADR-030 replaces v0.1's field-reference and reviewer requirements. The prior typhoon occupancy/water comparison candidates are removed from the active protocol. Historical progress entries describe the old scope only. Existing numerical, provenance, provider, privacy, security and dependency checks remain required. Task 3.9 still needs real application evidence for the two input documents; Task 6.6 needs repeatable workflow/extraction/traceability checks, not a participant study.

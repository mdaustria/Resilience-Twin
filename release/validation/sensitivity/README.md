# Bounded synthetic sensitivity record — Task 2.12

[`tiny-expanded.json`](tiny-expanded.json) records the exact 10 expanded configurations and 20 policy/model pairs from [`tiny-cases.json`](../../../tests/fixtures/validation/sensitivity/tiny-cases.json). Its fixture checksum and repeated exogenous hash make the paired conditions inspectable. Low and high travel reverse the proposed change's on-time ranking in the synthetic two-group case. A failure that disappears under `earliest_deadline_reference_v1` is labeled policy dependent; it is not evidence that a physical resource shortage is unavoidable.

`earliest_deadline_reference_v1` uses the existing trip feasibility and known-observation boundary, orders cohorts by absolute deadline, and makes no local improvement moves. The tiny exhaustive case enumerates its declared static candidate choices only. The resulting 2-person gap for `deadline_greedy_v1` documents one heuristic limitation, not a global optimum claim.

These ranges and the adverse combination are synthetic fixture assumptions. They have no real-world probability interpretation. ADR-030 permits explicit engineering ranges without Philippine field measurements or external review; Task 3.9 must still record sensitivity for the declared PDF/OSM demonstration inputs.

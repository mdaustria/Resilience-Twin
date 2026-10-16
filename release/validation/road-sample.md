# Synthetic road sample review — Task 2.3

Date: 13 October 2026. Fixture: [`tests/fixtures/roads/reference-small.json`](../../tests/fixtures/roads/reference-small.json). This is an internally checked arithmetic reference. ADR-030 requires no independent reviewer or field travel-time evidence. The fixture supports engineering verification; it does not by itself complete the PDF/OSM milestone A demonstrations.

The graph has directed nodes A–G, with G isolated. A→B takes 2 seconds/2,000 mm. B→E has a 3-second local bridge edge and a parallel 1-second emergency-only edge; E→B takes 3 seconds. All three belong to `bridge-1`, so asset closure removes both travel directions and both eastbound segments. B→C→E and B→D→E each take 4 seconds/4,000 mm. E→F takes 2 seconds/2,000 mm. B→F is marked as an incomplete extent cut, so its tempting 1-second time must not become a valid route.

| Case | Hand-checked exact path | Time / length | Review reason |
| --- | --- | --- | --- |
| Car base | a-west, b-bridge-local, h-dest | 7 s / 7,000 mm | The emergency-only edge is unavailable to car. |
| Emergency base | a-west, b-bridge-priority, h-dest | 5 s / 7,000 mm | Explicit emergency profile admits the priority edge. |
| Bridge asset closed | a-west, d-north, e-north, h-dest | 8 s / 8,000 mm | North and south have equal cost; `d-north` wins stable lexical tie. |
| Node-via `no` north | a-west, f-south, g-south, h-dest | 8 s / 8,000 mm | With bridge closed, the specified a-west→d-north turn is forbidden. |
| Node-via `only` north | a-west, d-north, e-north, h-dest | 8 s / 8,000 mm | Other exits after a-west are forbidden. |
| Way-via `no` north exit | a-west, f-south, g-south, h-dest | 8 s / 8,000 mm | The a-west→d-north→e-north→h-dest sequence is forbidden. |
| Way-via `only` north exit | a-west, d-north, e-north, h-dest | 8 s / 8,000 mm | Each required via edge and final exit is enforced. |
| Ambiguous way-via | a-west, f-south, g-south, h-dest | 8 s / 8,000 mm | Exclude the affected way entry until review. |
| Conditional node-via | no route | — | Exclude all exits after a-west; no supported condition evaluation exists. |
| Reverse bridge | c-bridge-west | 3 s / 3,000 mm | Reverse segment is independent; bridge asset closure removes it too. |
| One-way reverse and isolated G | no route | — | No B→A edge and no edge enters G. |
| Boundary-only fallback | no route; boundary cut identified | — | Closure of valid B exits leaves only truncated B→F; never report success. |

All edge and turn IDs are explicit. The fixture's expected outcomes come from adding the stated integer edge weights and applying the stated restrictions, not from running the router to generate expected values. The test compares routing results against these fixed expectations and repeats them after edge/restriction input reordering. Unreviewed conditional or ambiguous turns are excluded conservatively. Disconnected and boundary-cut outcomes remain distinct. A later real road sample must establish OSM source date/license, geometry, restriction coverage, profile access, projection and extent cuts; the synthetic fixture cannot establish those facts.

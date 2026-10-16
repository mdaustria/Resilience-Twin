# Task 2.3 road reference fixture

`reference-small.json` is a synthetic directed graph with seven nodes, ten exact road edges and one disconnected node. Parallel eastbound edges and one westbound edge share a bridge asset. Travel seconds, integer millimeter lengths, vehicle profiles, restrictions and the boundary cut are declared fixture assumptions, not claims about an OSM import or either supplied PDF.

The `cases` array pins expected edge IDs, travel time and distance for base routes, closures, ties, node-via and way-via turns, conservative exclusion of uncertain restrictions, one-way access, reverse bridge access, disconnection and boundary truncation. Hand arithmetic and the expected paths are recorded in `release/validation/road-sample.md`. The Task 2.4 reuse comparison and Task 3.5 reviewed real road sample remain separate gates.

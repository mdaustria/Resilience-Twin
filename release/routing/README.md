# Task 2.4 routing reuse decision and evidence

[ADR-028](ADR-028.md) selects the standard-library exact-edge Dijkstra router
as the **one production routing implementation** for the Task 3.6 compiler.
The approved `pyvalhalla==3.9.1` remains a development-only comparison tool.
The selection rests on exact directed edge and asset closures, stable paths
and conservative turn semantics; it is not a speed ranking.

## Shared-source OSM comparison

[`osm_probe.py`](osm_probe.py) reads the pinned PBF directly and records a
bounded 328-node/527-edge car graph near bridge way `7010992` in
[`utrecht-bridge-graph.json`](utrecht-bridge-graph.json). The graph records
source tags, coordinates, OSM turn relations touching its ways, unknown-speed
and length assumptions, and boundary cuts. The relevant manually reviewed
source facts are bridge way `7010992` (`bridge=yes`, `layer=1`, no oneway),
continuing way `7010987`, and relation `153969` (`only_straight_on` from way
`310833905` through node `45150439` to way `51978656`). These are OSM facts,
not authority on field passability or disaster conditions.

Run the probe with `uv run python -m release.routing.osm_probe
release/routing/utrecht_netherlands.osm.pbf --bridge-graph
release/routing/utrecht-bridge-graph.json`. Benchmark with
`uv run python -m scripts.benchmark_routing --mode bridge-reference --output
release/routing/bridge-reference-benchmark.json` and the same command using
`--mode bridge-valhalla --config CONFIG --output
release/routing/bridge-valhalla-benchmark.json`. The raw
[`reference`](bridge-reference-benchmark.json) and
[`candidate`](bridge-valhalla-benchmark.json) files contain the exact paths,
input hashes, 25-call timings and process working-set peaks.

| Common case | Bounded reference | Valhalla full Utrecht tiles |
| --- | --- | --- |
| Forward/reverse bridge open | Both use way `7010992`, about 85 m; 7 s integer assumption | Both use way `7010992`, 0.085 km / 6.12 s |
| Forward bridge asset closed | Avoids bridge; 378.954 m / 50 s | Small midpoint exclusion polygon avoids bridge; 0.379 km / 47.228 s |
| Reverse bridge asset closed | Avoids bridge; 1,279.474 m / 122 s | Same polygon avoids bridge; 1.401 km / 138.796 s |
| Node-via `only` relation `153969` | Follows required way `51978656`; 278.167 m / 26 s. Without the restriction, a direct forbidden turn would be 20.903 m / 3 s. | Follows required way `51978656`; 0.277 km / 28.582 s |

The bounded and full graphs share the exact PBF source but differ in extent,
access compilation and cost rules. Reference timing medians were 1.4–12.7 ms
with 33.61 MiB process peak; candidate common-case medians were about
3.5–6.8 ms with 79.10 MiB process peak. These are machine observations, not
comparable throughput or capacity claims. The reference additionally showed
that closing **only** directed edge `osm:7010992:0:forward` reroutes forward
travel while reverse travel still uses the bridge. Valhalla's documented
route request has no exact directed-edge-ID closure parameter; the tested
polygon closes both directions. This semantic difference drives ADR-028.

The sampled OSM node-via `only` case does not prove all OSM relation classes;
way-via, uncertain/conditional turns, emergency profiles and equal-cost tie
behavior remain covered by synthetic reference tests and gated real-graph
compiler checks. The sample does not establish Philippine road quality.

## Earlier exploratory measurements

The two measured routes are **not on the same graph**. The standard-library
reference uses the reviewed synthetic graph in
`tests/fixtures/roads/reference-small.json`; Valhalla uses the Utrecht OSM
fixture below. The numbers describe feasibility only. They must not be ranked
as a performance comparison or used to select a production router.

## Source and replay

- Candidate: `pyvalhalla==3.9.1`, pinned in `pyproject.toml` and `uv.lock` as a
  development dependency for this evaluation. The Windows x64 `abi3` wheel
  installed under the approved CPython 3.13.16; its bundled tile builder
  successfully built the sample locally with two threads.
- OSM fixture: [`utrecht_netherlands.osm.pbf`](utrecht_netherlands.osm.pbf),
  11,785,991 bytes, SHA-256
  `8522f893d9c9c201d19d8fc0e39a038ad25fb21f6832370d4d257b4b495b9fa7`.
  Source: [Valhalla 3.9.1 test data](https://github.com/valhalla/valhalla/blob/3.9.1/test/data/utrecht_netherlands.osm.pbf).
  © OpenStreetMap contributors; the upstream test data is licensed under
  [ODbL](https://github.com/valhalla/valhalla#license). The original OSM
  extraction date is not recorded here, so this is not a production source
  snapshot. It does not establish Philippine road or hazard validity.
- Build a local config and tiles from the fixture with `valhalla.get_config`
  (`tile_extract=''`, tile directory under ignored `.runtime/`) and
  `uv run python -m valhalla valhalla_build_tiles -c CONFIG -j 2
  release/routing/utrecht_netherlands.osm.pbf`. The generated tiles are not
  checked in. The benchmark's Valhalla mode needs `--config CONFIG`.
- Run `uv run python -m scripts.benchmark_routing --mode reference --output
  release/routing/reference-benchmark.json` and the same command with
  `--mode valhalla --config CONFIG --output
  release/routing/valhalla-benchmark.json`. Each benchmark runs 25 route calls
  after graph/actor construction. Reported process working-set peak includes
  Python and native allocation in each separate process; it excludes tile
  building. The Python allocation figure excludes native allocation.

## Observations on this Windows host

| Path | Input and coverage | Median / p95 route call | Peak process working set |
| --- | --- | ---: | ---: |
| Standard-library reference | 14 synthetic reviewed cases, including exact asset closures, profiles, node/way-via rules, ties and boundary cuts | Case median mean 0.169 ms; largest case p95 0.511 ms | 22.59 MiB |
| Valhalla 3.9.1 | One Utrecht auto-costing request, 25 byte-identical route responses; 80 traced graph edge IDs | 11.212 / 15.135 ms | 79.98 MiB |

The raw artifacts are [`reference-benchmark.json`](reference-benchmark.json)
and [`valhalla-benchmark.json`](valhalla-benchmark.json). The candidate's
3.135 km / 312.845 s route is not comparable with the synthetic travel-time
assumptions. Its `trace_attributes` edge IDs come from a separate map match of
the output shape, not an exact edge path promised by the route response.

Valhalla's [route API](https://github.com/valhalla/valhalla/blob/3.9.1/docs/docs/api/route/api-reference.md)
documents polygon exclusions and geometry-matched cost factors. Neither is a
request parameter that names the precise directed graph edges belonging to a
bridge asset. Geometry exclusions can affect adjacent roads; cost factors are
preferences, not hard closures. No exact-edge closure or asset-to-edge mapping
was demonstrated. The Utrecht sample also has no independently reviewed
common graph for the reference router, no matched turn-restriction/profile/tie
cases, and no audited OSM extraction boundary. Integration would require
mapping source assets to Valhalla graph IDs and proving per-run exclusion,
including both bridge directions, or rebuilding tiles for each closure; those
steps are unmeasured and may be infeasible.

**Gate status:** Task 2.4's one-router selection is recorded in ADR-028.
The OSM graph compiler, Philippine source review and municipality-scale
performance remain later acceptance gates. Valhalla's development pin does
not authorize or imply a second deployed routing implementation.

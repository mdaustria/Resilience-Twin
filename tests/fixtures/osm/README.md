# Pinned OSM import fixture

Task 3.5 reuses the user-approved Utrecht PBF at `release/routing/utrecht_netherlands.osm.pbf`. The 11,785,991-byte file is not copied into this directory. Its SHA-256 and ODbL attribution are pinned in `packages/adapters/geo/catalog.py`. `tests/integration/test_osm_import.py` also uses a tiny malformed byte fixture and an outside-to-outside crossing to test rejection and extent cuts.

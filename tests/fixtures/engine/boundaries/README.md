# Hand-calculated population boundary case

`population-horizon.json` specifies 15 distinct people at a 10-second horizon.
Three are already sheltered; four finish unloading exactly at their 10-second
deadline; two remain on an edge with a deadline of 8; five are waiting with a
deadline of 12; one has not yet requested evacuation (request at 11).

Expected terminal buckets: 7 sheltered, 2 in transit, 5 waiting, 1 not
requested. Four on-time arrivals, two deadline misses, five pending people,
two unfinished movements and seven unserved people. The three initial
occupants are counted once in sheltered occupancy, not as new arrivals.

`disruption-at-horizon.json` places a shelter closure, arrival completion and
deadline at second 10. The closure executes first, so four people remain
unloading and miss the deadline; the attempted completion is not an arrival.

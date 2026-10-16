# Tiny synthetic sensitivity cases — Task 2.12

[`tiny-cases.json`](tiny-cases.json) fixes four integer-unit low/nominal/high ranges with explicit synthetic provenance. The adverse case takes high travel, high loading, earlier demand, and high per-person water use. Every expanded case pins the same fictional exogenous hash; each baseline/variant pair receives exactly the same configuration and policy version.

The two-group calculation is intentionally small enough to check by hand. Group 1 has four people and a 5-second deadline; group 2 has four people and an 8-second deadline. At nominal loading and request timing, low travel gives baseline 4 versus variant 8 people on time; high travel gives baseline 4 versus variant 0. Water demand uses 1/2/3 mL per person-second, integer inventory and a 10-second horizon. This is an arithmetic policy-sensitivity fixture, not a Philippine travel, evacuation, water-use, probability, or optimality estimate.

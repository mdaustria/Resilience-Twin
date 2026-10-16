# Hand-calculated water boundary case

`final-interval.json` has a five-second horizon and no ordinary events. The
terminal event must integrate all five seconds. Two initial shelter occupants
need 2 mL/s, a waiting resident needs 0.5 mL/s, and a resident in transit needs
1 mL/s. Their separate supply locations start with 7, 2 and 0 mL.

At second 5, integer demand is 10 + 2 + 5 = 17 mL; 9 mL is supplied and 8 mL
is unmet. The waiting resident carries half a milliliter into the next
interval. The shelter first runs dry at second 4, the pickup store at second
4, and the explicitly empty transit store at second 0. These are the first
whole seconds where accrued integer demand reaches available stock.

# Hand-calculated trip and resource case

`trip-small.json` has four passengers and a four-seat vehicle. Empty pickup
travel takes 5 s and 100 mm; loading takes 3 s; passenger travel takes 10 s
and 400 mm; unloading takes 2 s; required return takes 8 s and 300 mm.
Dispatch at second 0 yields pickup at 5, loaded at 8, shelter arrival at 18,
unloaded at 20, vehicle/crew release at 28, and 800 mm reserved distance.
The shelter holds 2 initial occupants and has 6 seats, so the four incoming
passengers fill its last places. Vehicle and crew windows through second 30
cover the complete trip. A 799 mm budget or a window ending at second 27 must
reject the trip before any reservation.

The fixture uses integer seconds, people, and millimeters. Road paths are
already reviewed route results; route compilation and policy choices are
separate tasks. A cancellation releases unused distance and shelter seats;
actual traveled distance remains spent.

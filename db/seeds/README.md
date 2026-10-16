# Firestore test data

There is no production seed. Integration tests create distinct temporary
owners with the same synthetic source checksum in the emulator, then
delete emulator data. Never seed a real user's workspace or copy analysis
across owners. A cloud smoke uses a unique nonproduction prefix and cleans up
only its own records.

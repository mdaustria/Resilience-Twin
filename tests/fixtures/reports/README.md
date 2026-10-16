The Task 5.6 browser fixture creates a one-page fictional PDF in the emulator-backed
guest workspace. `inspect_pdf.py` extracts text from downloaded PDF bytes with the
approved `pypdf` runtime so the test can verify labels, source hash and outcome claims.
The full public source PDFs are separate Task 5.7 cases.

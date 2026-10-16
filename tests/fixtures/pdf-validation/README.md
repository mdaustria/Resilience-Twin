# Task 3.1 generated PDF tool fixtures

`scripts/probe_document_tools.py` creates small original PDFs in memory: a clean
one-page PDF, an encrypted PDF, and a JavaScript `OpenAction` PDF. It also
passes malformed and oversized PDF-like bytes. No uploaded or user-supplied
document is copied into fixtures. `tests/contracts/test_provider_configuration.py`
checks the observed parser classifications and exact pinned versions.

These are bounded selection cases. They do not prove malware scanning,
resistance to every active PDF feature, full-size source compatibility, or
the later Task 3.2 intake contract. Run the probe with `--require-scanner`
against a verified ClamAV 1.5.4 binary and fresh signatures before recording
scanner acceptance. If the scanner is absent, that command exits nonzero.

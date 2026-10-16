# Document processing decision record — Task 3.1 (13 October 2026)

Status: **Task 3.1 decision and compatibility gate complete**. The user approved `google-genai==2.29.0`, `pypdf==6.20.1`
and ClamAV `1.5.4` for the Phase 3 pipeline. The two Python packages are pinned
in `pyproject.toml`/`uv.lock` and locally installed. The approved ClamAV Windows
runtime and fresh signatures pass the local scanner selection probe; Ubuntu
24.04 CI also passed. Production packaging remains a later task. The Gemini key is present in
Windows user environment scope and is never stored in this repository. A
14 October 2026 user screenshot identifies project `AI Projects`
(`ai-projects-250716`), billing account `WTI Offline Billing Account`, and
Postpay Tier 3. A user-console lookup on 13 October 2026
verified access through Gemini Developer API `v1` to the exact listed model
`models/gemini-3.8-flash`. A second user-console run successfully processed a
431-byte synthetic blank PDF with that exact model. Task 2.1's input-based
protocol is complete (ADR-030). At the Task 3.1 selection gate, no source PDF
had been sent to Gemini. Task 3.3's later bounded pilot is recorded below.

## Candidate provider configuration

`release/providers.json` records the **disabled** Gemini Developer API path:
`google-genai==2.29.0`, API `v1`, exact model `gemini-3.8-flash`, and no
automatic global fallback or search grounding. The model is a candidate for
page-group extraction; the bounded live synthetic-PDF probe with the actual key
verified project access and the returned exact model. SDK documentation confirms
explicit API-key client creation and API-version selection. [SDK release](https://pypi.org/project/google-genai/2.29.0/), [model](https://ai.google.dev/gemini-api/docs/latest-model).

The [Gemini API terms](https://ai.google.dev/gemini-api/terms) classify API use
through a project with active Cloud Billing as a Paid Service. Google states
that paid prompts, files and responses are not used to improve its products.
It logs prompts and responses for abuse monitoring and may store or cache them
in any country where Google or its agents maintain facilities. The
[abuse-monitoring policy](https://ai.google.dev/gemini-api/docs/usage-policies)
states a 55-day retention period; the default project log window is also 55
days and can be shortened separately in AI Studio. This Developer API path is
therefore not region-pinned and zero data retention has not been approved for
this project. Grounding, File API storage, explicit caching and Interactions
state storage remain disabled. The [document guide](https://ai.google.dev/gemini-api/docs/document-processing)
describes PDF visual input and a 50 MB/1,000-page API limit, which covers the
size/page minima of the two supplied files on paper. That is a provider limit,
not an application throughput or quality result. Use bounded page groups and
preserve source-page mapping; never silently omit image or split-table regions.

Keep the Gemini key only in `GEMINI_API_KEY` on the backend (Secret Manager in
deployment). Never commit it, pass it to the browser, echo it in test output,
or include source pages in logs. A live probe must use a small synthetic PDF,
record the project/tier, model ID, endpoint/API version, request ID if exposed,
token/cost estimate, returned version metadata, and outcome without content.
`scripts/probe_gemini_provider.py` implements one blank-page synthetic PDF
request to the exact candidate model with a 64-output-token cap and 20-second
timeout. It prints only status and metadata; it never prints the credential or
response text. On 13 October 2026 it returned `ConnectError` before receiving
a response, both in the default sandbox and with network escalation. DNS
lookup of `generativelanguage.googleapis.com` also failed from the execution
host. A later lookup from the user's normal console succeeded at
`2026-10-13T07:34:38.733687+00:00`, verifying the endpoint, API version,
credential acceptance and exact model lookup. The bounded generation succeeded
at `2026-10-13T07:36:30.994002+00:00` with response ID
`297NavGZM9Xn1e8P5tOKwAU`, returned model `gemini-3.8-flash`, 538 input tokens,
1 output token, 24 thinking tokens and 563 total tokens. The 64-token output cap
held and response text was present but was not printed or stored. At the paid
standard introductory rates published for 13 October 2026 ($0.75/million input
tokens and $3.75/million output tokens including thinking), the calculated
request cost is $0.00049725; free-tier cost would be zero. The actual key tier
is now verified as Postpay Tier 3; the billed amount remains unverified.
[Pricing](https://ai.google.dev/gemini-api/docs/pricing).

Tier 3 is a quota tier, not an application budget. Official limits include a
$200 rolling ten-minute spend-rate limit, a $20,000–$100,000+ billing-tier cap,
and 1,000,000,000 Gemini 3.8 Flash batch-enqueued tokens. The owner-reported
interactive display for `gemini-3.8-flash` showed RPM 1/20,000, TPM 538/20,000,000
and RPD 1/unlimited, recorded as displayed usage versus limit rather than a
guarantee of available capacity. The probe itself permits one call, caps model
output at 64 tokens and uses a $0.01 review threshold. The owner confirmed an
authorization key limited to Gemini and a $50 monthly project cap; this cap
may overrun during billing latency and is not a total Google Cloud budget. The
general public-upload provider route remains disabled until the later ingestion
and ownership safeguards are implemented. Only the two hash-pinned public pilot
sources are enabled for the Task 3.3 local runner.
[Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits),
[billing](https://ai.google.dev/gemini-api/docs/billing),
[zero data retention](https://ai.google.dev/gemini-api/docs/zdr).
On 14 October 2026, the user confirmed both supplied pilot PDFs are publicly
available and authorized their use for this project. No separate official or
source-owner approval is required for these two pilot inputs. Future public
uploads still need a clear processing notice and user acknowledgment of the
actual provider retention/deletion terms. Public availability does not verify
the project-level provider controls listed below.

Processing disclosure for the future public upload flow: Before upload, tell
the user that the original document will be stored privately for the analysis;
after validation, selected page groups may be sent to the Gemini Developer API
to suggest facts for personal review. The Gemini Developer API is not region
pinned. Paid-service content is not used for product improvement; provider abuse
monitoring may retain content for 55 days, while the owner reports seven-day
project logs and data sharing off. The source PDF is immutable, model suggestions
are not verified facts, and only the deterministic engine computes outcomes.
Require the uploader to acknowledge this processing and confirm permission to
submit the document. Publish the measured application storage, deletion and
backup periods before public uploads are enabled; the temporary limits in the
PRD are targets until operationally verified, and saved-work retention remains
a later product decision. This records the Task 3.1 terms without claiming that
the public upload UI or operational retention gate is complete.

## Local PDF gate selection

### Task 3.3 bounded public-source pilot (14 October 2026)

After the complete local intake gate in 3.2, the user-authorized public QC and
Guiguinto PDFs were sent as source-bound groups of at most eight pages to the
configured Gemini Developer API `v1` model `gemini-3.8-flash`. The runner accepts
only the two known source SHA-256 values, checks the original bytes, limits each
page slice and response to 10 MB and 1 MB, caps output at 8,192 tokens per call,
and has a configurable five-dollar maximum estimated paid usage per source run.
It used inline PDF data; no File API, grounding, caching, or fallback model was
enabled. Exact raw responses are saved for offline replay, with byte-stable Git
attributes. The general public-upload flag remains false; the pilot-only flag
is true for these two source hashes.

All 112 QC and 191 Guiguinto physical pages were grouped without truncation.
QC had 14 live groups, 21 candidates after unit validation and an estimated
$0.070033 usage. Guiguinto had 27 groups (25 new calls plus two earlier pilot
groups), 151 candidates after unit validation and an estimated $0.183221 usage.
These are estimates from provider token metadata at the published introductory
rate, not verified billed charges. Both source cases have separate critical-fact
review records in `release/validation/extraction/adjudication.json`; automatic
candidate coverage is not a correctness or run-readiness score. Split-table
slice-relative page numbers were mapped to the original physical page only
when the cited region matched; original raw responses were preserved. Invalid
percentage/currency units were rejected. Image-table values, the 3,987/4,087
capacity conflict, shared facilities, proposed resources, missing QC annexes
and qualitative pickup statements are recorded with distinct manual review.
Provider abuse-monitoring retention and the owner-reported seven-day project
log setting described above apply to these pilot requests.

### Selected parser and scanner

`pypdf==6.20.1` is a BSD-licensed pure-Python PDF parser supporting the pinned
Python 3.13 runtime. Use strict parsing, original-byte SHA-256, byte/page caps,
encryption rejection, and bounded checks for active entries. The local probe
generates clean, encrypted, JavaScript-action, malformed and oversized cases;
its result is selection evidence only. In Task 3.2 the intake adapter must
quarantine original bytes, scan before extraction, keep all page indexes,
preserve source bytes, and fail closed if parsing/scanning fails. Sparse text
does not imply an empty page or complete visual coverage. [pypdf release](https://pypi.org/project/pypdf/6.20.1/).

ClamAV `1.5.4` is selected as the separate malware scanner. Official release
metadata lists Windows x64 and Linux x64 assets; the Windows zip SHA-256 is
`0d9e0228b2674137ea1a2853566c98a0278ad52ab2582c3d6dbd75373848c395`.
The direct release URL failed DNS resolution, but the official GitHub asset API
delivered the same archive. Its SHA-256 matched the published digest. FreshClam
downloaded and tested the current local signature set (`daily.cvd` version
28152, built 13 October 2026). The scanner-required probe passed with
`clamscan` 1.5.4: clean PDF exit 0 and benign custom-signature detection exit 1.
The host antivirus intercepted the standard EICAR string before ClamAV could
read it, so the custom signature checks ClamAV's detection path without
disabling host protection. This verifies local Windows behavior; the hosted
Linux result is recorded below. Production signature update/packaging remains
open. Production ingestion must
fail closed when ClamAV is missing, signatures are stale, it times out, or it
returns an error. Parser checks alone are not malware clearance. [ClamAV
release](https://github.com/Cisco-Talos/clamav/releases/tag/clamav-1.5.4),
[install guidance](https://docs.clamav.net/manual/Installing.html).

On 14 October 2026, Task 3.1 added a Linux GitHub Actions step that downloads
the exact approved 1.5.4 Debian package, verifies the official release digest,
updates signatures and runs the scanner-required clean/detection probe. The
workflow had not yet run on GitHub at that point. The later hosted result and
owner-reported settings below supersede those earlier gaps.

Later on 14 October, the user specified target controls: restrict the key to
the Generative Language API, request a $5 monthly project spend cap, select
seven-day AI Studio project-log retention, and leave data sharing disabled.
These historical targets remain recorded separately from the later owner report
in `release/providers.json`; the $5 target was superseded by the user-approved
$50 cap. The in-app
browser reached Google sign-in, so the project settings could not be inspected
or applied in this session. After sign-in, verify the exact project and each
saved setting without exposing the key. [Gemini billing guidance](https://ai.google.dev/gemini-api/docs/billing)
says project caps are experimental, can overrun during billing latency, and
are unavailable to invoiced/offline accounts. The recorded billing account's
display name includes "Offline", but its account type and cap eligibility must
be checked in AI Studio rather than inferred from that name. A $5 cap is a
project monthly Gemini API control only if the console actually offers and
saves it; it is not a total Google Cloud budget. [AI Studio log guidance](https://ai.google.dev/gemini-api/docs/logs-datasets)
allows seven-day project-log retention. That setting does not replace the
separate 55-day provider abuse-monitoring retention described above.

The user subsequently relayed the project owner's confirmation that the key
for `ai-projects-250716` is limited to Gemini, project logs are capped at seven
days, and data sharing is off. The owner later identified the key as an
authorization key, reported the active rate-limit display above, and updated
the approved monthly project cap from $5 to $50. These are owner-reported
settings, not independently inspected console settings, and are recorded as
such in `release/providers.json`. On the same day,
an isolated CI branch was prepared with the pinned ClamAV Linux step, but
automatic approval review rejected publishing repository files to the remote.
The only installed local WSL distribution uses musl rather than the approved
Debian package's glibc target; Docker's Linux service could not be started.
After the user explicitly authorized the push, the isolated branch ran on
GitHub Actions Ubuntu 24.04. [Run 38518985622](https://github.com/mdaustria/Resilience-Twin/actions/runs/38518985622)
passed on commit `88ac5431f7da3bd252c343593dd63d487fd8a5a7`: the exact
ClamAV 1.5.4 Debian package hash matched, fresh signatures loaded, the clean
fixture exited 0, and the benign custom-signature fixture exited 1 with
`scanner_status=verified`. Frozen installs and the branch combined check also
passed. Production image packaging remains open for the later runtime task.

## Downstream gates

1. Use Task 2.1's frozen input-based verification protocol (ADR-030). No
   field-reference review or independent approver is required. Full PDF/OSM
   demonstrations and milestone A engineering evidence remain Task 3.9 work.
2. Preserve the owner-reported authorization key, Gemini-only scope, $50 cap,
   displayed interactive limits, seven-day logs and disabled data sharing.
   Do not submit either supplied PDF until the Task 3.2/3.3 intake/extraction
   paths and their bounded provider-work controls are ready.
3. Linux CI signature update and safe detection passed on the pinned runner.
   Package a fail-closed scanner for the intended production runtime in Task 6.2.
4. The public-source basis and processing terms are recorded above. Implement
   the upload acknowledgment and verify measured application retention before
   public release. Confirm complete-file intake limits and actual provider
   processing for both PDFs before Task 3.2/3.3 acceptance.

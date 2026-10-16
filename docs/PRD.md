# Resilience Twin — Product Requirements Document

Status: Public-use product plan for product and engineering review  
Date: 15 October 2026\
Target: Public researchers, residents, students, and community groups evaluating publicly available Philippine community/municipal disaster plans

## 1. Problem

Researchers and residents can read a publicly available Municipal Disaster Risk Reduction and Management (MDRRM) plan but may struggle to assess its assumptions, omissions, and operational weaknesses. Roads may become inaccessible, shelters may fill, vehicles may be insufficient, and supplies may run out. A static plan rarely reveals how those failures interact over time.

Resilience Twin turns an existing MDRRM PDF and a text location into a reviewable community model, tests that model under disruptions, and returns ranked weaknesses and proposed fixes. It treats hazard conditions as inputs. In the pilot, Gemini interprets documents and can explain results; deterministic code calculates routes, movement, occupancy, inventories, and outcomes. Users configure scenarios and proposed changes. AI-generated scenarios and replanning are later extensions.

The central question is: **Given this community's roads, shelters, population, vehicles, and supplies, what fails first, who is affected, and which changes improve the result?**

## 2. Users and access

The first release offers one **Start analysis** flow without sign-in (ADR-031). Anyone can upload a public disaster-plan PDF, enter a textual location, review evidence and assumptions, see results, and download reports. There are no user accounts, saved cross-session analyses, or saved conversations. No government affiliation, invitation, resource-owner confirmation, or official approval is required. A municipality is the subject of an analysis, not the owner of every analysis about it.

| User | Primary needs | Permissions |
| --- | --- | --- |
| Researcher or student | Inspect evidence, reproduce findings, test assumptions, and compare alternatives | Create, edit, run, export, and delete their own analyses |
| Resident or community member | Understand the local plan, identify gaps, and explore possible improvements | The same workspace-owner capabilities, without specialist or government credentials |
| Civic or community-group member | Prepare an evidence-backed assessment and proposed revisions | The same personal-workspace capabilities; multi-user collaboration is deferred |

Each workspace belongs exclusively to one temporary browser session. Users can upload, review evidence, run simulations within visible limits, compare hypothetical revisions, and download reports during that session. Refresh/reconnect with a valid credential resumes only the active analysis; a later new session starts fresh. Shared editing is deferred. Access to an analysis never grants authority over the municipality or source plan. Government employees may use the same public flow without special powers.

### Temporary analysis lifecycle

- A temporary analysis is private, absent from account history, and accessible only through its current browser session. It uses short-lived server storage for uploads and background processing; “temporary” does not mean zero storage.
- Initial product defaults: expire after **2 hours without deliberate user activity**, with an absolute **24-hour maximum** from creation. Background jobs and automatic polling do not extend the session. Show the expiry time and warn before it expires; allow deliberate activity to refresh the idle window only within the absolute maximum.
- Refresh/reconnect works while the session credential remains valid. Closing a tab/browser is not a reliable deletion signal and does not promise immediate erasure. Losing the session credential makes the analysis unrecoverable; there is no cross-device recovery or emailed access link.
- **End and delete analysis** immediately revokes access and requests cancellation/deletion. Expiry does the same automatically, including for running jobs. Active application copies must be purged within 24 hours after termination; backups containing temporary data expire within at most 7 days. Provider retention must be separately verified and disclosed before launch. Deletion does not remove reports already downloaded by the user.
- Download reports before ending the session or reaching expiry. The app provides no account history, saved conversations, emailed recovery links, or cross-device restoration.
- Sessions have visible upload/run/concurrency limits and abuse controls. Reaching a limit preserves available results until expiry and permits download; completed results remain downloadable without sign-in.

All workspaces are private by default. A publicly available source document does not make an uploaded copy, derived model, or result publicly visible in the app. Recommendations and proposed revisions belong only to the current workspace until its owner downloads them. The app does not modify the source document, publish a revised municipal plan, or send recommendations to officials. Every result is labeled an independent analysis, not an official assessment or endorsement.

## 3. Goals

1. Let any researcher or resident create an inspectable analysis from a public disaster-plan PDF and location without specialist modeling skills.
2. Make every important input traceable to a document page, reviewed external source, user correction, or explicit assumption.
3. Identify repeated and severe operational failures rather than reduce resilience to a single pass rate.
4. Demonstrate whether proposed changes improve outcomes across the same reproducible scenarios.
5. Keep recommendations and hypothetical plan revisions under the current user's control, with private versions, evidence, and comparisons that leave the source plan unchanged.
6. Deliver a reliable cloud application that isolates workspaces, expires temporary analyses predictably, and makes limitations visible alongside results.

## 4. Non-goals

- Predicting typhoon tracks, rainfall, flood depth, or bridge structural failure.
- Replacing hazard agencies, municipal command processes, engineering assessments, or professional judgment.
- Automatic dispatch, public alerts, evacuation orders, procurement, or changes to field operations.
- Use as the operational command system during an active disaster.
- A full hydrodynamic model, household-level agent simulation, or simulation of every hazard in the first release.
- Certifying that a community is safe or that a plan will succeed in the real world.
- Automatically rewriting or publishing an official MDRRM PDF.
- Municipal verification, official approval workflows, departmental resource certification, or government-only access.
- Offline extraction or simulation in the initial production release.
- Sign-in, account management/recovery, persistent user analysis or conversation history, and cross-device saved work.

## 5. Product scope and operating assumptions

The initial simulation focuses on flood-related evacuation and water sufficiency over a configurable horizon, defaulting to 72 hours. It models road accessibility, shelter capacity, vehicle availability, evacuation deadlines, and water consumption. Power and communication loss have explicitly configured operational effects, such as dispatch delays or facility unavailability; they are not full infrastructure-network simulations.

Population is modeled as aggregate groups associated with barangays or confirmed evacuation pickup points. Travel includes configurable vehicle capacity, availability, loading and unloading time, repeated trips, and route travel time. Each vehicle needs reviewed crew availability and a finite operating-distance budget representing fuel limits; unlimited shifts or fuel cannot be silently assumed. The pilot assumes dedicated crews, with no crew sharing or in-scenario refueling. Unsupported operations require a revised scope or remain unmet demand.

Shelter admission capacity, population conservation, and nonnegative water inventory are hard constraints. Water sufficiency is an evaluated outcome: the safety-first policy may evacuate people to a shelter with a projected shortage when this improves on-time evacuation. Such arrivals are never labeled water-sufficient. Findings distinguish arrival before the deadline from sustained shelter/water sufficiency. Pre-scenario water redistribution is supported; in-scenario supply transport and resupply are deferred. Other evacuation modes must be represented explicitly; walking or private transport must not be silently assumed.

Initial shelter occupants must be linked to distinct population cohorts and counted once in capacity, consumption, and population totals. At the evaluation horizon, the engine accounts for consumption through the final interval, retains unfinished movements, and reports pending demand and deadlines beyond the horizon as unevaluated rather than successful.

The pilot uses historical and hypothetical scenarios configured and reviewed by users. A versioned hazard-input format supports future forecast integrations. Rainfall descriptions alone do not determine road closures: affected roads and facilities require reviewed hazard mapping or explicit scenario assumptions.

The app evaluates the documented plan and a declared computational interpretation of it. Map modeled procedures to cited plan passages where possible. If the document omits an operational rule, any default allocation policy is an explicit modeling assumption, not a claim about what the municipality actually does. Separate document gaps, modeled failures, policy-dependent findings, and hypothetical improvements. An absent fact is not proof that a resource does not exist.

Four primary screens support the complete loop:

**Community Twin → Scenario → Live Simulation → Resilience Findings → Explore Improvements → Run Again**

Upload, evidence review, data correction, workspace variants, and comparison are panels or states within these screens rather than additional primary screens.

### 5.1 Supplied-plan compatibility and geographic scope

The two sources identified by filename, checksum and physical page count in [the PDF input review](pdf-input-fit-review.md#inspection-and-source-identity) are separate required compatibility cases. Each starts its own analysis; neither is presumed to contain every operational input. Acceptance requires both outcomes below for each source, after source/provider processing gates pass. The only required external inputs are the PDF and a textual location for OSM. “Supplemented” means missing computational values completed by explicit, user-visible modeling assumptions; no extra document, field measurement, event report or external approver is required. Optional additional evidence remains supported.

| Source | Source-only outcome | Supplemented-run outcome |
| --- | --- | --- |
| `QCDRRMP-2021-2027_Volume-1.pdf` | Review all 112 pages, preserve historical demographics and proposed district shelters as documentary evidence, identify referenced but unsupplied annexes, and export unresolved operational gaps with simulation not performed | Use cited cohorts/resources where available and explicit hypothetical cohorts/pickups, resources, water and timing where missing, with pinned OSM roads for an explicitly selected QC study area; seal reviewed inputs, run baseline and disruption, compare a paired hypothetical change, and export scoped findings |
| `Guiguinto-MDRRM-PLAN-2023-2025.pdf` | Review all 191 pages, expose image-table/split-header coverage, source capacity units/ranges and the 3,987 subtotal versus 4,087 printed-total conflict, and export the remaining gaps with simulation not performed | Resolve capacity units, shared facilities, applicability dates and conflicts; supplement resource, water, geography and scenario gaps for a declared study extent; complete the same baseline, disruption, paired-change and export loop |

QC simulation acceptance covers an explicitly selected study area, as chosen by the user on 13 October 2026. Record its named barangays/pickups, boundary, included population and resources, road extent/buffer, cross-boundary assumptions and exclusions before sealing. Preserve city-wide source evidence during review, but do not use city totals as study-area demand without an explicit supported allocation. Reports and comparisons identify the modeled extent; a study-area result establishes no whole-QC result for all 142 barangays. The concrete area is selected and reviewed during geography preparation. Guiguinto also requires a declared modeled extent and explicit exclusions; documentary coverage alone establishes no municipal-scale simulation claim.

The guest-only flow must support each complete source individually: 112 pages / 2,943,608 bytes for QC and 191 pages / 9,418,109 bytes for Guiguinto. Published per-file intake and extraction limits must accommodate at least 191 pages and 9,418,109 bytes; these are acceptance minima, not measured throughput or final quota settings. Bound page-group work and publish separately measured limits for supplementary documents, total workspace usage and simulation size. Never silently truncate pages, entities or geography. Verify local intake/extraction in milestone A, the guest-only flow and isolation between independent sessions in milestone B, and actual throughput/session-lifetime feasibility before milestone C. The provisional 25-barangay performance benchmark remains separate from full-document support and does not establish whole-QC capacity.

## 6. Core flows

### 6.1 Upload and generate the community twin

1. The user selects Start analysis to create a temporary private workspace. The app displays expiry, processing/deletion terms, and limits before upload, without an account requirement.
2. On Community Twin, the user uploads a publicly available MDRRM PDF, records its public source URL or publication reference and date when known, and enters a location, such as “Guiguinto, Bulacan.” Source metadata is provenance, not a government-approval requirement.
3. The app resolves the location and requests confirmation when boundaries or place names are ambiguous.
4. Gemini extracts barangays, population groups, vulnerable areas, evacuation centers, capacities, vehicles, bridges, routes, water and other supplies, critical facilities, and emergency procedures.
5. The app retrieves an OpenStreetMap road and bridge network for the confirmed area and records a dated source snapshot.
6. Community Twin displays a map, entity counts, extracted records, citations, uncertain matches, and a completeness checklist. Detected counts must reflect actual extraction, not preset examples.
7. Users inspect PDF page references, correct records, confirm locations and road connections, and review possible duplicates and conflicting values.

Account for every physical page and relevant content region as processed, unresolved or failed. Nonempty text does not prove that image tables or graphic marks were read. Use the approved visual/OCR path or manual recovery for such regions, preserving physical-page citations and split-table/header relationships. Show unresolved coverage; do not present an incomplete extraction as complete.

Unlocated facilities and unresolved road connections remain visible as unresolved. The app must not fabricate coordinates or silently attach a facility to an arbitrary route. Large population groups require reviewed pickup locations or explicit spatial assumptions; a barangay centroid is an assumption, not a verified assembly point.

### 6.2 Fill missing information and confirm the twin

1. Missing essential fields appear in a review checklist. The app may provide a minimal public-context Google Search query for the user to open independently; it does not collect search results.
2. The user supplies public evidence, a source URL, an attributed assertion, or an explicit assumption. Candidate evidence records title, retrieval date, publication date when available, municipality match, and proposed fact. Government or original institutional sources are preferred, but contact with officials is not required.
3. When choosing optional additional evidence, users inspect the underlying source and attach a permitted excerpt or document page. An explicit assumption needs no additional document. The pilot records URLs without automatically fetching them. A search snippet alone cannot establish a confirmed operational input. Inaccessible sources remain unverified; user assertions and assumptions retain their distinct labels even after user review.
4. The user reviews candidates, resolves conflicts, or supplies a correction. Search findings never silently overwrite confirmed values.
5. Each material field records its provenance, review status, uncertainty, units, and applicable date. Values distinguish PDF extraction, external evidence, user assertion, and explicit assumption.
6. Exploratory runs may proceed with declared assumptions. If an essential computational input has neither a usable value nor an explicit assumption, the run is blocked with an actionable explanation.
7. The app presents available values and versioned defaults in one compact assumptions summary. The user can accept or edit those assumptions together and save a runnable baseline version. This is personal review, not certification. No independent reviewer or official approval is required. Missing essential numeric values block only simulation; users can still inspect extracted records and export a document-gap assessment clearly labeled “simulation not performed.” An unknown value can be replaced with an explicit plausible assumption for an exploratory run, never silently with zero.

Preserve statement type (reported existing resource, proposed/target, historical observation or scenario assumption), applicable date, geography, original quantity/unit/range and source fragment separately from the normalized operational value. Proposed shelters, procurement budgets and household water connections are not available shelter, fleet or water inventory. Review applicability to the scenario date, including Guiguinto's 2023–2025 plan period; historical scenarios remain supported. A plan title or user acknowledgment does not make an old fact current.

Families cannot silently become people; ranges cannot silently become endpoints. Retain any accepted conversion/allocation rule, its explicit assumption and integer result. Distinguish blank/unknown cells from reviewed absence symbols, allocate shared facilities only once, and separate overlapping population/exposure counts. Preserve conflicting source values and arithmetic discrepancies alongside the reviewed resolution; never overwrite a source total to hide a conflict.

For each computational gap, show the missing field, why the engine requires it, the evidence or explicit assumption that can fill it, and the conclusions dependent on it. Supplementary documents and annexes belong to the same analysis with their own immutable source identity and citations. Corrections recompute readiness and invalidate affected acknowledgments. Walking, staged transfers and resupply procedures remain visibly unmodeled where the engine does not support them; they cannot silently supply movement or water inputs.

Manual evidence review is the production-pilot acceptance path. Automated Google Search discovery and source fetching are later features, gated on a suitable provider contract, source rights, and security validation. They are not pilot launch dependencies.

Essential input categories include population and pickup locations, initial shelter occupants, shelter capacities, a usable road graph and access points, vehicle capacity, crew availability, operating-distance budgets, movement timing, evacuation deadlines, initial water inventory, and consumption rates. OSM bridge records do not by themselves establish structural condition, clearance, or safety.

### 6.3 Create and review a scenario

1. On Scenario, the user selects a historical or hypothetical scenario and an evaluation horizon.
2. The user configures a scenario from reviewed hazard history or explicit hypothetical assumptions. A deterministic summary describes the configured inputs. Invented scenario names and events are labeled hypothetical.
3. A structured editor exposes displacement by population group, evacuation demand timing, deadlines, road closures, shelter restrictions, vehicle outages, and power or communication effects.
4. The user reviews the parameters, assumptions, and disruption schedule. Narrative content cannot silently alter engine inputs.
5. The app saves an immutable scenario version, validated input configuration, and random seed where sampling is used.

### 6.4 Run the live simulation and break the plan

1. On Live Simulation, the user starts a baseline run and can play, pause, or change playback speed.
2. The timeline and map show demand, vehicle movements, accessible routes, shelter occupancy, water remaining, and unresolved demand.
3. “Break My Plan” runs a disruption or a reproducible suite: bridge or road closure, shelter capacity loss, vehicle outage, power or communication loss, and sudden displacement.
4. The engine updates routing and allocations using a versioned deterministic policy subject to the configured constraints. Simulation requires no Gemini calls.
5. Users edit a hypothetical preparatory proposal in their workspace and evaluate it as a separate run against the same scenarios. Mid-run AI branches are deferred. The source plan and other users' analyses are unchanged.
6. The event log records the disruption, deterministic response, constraint violations, and resulting metrics. A Gemini outage may delay extraction or optional explanations but cannot interrupt a prepared simulation; explanations have a deterministic template fallback.

The engine must preserve population and inventory accounting, prevent double-booking of vehicles, enforce route accessibility and shelter limits, and expose unmet demand. It must not represent impossible assignments as successful evacuations or silently discard unserved residents.

### 6.5 Explain findings and compare improvements

1. Resilience Findings ranks weaknesses using engine evidence: affected residents, missed deadlines, scenario recurrence, shelter demand beyond capacity, and water shortfall timing.
2. Each finding includes the affected locations and groups, triggering disruptions, evidence from the timeline, uncertainty, recurrence count and denominator, and proposed actions.
3. Rule-based recommendations and user-authored proposals may include alternate routes, pre-scenario vehicle repositioning, pre-scenario water redistribution, or revised shelter preferences. Resource additions and unsupported capabilities are labeled as requirements, not existing assets. AI recommendation generation is deferred.
4. The user selects a proposal and inspects a concrete diff of changed assumptions, assignments, resource quantities, and operating rules.
5. The app runs the proposed version against the same scenario suite and seeds. It reports improvements, unchanged failures, and regressions within that workspace.
6. The user saves, renames, compares, or discards their hypothetical variants. No submit-for-approval or municipal adoption step exists.
7. Saving a variant creates a new version without overwriting the original PDF, baseline, or earlier evidence. The app never implies that a saved proposal has been adopted or implemented.
8. Users download an independent findings report containing source publication details, scope, versions, assumptions, evidence, simulation/comparison status, recommendations, and a proposed-revision diff. Untested recommendations are labeled untested; report text does not amend the source plan.

## 7. Feature priorities

### Must have for initial production

- The four-screen workflow, responsive for desktop and tablet use.
- Guest-only on-demand analyses; private temporary-session ownership, visible expiry, end-and-delete, and isolation between users analyzing the same municipality or PDF.
- Asynchronous PDF extraction with progress, recoverable failures, page citations, and editable records.
- Text location resolution and versioned OSM road-network ingestion with geographic review.
- Missing-data checklist, manual source submission and user review, conflict handling, and provenance tracking; official resource confirmation is optional evidence, never an access gate.
- Separate document-review and simulation-readiness checks; permit gap assessment without a runnable model and exploratory simulation with explicit assumptions.
- A deterministic flood-evacuation and water-inventory engine with explicit constraints and documented model assumptions.
- Reviewed structured scenarios, saved seeds, individual disruptions, and repeatable scenario suites.
- Live timeline playback, map visualization, and inspection of engine events.
- Deterministic replanning and user-authored preparatory proposals; template fallback for optional AI explanations.
- Ranked, evidence-backed findings and concrete proposed changes.
- Before-and-after comparisons using equivalent scenarios; visible adverse tradeoffs.
- A bounded sensitivity suite for travel/loading times, demand timing, and water use, plus a reference allocation policy to expose policy-dependent findings.
- Temporary baseline/variant versions and within-session change records, plus downloadable independent reports with recommendations and proposed revisions; preserve original source documents.
- Production monitoring, job recovery, rate and cost controls, backups, and documented retention and deletion behavior.

### Should have after the production baseline

- Accounts, persistent history, temporary-to-saved conversion, and collaboration only after a separate product decision; none is scheduled or required for the guest-only release.
- Automated Google Search discovery and source retrieval, only after provider access, permitted persistence, and source security are validated.
- AI-generated scenarios, proposals, and checkpoint replanning branches, after measured benefit over deterministic policies.
- In-scenario supply transport, refueling, and shared-crew scheduling, only with reviewed operational data and model validation.
- Bulk record editing and structured import/export for resource updates.
- Interactive sensitivity exploration beyond the required bounded validation suite.
- Configurable scenario libraries and reusable disruption templates.
- English and Filipino explanations, with consistent units and terminology.
- Optional read-only sharing of selected exploratory results, with clear authority and privacy labels.
- Personal notes and follow-up questions attached to findings and proposed revisions.
- A reviewed process for incorporating updated public data without invalidating prior runs.

### Won't have in the initial release

- Live forecast feeds or automatic conversion of weather forecasts into flood extents.
- Real-time dispatch, live resident tracking, public warning delivery, or emergency-command integration.
- Individual resident records, household geolocation, or health-record ingestion as modeled entities.
- Automatic publication, procurement, or adoption of recommendations.
- Full power-grid, telecommunications, traffic-congestion, hydrodynamic, or structural-engineering simulation.
- Full offline operation or comprehensive modeling of non-flood disasters.

## 8. Constraints and design requirements

### Evidence, uncertainty, and model boundaries

- Source confidence and human review status are separate fields. A model confidence score is not a calibrated probability unless validated as such.
- Conflicting or stale values remain visible until resolved. Human assertions retain attribution even when no external evidence is available.
- Findings describe outcomes under specified assumptions. They do not claim real-world failure probabilities from a handpicked scenario suite.
- “Repeated failure” means recurrence across a named suite, with its denominator disclosed. Single severe failures remain visible.
- Scenario-specific displacement must not exceed the modeled population without an explicit external-arrival assumption.
- Numeric findings and comparisons originate from engine outputs. Gemini explanations must reference those outputs and cannot introduce unsupported quantities.
- Documents and web pages are untrusted source material. Embedded instructions cannot change app permissions, tool policies, or simulation configuration.

### Ranking and optimization

The default priority is residents unable to reach safety before their deadline, with explicit attention to vulnerable population groups; then shelter overload, water shortfalls, and resource cost. The app reports aggregate outcomes and vulnerable-group outcomes together. It must expose tradeoffs where a proposed change improves one group while worsening another.

Severity rules and any optimization weights must be documented, versioned, and reviewable. Initial severity thresholds are a pilot-validation decision, not an unexplained LLM judgment. Heuristic solutions must not be presented as mathematically optimal unless the solver establishes that result.

### Reproducibility and workspace versions

Versions, evidence, job records and comparisons are temporary processing state within the active analysis. They support review, deterministic replay and downloads until expiry; they are not persistent user history. Reports already downloaded remain with the user.

Each run pins document and evidence versions, twin version, OSM snapshot, scenario parameters, engine and allocation-policy versions, configuration, and random seed. Accepted Gemini extraction artifacts are saved under the data policy; simulation consumes sealed facts. Replays never generate fresh LLM output. Later AI proposal features must persist their exact response artifacts before evaluation.

Draft, ready-to-run, completed/partial/failed run, and evaluated/untested proposal states describe analysis progress, not official authority. A material change creates a new version and invalidates affected personal-review acknowledgments. The server checks workspace ownership and run prerequisites; saving or exporting an analysis never requires government approval.

### Privacy and security

Use a managed cloud deployment with encrypted transport and storage, tenant-scoped access, private document storage, and audited changes. Model aggregate population data. Uploaded documents may still contain personal information; provide notice, restricted access, retention controls, and a defined deletion process.

Uploading records the public source/publication reference and the user's acknowledgment of document-processing terms, including processing through Gemini. The app does not request municipal authorization to use its public analysis workflow. Google Search queries use the minimum necessary public geographic and factual context; they must not include private document contents or personal information. Production use depends on a reviewed provider configuration and deployment region. Source and map attribution must be retained in the app and exports.

### Reliability and usability

Internet connectivity is required for extraction and simulation. Downloads support later offline reading. Background jobs report progress, support cancellation, and recover without duplicating runs or variants. Jobs survive a refresh or disconnected tab only until session expiry or explicit deletion; the UI explains that time limit before launch. Do not start a job whose configured execution budget exceeds the remaining session lifetime. Deletion/expiry cancels pending work and prevents workers from recreating deleted results. Partial results and failed jobs are explicitly labeled.

Use Asia/Manila as the default scenario display timezone, while storing timestamps unambiguously. Show units and simulation time consistently. Maps have corresponding tabular views; critical status cannot depend on color alone. Essential workflows support keyboard navigation and accessible text labels.

Provider quotas, extraction cost, storage, and scenario-run limits must be bounded per workspace and temporary session with network-level issuance/rate limits and platform-wide spend caps. A new cookie must not provide unlimited paid work. Use graduated abuse challenges where needed and account for shared networks. Later automated search requires its own cost limit before activation. Limits must be visible before a job starts. Plan-size and municipality-scale limits are established through pilot benchmarking rather than hidden truncation.

## 9. Success criteria

The following are proposed release gates and pilot targets, not claims about an implemented product. Engineering verifies the PDF/location workflow and software behavior under declared assumptions (ADR-030). No real participant recruitment, independent/domain reviewer, field measurements or real-event comparisons are release requirements. Source inspection may be performed by the developer/operator. These checks establish input fidelity and deterministic behavior, not predictive field accuracy.

| Area | Acceptance criterion |
| --- | --- |
| Workflow completion | Scripted browser journeys for each supplied PDF and textual location complete temporary upload/review/run/compare/export without signing in, plus gap-only flows and isolation between two independent guest sessions; all required cases pass |
| Time to first result | Record automated end-to-end elapsed time and provider/engine contributions for each declared benchmark; publish measured limits. Do not claim human completion time from automation |
| Extraction quality | For each supplied document separately, at least 90% of adjudicated required facts actually present are correctly extracted with the right units and physical-page references. Record denominators and review all run-critical facts; unresolved critical extraction errors block operational promotion. Include image tables, split headers and graphic marks; one document's score cannot hide the other's failure |
| Input compatibility | Both exact sources in §5.1 independently pass complete-document intake/review/gap export and the supplemented baseline/disruption/paired-change/export journey. Record source-only and supplemented readiness separately; a gap-only export cannot satisfy the run journey |
| Geographic and size scope | The guest-only flow accommodates each full file under published limits at or above §5.1 minima. QC results identify the selected study area and exclusions. Measure extraction separately from engine scale; no silent truncation or whole-city claim from a smaller benchmark |
| Traceability | Every essential run input has recorded provenance or an explicit assumption, and every numeric finding links to engine evidence |
| Review and readiness | Missing essential computational inputs block simulation, not evidence inspection or document-gap export. A runnable baseline requires explicit user acknowledgment of material assumptions; no municipal verification or official approval is requested |
| Engine correctness | Reviewed benchmark cases cover unreachable routes, shelter overflow demand, vehicle outages, loading delays, concurrent demand, and water exhaustion; conservation and resource constraints hold in every case |
| Boundary accounting | Hand-calculated fixtures exactly match initial-occupant totals, empty-event final intervals, horizon-boundary completions/deadlines, unfinished trips, crew-window expiry, and operating-distance exhaustion |
| Input-based model verification | Freeze synthetic arithmetic references and exact tolerances for arrival time, evacuated population and water shortfall; score through the engine with no unresolved critical discrepancy. Pin PDF/OSM inputs and assumptions for demonstrations. Existing visible fixtures are regression references, not blind held-out validation; tolerance changes require a new version and retained/rerun scores |
| Sensitivity and policy dependence | Run nominal/low/high reviewed travel, loading, demand-timing, and water-use assumptions, one factor at a time plus an agreed adverse combination. Compare two deterministic allocation policies; show rank reversals and outcome ranges. Policy-dependent failures cannot be presented as unavoidable resource deficiencies |
| Manual evidence workflow | Public users review missing facts through documents, source references, assertions, or explicit assumptions without automated search or mandatory official contact. Reports distinguish missing documentation from demonstrated resource shortages |
| Source and output separation | Two users uploading the same public PDF receive isolated analyses. Saving, simulating, or exporting a proposed revision leaves the source bytes and the other workspace unchanged. Every output identifies independent analysis, evidence gaps, and tested versus untested proposals |
| Reproducibility | Identical pinned inputs and deterministic policy/configuration reproduce the same event sequence and metrics in the supported runtime, including checkpoint resume |
| Scenario comparison | Every claim of measured improvement requires evaluation against the same baseline suite and seeds, showing gains and regressions. Users may save/export recommendations before evaluation, clearly labeled untested |
| Finding traceability | All top-ten findings per benchmark (or all if fewer) have valid source/assumption and metric links, a modeled-cause explanation, limitations, and tested/untested labels. Check links and quantities against recorded evidence; no subjective usefulness percentage is claimed |
| Performance | Provisional benchmark: a 72-hour simulation with 25 barangays, 30 shelters, 50 vehicles, and 20,000 routable edges completes within 60 seconds at the 95th percentile; a 50-scenario suite completes within 10 minutes at agreed pilot concurrency |
| Job reliability | At least 99% of valid jobs complete or recover automatically during pilot measurement; external-provider failures are reported separately and never appear as successful completion |
| Access control | Requests without the workspace's valid temporary credential cannot read, alter, run, export, or delete it; matching source documents never grant access |
| Temporary lifecycle | Test idle and absolute expiry, polling not extending life, refresh/reconnect, lost credentials, explicit deletion, expiry during jobs/uploads/exports, and rejection of legacy account credentials. Access ends immediately; measured purge/backups meet §2 deadlines; new-session abuse cannot bypass platform spend caps |
| Recovery | A documented operational restore exercise recovers eligible still-active session state before production launch, using the original valid credential and unchanged expiry; tombstones prevent deleted/expired work from returning. This provides no user history or lost-credential recovery |

Production launch requires the engineering, input-fidelity, security and operational gates above. Record model assumptions and keep severity labels provisional and tied to raw metrics. No external domain approval or empirical field validation is required for this exploratory scope; deterministic correctness does not establish real-world predictive validity. Field validation and participant studies are optional future work, not hidden launch dependencies.

## 10. Open questions

These do not block initial product design, but their owners must resolve them before the relevant production milestone.

| Question | Owner / timing |
| --- | --- |
| Which textual locations, resolved OSM study areas and explicit defaults accompany the two PDFs in §5.1? | Product and engineering; before source demonstrations |
| Which temporary upload/run limits and bounded operational recovery targets support public access, and do measured purge/provider policies meet the stated temporary lifecycle? | Product and engineering; before public beta |
| Which PDF/OSM-derived values and explicit hypothetical closure, travel, boarding, crew, distance and assistance defaults are used, and how are unknowns shown? | Product and engineering; before scenario acceptance |
| Which Google Search integration and source-retrieval mechanism meet evidence, quota, cost, and persistence requirements? | Engineering; before enabling later automated research, not a pilot blocker |
| Which Gemini configuration, cloud region, retention periods, deletion process, and document-processing terms support user-consented public-plan uploads? | Product and engineering; before production data ingestion |
| What severity thresholds and treatment of competing vulnerable-group outcomes should be used? | Product and engineering; before findings acceptance; thresholds remain provisional modeling choices |
| What document sizes, geographic network sizes, concurrent users, job quotas, availability, and recovery objectives can the pilot support? | Engineering and product; after representative load benchmarks, before launch |
| How will roads crossing municipal boundaries and hypothetical use of neighboring facilities be reviewed and represented without implying operational permission? | Product and engineering; check against PDF/OSM and label hypothetical use before geography acceptance |
| What are the initial operating budget and responsibility for communicating stale sources and updating reference data? | Product and engineering; before launch |

## 11. Delivery boundary

The initial deliverable is a public self-service application for independent evaluation of publicly available community/municipal disaster plans, with the four specified screens and Must features above. Users review evidence, run deterministic scenarios, and keep recommendations and proposed revisions inside their temporary private workspace until expiry, and download reports for later use. The app neither changes the source plan nor requires or grants official approval. Deferred features are not hidden launch requirements. Expansion into live emergency operations, additional hazards, or live forecast ingestion requires a separate product and validation decision.

## 12. Delivery sequence and stop/go gates

| Milestone | Deliverable and owner | Exit gate |
| --- | --- | --- |
| A — Prove the model and data path first | Engineering uses the two separate PDFs in §5.1 and textual locations resolved to pinned OSM, explicit modeling assumptions, and a prespecified arithmetic verification protocol. Each case demonstrates extraction/review, gap export, baseline, disruption, paired hypothetical change and findings export; QC uses a selected study area | Exact boundary fixtures pass; synthetic arithmetic reference outcomes meet exact tolerances; each document's extraction is adjudicated; source-only and supplemented readiness are recorded separately; source rules remain distinct from assumed policies; sensitivity and routing/dependency decisions are recorded. Unsupported conclusions remain unavailable rather than requiring official access |
| B — Build the public workspace flow | Engineering connects one guest-only temporary-session flow to the four screens, owner-scoped uploads, evidence review, baselines/variants, reports, expiry/deletion, and durable jobs | A scripted browser journey completes the temporary flow without an account. Two independent guest sessions analyze the same document without shared state. Source preservation, reconnect, expiry/deletion, retry/replay and isolation checks pass |
| C — Release public beta | Engineering demonstrates representative load, per-session, network and global spend limits, failure recovery, and restoration; product records region, lifecycle, operating assumptions, and support ownership | All §9 acceptance gates pass; supported document/network/concurrency limits, monthly budget, abuse controls, alert ownership, and rollback procedure are recorded. No municipal affiliation or approval gate is introduced |
| D — Expand from measured need | Product and engineering evaluate deferred features against pilot findings | Each feature has demonstrated user value and its own provider, security, data, and validation gates; automated search and AI replanning cannot bypass them |

Milestone A and completed Phase 1–3 evidence remain unchanged by ADR-031. The next implementation task is the revised Phase 4.1, followed by the guest-only milestone B flow. Use synthetic/redacted fixtures until document-processing consent and provider/data-region settings are ready. Design the demonstration around a public user and private workspace; official approvals and departmental workflows are outside the product scope.

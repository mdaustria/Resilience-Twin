# Resilience Twin — Product Requirements Document

Status: Public-use product plan for product and engineering review  
Date: 12 October 2026  
Target: Public researchers, residents, students, and community groups evaluating publicly available Philippine community/municipal disaster plans

## 1. Problem

Researchers and residents can read a publicly available Municipal Disaster Risk Reduction and Management (MDRRM) plan but may struggle to assess its assumptions, omissions, and operational weaknesses. Roads may become inaccessible, shelters may fill, vehicles may be insufficient, and supplies may run out. A static plan rarely reveals how those failures interact over time.

Resilience Twin turns an existing MDRRM PDF and a text location into a reviewable community model, tests that model under disruptions, and returns ranked weaknesses and proposed fixes. It treats hazard conditions as inputs. In the pilot, Gemini interprets documents and can explain results; deterministic code calculates routes, movement, occupancy, inventories, and outcomes. Users configure scenarios and proposed changes. AI-generated scenarios and replanning are later extensions.

The central question is: **Given this community's roads, shelters, population, vehicles, and supplies, what fails first, who is affected, and which changes improve the result?**

## 2. Users and access

The first release offers **Start temporary analysis** without signing in and **Sign in to save your work** for persistent workspaces. Both serve anyone evaluating a publicly available disaster plan. No government affiliation, invitation, resource-owner confirmation, or official approval is required. A municipality is the subject of an analysis, not the owner of every analysis about it.

| User | Primary needs | Permissions |
| --- | --- | --- |
| Researcher or student | Inspect evidence, reproduce findings, test assumptions, and compare alternatives | Create, edit, run, export, and delete their own analyses |
| Resident or community member | Understand the local plan, identify gaps, and explore possible improvements | The same workspace-owner capabilities, without specialist or government credentials |
| Civic or community-group member | Prepare an evidence-backed assessment and proposed revisions | The same personal-workspace capabilities; multi-user collaboration is deferred |

Each workspace belongs either to a temporary browser session or a signed-in account. Temporary users can upload, review evidence, run simulations within visible limits, compare hypothetical revisions, and download reports without an account. Signed-in workspaces save history across sessions. Shared editing is deferred. Access to an analysis never grants authority over the municipality or source plan. Government employees may use the same public flow without special powers.

### Temporary analysis lifecycle

- A temporary analysis is private, absent from account history, and accessible only through its current browser session. It uses short-lived server storage for uploads and background processing; “temporary” does not mean zero storage.
- Initial product defaults: expire after **2 hours without deliberate user activity**, with an absolute **24-hour maximum** from creation. Background jobs and automatic polling do not extend the session. Show the expiry time and warn before it expires; allow deliberate activity to refresh the idle window only within the absolute maximum.
- Refresh/reconnect works while the session credential remains valid. Closing a tab/browser is not a reliable deletion signal and does not promise immediate erasure. Losing the session credential makes the analysis unrecoverable; there is no cross-device recovery or emailed access link.
- **End and delete analysis** immediately revokes access and requests cancellation/deletion. Expiry does the same automatically, including for running jobs. Active application copies must be purged within 24 hours after termination; backups containing temporary data expire within at most 7 days. Provider retention must be separately verified and disclosed before launch. Deletion does not remove reports already downloaded by the user.
- Signing in does not silently save or attach temporary work. In the first release, users download results before ending the session and start a separate saved workspace if needed; converting a live temporary workspace to a saved one is deferred.
- Temporary sessions have smaller visible upload/run/concurrency limits and abuse controls. Reaching a limit preserves available results until expiry and permits download; it never forces sign-in to retrieve completed results.

All workspaces are private by default. A publicly available source document does not make an uploaded copy, derived model, or result publicly visible in the app. Recommendations and proposed revisions belong only to the current workspace until its owner downloads them. The app does not modify the source document, publish a revised municipal plan, or send recommendations to officials. Every result is labeled an independent analysis, not an official assessment or endorsement.

## 3. Goals

1. Let any researcher or resident create an inspectable analysis from a public disaster-plan PDF and location without specialist modeling skills.
2. Make every important input traceable to a document page, reviewed external source, user correction, or explicit assumption.
3. Identify repeated and severe operational failures rather than reduce resilience to a single pass rate.
4. Demonstrate whether proposed changes improve outcomes across the same reproducible scenarios.
5. Keep recommendations and hypothetical plan revisions under the current user's control, with private versions, evidence, and comparisons that leave the source plan unchanged.
6. Deliver a reliable cloud application that isolates workspaces, expires temporary analyses predictably, preserves opted-in saved work, and makes limitations visible alongside results.

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

## 6. Core flows

### 6.1 Upload and generate the community twin

1. The user selects Start temporary analysis or signs in to create a saved private workspace. Temporary mode displays expiry, processing/deletion terms, and limits before upload, without an account requirement.
2. On Community Twin, the user uploads a publicly available MDRRM PDF, records its public source URL or publication reference and date when known, and enters a location, such as “Guiguinto, Bulacan.” Source metadata is provenance, not a government-approval requirement.
3. The app resolves the location and requests confirmation when boundaries or place names are ambiguous.
4. Gemini extracts barangays, population groups, vulnerable areas, evacuation centers, capacities, vehicles, bridges, routes, water and other supplies, critical facilities, and emergency procedures.
5. The app retrieves an OpenStreetMap road and bridge network for the confirmed area and records a dated source snapshot.
6. Community Twin displays a map, entity counts, extracted records, citations, uncertain matches, and a completeness checklist. Detected counts must reflect actual extraction, not preset examples.
7. Users inspect PDF page references, correct records, confirm locations and road connections, and review possible duplicates and conflicting values.

Unlocated facilities and unresolved road connections remain visible as unresolved. The app must not fabricate coordinates or silently attach a facility to an arbitrary route. Large population groups require reviewed pickup locations or explicit spatial assumptions; a barangay centroid is an assumption, not a verified assembly point.

### 6.2 Fill missing information and confirm the twin

1. Missing essential fields appear in a review checklist. The app may provide a minimal public-context Google Search query for the user to open independently; it does not collect search results.
2. The user supplies public evidence, a source URL, an attributed assertion, or an explicit assumption. Candidate evidence records title, retrieval date, publication date when available, municipality match, and proposed fact. Government or original institutional sources are preferred, but contact with officials is not required.
3. Users inspect the underlying source and attach a permitted excerpt or document page. The pilot records URLs without automatically fetching them. A search snippet alone cannot establish a confirmed operational input. Inaccessible sources remain unverified; user assertions and assumptions retain their distinct labels even after user review.
4. The user reviews candidates, resolves conflicts, or supplies a correction. Search findings never silently overwrite confirmed values.
5. Each material field records its provenance, review status, uncertainty, units, and applicable date. Values distinguish PDF extraction, external evidence, user assertion, and explicit assumption.
6. Exploratory runs may proceed with declared assumptions. If an essential computational input has neither a usable value nor an explicit assumption, the run is blocked with an actionable explanation.
7. The user reviews material assumptions and saves a runnable baseline version. This is personal review, not certification. No independent reviewer or official approval is required. Missing essential numeric values block only simulation; users can still inspect extracted records and export a document-gap assessment clearly labeled “simulation not performed.” An unknown value can be replaced with an explicit plausible assumption for an exploratory run, never silently with zero.

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
- No-sign-in temporary analyses and optional self-service sign-in for saved workspaces; private session/account ownership, visible expiry, end-and-delete, and isolation between users analyzing the same municipality or PDF.
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
- Private baseline/variant versions, change history, and downloadable independent reports with recommendations and proposed revisions; preserve original source documents.
- Production monitoring, job recovery, rate and cost controls, backups, and documented retention and deletion behavior.

### Should have after the production baseline

- Explicit conversion of an active temporary analysis into a saved workspace, and user-invited collaboration, with ownership/transfer rules designed before release.
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

Each run pins document and evidence versions, twin version, OSM snapshot, scenario parameters, engine and allocation-policy versions, configuration, and random seed. Accepted Gemini extraction artifacts are saved under the data policy; simulation consumes sealed facts. Replays never generate fresh LLM output. Later AI proposal features must persist their exact response artifacts before evaluation.

Draft, ready-to-run, completed/partial/failed run, and evaluated/untested proposal states describe analysis progress, not official authority. A material change creates a new version and invalidates affected personal-review acknowledgments. The server checks workspace ownership and run prerequisites; saving or exporting an analysis never requires government approval.

### Privacy and security

Use a managed cloud deployment with encrypted transport and storage, tenant-scoped access, private document storage, and audited changes. Model aggregate population data. Uploaded documents may still contain personal information; provide notice, restricted access, retention controls, and a defined deletion process.

Uploading records the public source/publication reference and the user's acknowledgment of document-processing terms, including processing through Gemini. The app does not request municipal authorization to use its public analysis workflow. Google Search queries use the minimum necessary public geographic and factual context; they must not include private document contents or personal information. Production use depends on a reviewed provider configuration and deployment region. Source and map attribution must be retained in the app and exports.

### Reliability and usability

Internet connectivity is required for extraction and simulation. Downloads support later offline reading. Background jobs report progress, support cancellation, and recover without duplicating runs or variants. Saved-workspace jobs survive tab closure/sign-out and reconnect after sign-in. Temporary jobs survive a refresh or disconnected tab only until session expiry or explicit deletion; the UI explains that time limit before launch. Do not start a job whose configured execution budget exceeds the remaining session lifetime. Deletion/expiry cancels pending work and prevents workers from recreating deleted results. Partial results and failed jobs are explicitly labeled.

Use Asia/Manila as the default scenario display timezone, while storing timestamps unambiguously. Show units and simulation time consistently. Maps have corresponding tabular views; critical status cannot depend on color alone. Essential workflows support keyboard navigation and accessible text labels.

Provider quotas, extraction cost, storage, and scenario-run limits must be bounded per workspace, across an account for saved work, and per temporary session with network-level issuance/rate limits and platform-wide spend caps. A new cookie must not provide unlimited paid work. Use graduated abuse challenges where needed and account for shared networks. Later automated search requires its own cost limit before activation. Limits must be visible before a job starts. Plan-size and municipality-scale limits are established through pilot benchmarking rather than hidden truncation.

## 9. Success criteria

The following are proposed release gates and pilot targets, not claims about an implemented product. Product, engineering, and independent disaster-planning/domain reviewers validate benchmark sizes and thresholds before service-level commitments. Researchers and residents participate in usability testing; a municipal sponsor is not required.

| Area | Acceptance criterion |
| --- | --- |
| Usability | At least 4 of 5 representative researchers/residents complete the temporary upload/review/run/compare/export flow without signing in or receiving developer/official assistance; separately verify the saved-workspace flow |
| Time to first result | With a complete benchmark plan and reviewer available, median active user time from upload to first exploratory findings is at most 60 minutes; unavailable-data waiting time is reported separately |
| Extraction quality | On an adjudicated pilot document set, at least 90% of required facts actually present in the documents are correctly extracted with the right units and page references; missing facts are not invented |
| Traceability | Every essential run input has recorded provenance or an explicit assumption, and every numeric finding links to engine evidence |
| Review and readiness | Missing essential computational inputs block simulation, not evidence inspection or document-gap export. A runnable baseline requires explicit user acknowledgment of material assumptions; no municipal verification or official approval is requested |
| Engine correctness | Reviewed benchmark cases cover unreachable routes, shelter overflow demand, vehicle outages, loading delays, concurrent demand, and water exhaustion; conservation and resource constraints hold in every case |
| Boundary accounting | Hand-calculated fixtures exactly match initial-occupant totals, empty-event final intervals, horizon-boundary completions/deadlines, unfinished trips, crew-window expiry, and operating-distance exhaustion |
| Model validity | Before implementation acceptance, product/engineering and independent domain reviewers record a benchmark protocol with reference cases and numeric tolerances for arrival time, evacuated population, and water shortfall; held-out cases must meet those tolerances, with no unresolved critical discrepancy. Tolerances cannot be relaxed after seeing results without a new version and rerun |
| Sensitivity and policy dependence | Run nominal/low/high reviewed travel, loading, demand-timing, and water-use assumptions, one factor at a time plus an agreed adverse combination. Compare two deterministic allocation policies; show rank reversals and outcome ranges. Policy-dependent failures cannot be presented as unavoidable resource deficiencies |
| Manual evidence workflow | Public users review missing facts through documents, source references, assertions, or explicit assumptions without automated search or mandatory official contact. Reports distinguish missing documentation from demonstrated resource shortages |
| Source and output separation | Two users uploading the same public PDF receive isolated analyses. Saving, simulating, or exporting a proposed revision leaves the source bytes and the other workspace unchanged. Every output identifies independent analysis, evidence gaps, and tested versus untested proposals |
| Reproducibility | Identical pinned inputs and deterministic policy/configuration reproduce the same event sequence and metrics in the supported runtime, including checkpoint resume |
| Scenario comparison | Every claim of measured improvement requires evaluation against the same baseline suite and seeds, showing gains and regressions. Users may save/export recommendations before evaluation, clearly labeled untested |
| Findings usefulness | Pilot reviewers judge at least 80% of the ten highest-ranked findings across agreed benchmark cases to be understandable, evidence-supported, and actionable or explicitly constrained by missing resources |
| Performance | Provisional benchmark: a 72-hour simulation with 25 barangays, 30 shelters, 50 vehicles, and 20,000 routable edges completes within 60 seconds at the 95th percentile; a 50-scenario suite completes within 10 minutes at agreed pilot concurrency |
| Job reliability | At least 99% of valid jobs complete or recover automatically during pilot measurement; external-provider failures are reported separately and never appear as successful completion |
| Access control | Requests without the workspace's valid temporary credential or owning account session cannot read, alter, run, export, or delete it; matching source documents never grant access |
| Temporary lifecycle | Test idle and absolute expiry, polling not extending life, refresh/reconnect, lost credentials, explicit deletion, expiry during jobs/uploads/exports, and sign-in without accidental attachment. Access ends immediately; measured purge/backups meet §2 deadlines; new-session abuse cannot bypass platform spend caps |
| Recovery | A documented backup restoration exercise recovers an owner's baseline, variants, and saved run evidence before production launch; deletion tombstones prevent recovery from republishing deleted work |

Production launch also requires documented evacuation-model assumptions and review of representative simulation results by qualified independent domain reviewers. This validates the product's model; it does not require each user's work to obtain expert or government approval. Numerical correctness alone does not establish real-world validity.

## 10. Open questions

These do not block initial product design, but their owners must resolve them before the relevant production milestone.

| Question | Owner / timing |
| --- | --- |
| Which publicly available plans and representative locations form the benchmark, and who provides independent reference-case review? | Product and domain reviewers; before extraction and engine acceptance |
| Which saved-workspace retention/account recovery and temporary upload/run limits support public access, and do measured purge/provider policies meet the stated temporary lifecycle? | Product and engineering; before public beta |
| Which reviewed hazard maps, closure rules, travel speeds, boarding times, crew windows, fuel-distance budgets, and assistance assumptions are suitable, and how are unknowns represented? | Independent domain reviewers and engineering; before model validation |
| Which Google Search integration and source-retrieval mechanism meet evidence, quota, cost, and persistence requirements? | Engineering; before enabling later automated research, not a pilot blocker |
| Which Gemini configuration, cloud region, retention periods, deletion process, and document-processing terms support user-consented public-plan uploads? | Product and engineering; before production data ingestion |
| What severity thresholds and treatment of competing vulnerable-group outcomes should be used? | Independent domain reviewers and product; before findings acceptance |
| What document sizes, geographic network sizes, concurrent users, job quotas, availability, and recovery objectives can the pilot support? | Engineering and product; after representative load benchmarks, before launch |
| How will roads crossing municipal boundaries and hypothetical use of neighboring facilities be reviewed and represented without implying operational permission? | Domain reviewers and engineering; before geography acceptance |
| What are the initial operating budget and responsibility for communicating stale sources and updating reference data? | Product and engineering; before launch |

## 11. Delivery boundary

The initial deliverable is a public self-service application for independent evaluation of publicly available community/municipal disaster plans, with the four specified screens and Must features above. Users review evidence, run deterministic scenarios, and save recommendations and proposed revisions inside their own private workspace. The app neither changes the source plan nor requires or grants official approval. Deferred features are not hidden launch requirements. Expansion into live emergency operations, additional hazards, or live forecast ingestion requires a separate product and validation decision.

## 12. Delivery sequence and stop/go gates

| Milestone | Deliverable and owner | Exit gate |
| --- | --- | --- |
| A — Prove the model and data path first | Engineering and independent domain reviewers select one public plan, a reviewed road sample, explicit evidence/assumptions, and a prespecified benchmark protocol. Demonstrate extraction/review, a document-gap assessment, one baseline, one disruption, and one paired hypothetical change | Exact boundary fixtures pass; held-out reference outcomes meet tolerances; source-plan rules are distinguished from assumed policies; sensitivity and policy differences are visible; routing/dependency decisions are recorded. Unsupported conclusions remain unavailable rather than requiring official access |
| B — Build the public workspace flow | Engineering connects temporary sessions and optional sign-in to the four screens, owner-scoped uploads, evidence review, baselines/variants, reports, expiry/deletion, and durable jobs | A researcher/resident completes the temporary flow without an account. Temporary and saved users independently analyze the same document without shared state. Source preservation, reconnect, expiry/deletion, retry/replay and isolation checks pass |
| C — Release public beta | Engineering demonstrates representative load, per-account and global spend limits, failure recovery, and restoration; product records region, lifecycle, operating assumptions, and support ownership | All §9 acceptance gates pass; supported document/network/concurrency limits, monthly budget, abuse controls, alert ownership, and rollback procedure are recorded. No municipal affiliation or approval gate is introduced |
| D — Expand from measured need | Product and engineering evaluate deferred features against pilot findings | Each feature has demonstrated user value and its own provider, security, data, and validation gates; automated search and AI replanning cannot bypass them |

The next engineering task is milestone A, not the complete UI or infrastructure rollout. Use synthetic/redacted fixtures until document-processing consent and provider/data-region settings are ready. Design the demonstration around a public user and private workspace; official approvals and departmental workflows are outside the product scope.

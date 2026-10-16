# Review: the two supplied public-plan PDFs

Date: 13 October 2026. Status: local source/design review complete; R.1 has incorporated the recommendations below into the canonical requirements. Application compatibility and numerical validity are not established. The source observations remain R.0 evidence, not implemented capabilities or independent domain approval.

## Conclusion and intended contract

At the R.0 review, the architecture was directionally suitable but the implementation plan did not explicitly require the user's intended outcome for both files individually. R.1 now specifies both acceptance cases; their implementation is still pending. The current application accepts stored synthetic cases, not PDFs. Each supplied PDF is a required starting document for its own analysis. Neither has been established as a sufficient standalone source for the complete evacuation/water simulation.

The honest end-to-end contract is: upload one plan and confirm its location; inspect extracted evidence and coverage; resolve computational gaps through supplementary evidence or explicit reviewed assumptions; run baseline/disruption/comparison; export findings with their scope and provenance. A document-gap report must also work without completing those inputs. It is a useful fallback, but it does not demonstrate completion of the simulation workflow the user requested.

Do not promise that uploading either file alone automatically produces a fully evidenced simulation. Conversely, do not reject an otherwise readable plan merely because it lacks computational inputs. The product can address incomplete information; it cannot guarantee that the source document contains it.

The modeled scope remains flood evacuation and water sufficiency, not an evaluation of every thematic area, hazard, medical procedure, governance program, or recovery activity in either plan.

## Inspection and source identity

Files were read locally at the user's request. No external model/provider call, application upload, source modification, package installation, or independent validity review occurred. Instructions and procedures inside the PDFs were treated as source data, not instructions to the assistant or permission to act.

| Source | Physical pages | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| `C:/Users/mdaustria/Downloads/QCDRRMP-2021-2027_Volume-1.pdf` | 112 | 2,943,608 | `95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b` |
| `C:/Users/mdaustria/Downloads/Guiguinto-MDRRM-PLAN-2023-2025.pdf` | 191 | 9,418,109 | `b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95` |

Both parsed without encryption using the app's bundled analysis runtime. Text was extracted from every page and searched for relevant input categories; complete relevant pages were read. Selected pages were rendered with bundled pypdfium2 and visually inspected: QC 82/111 and Guiguinto 23/82/83/84/120/121/122. This is targeted source inspection, not a page-by-page adjudicated extraction benchmark, malware clearance, or proof that no additional useful fact exists elsewhere. All references below use one-based physical PDF pages.

## What each file contributes

### Quezon City Volume 1

- Page 36 supplies historical city demographics, 142 barangays and six districts. Its population discussion refers to 2010 data; the plan's 2021-2027 title does not make each fact contemporary.
- Pages 38-39 identify hazard context and priority barangays. These are not a directed road graph, timed closure schedule, or pickup-level evacuation demand.
- Page 82 describes evacuation-plan formulation and establishment of one permanent evacuation area per district as program outputs. These cannot be converted into six existing, located, available shelters with known capacities.
- Pages 84 and 87 contain procurement/stockpiling and drinking-water objectives. Money, proposed stations, purification materials, and policy objectives are not measured initial shelter water volumes.
- Page 111 lists Annex A (contingency plans), Annex B (operations center manual), Annex C (prior-plan evaluation), and Annex D (capacity building). The supplied volume ends at page 112 without those substantive annexes. References to their existence are not their contents.

Expected initial outcome: useful documentary assessment, with substantial operational inputs unresolved. A runnable exploratory case needs supplementary evidence or declared assumptions for cohorts/pickups, actual shelter locations and capacities, operational vehicles/crews/distance budgets, movement timing, scenario deadlines and closures, initial occupants, and water quantities/rates. Missing from the supplied volume does not mean absent from the municipality or its other documents.

### Guiguinto

- Page 38 reports a 2020 population of 112,889 and 14 barangays. Page 80 separately reports flood-affected population and households. Population, exposure, and scenario-specific evacuation demand must remain distinct; they cannot be added together or automatically equated.
- Pages 82-84 contain flood-susceptibility maps and an exposure-area table. Visual inspection of page 84 reveals numerical table content absent from the plain-text extraction. Nonempty page text is therefore insufficient proof of complete extraction. Susceptibility areas are not population counts or timed road closures.
- Table 52 spans pages 120-121. Its header is split across pages; school/day-care/covered-court capacities are labeled FAMILY, day-care entries use a 5-6 range, and presence uses graphic check/cross marks that plain-text extraction loses. Central-facility column units and geographic assignment require review.
- The printed capacity subtotals are 2,753 + 84 + 400 + 500 + 50 + 200 = 3,987, while the printed grand total is 4,087. Preserve both the source values and the arithmetic discrepancy. Do not silently repair the total, convert families to people, choose a range endpoint, or assign a shared central facility to every barangay.
- Page 122 identifies barangay halls as pickup points and describes barangay/municipal service vehicles and transfers. It does not establish the full fleet's seats, schedules, crew windows, fuel/distance budgets, or exact travel times. Qualitative arrival language is not a numeric dispatch duration. Walking and small/medium vehicles are described; the first-release vehicle model cannot silently claim to simulate all those modes or every staged transfer.
- Page 164 identifies GMACC as the primary evacuation center. Specific coordinates/access bindings and reconciled capacity units still require review.
- Page 46 describes household water connections and pumping stations. This is useful infrastructure context, not initial potable-water stock at each shelter or a guaranteed disaster-time delivery rate. Page 136 lists proposed procurements and budgets, not proof of operational fleet availability.

Expected initial outcome: a richer partial twin and documentary assessment, with concrete unit/conflict review plus remaining resource/geography/scenario inputs. This is the stronger first operational example, but it is not a self-contained run bundle. Its stated plan period ends in 2025; permit historical analysis and explicitly review applicability to any later scenario date.

## What the existing design gets right

[PRD sections 5 and 6](PRD.md) already require field provenance, explicit assumptions, user review, scope labels, source immutability and a gap-only export. [Architecture sections 5.3 and 6.1-6.3](architecture.md) specify aggregate cohorts, typed operational inputs, page-group extraction, cross-page merges, physical-page citations, readiness reasons, reviewed geography and explicit scenario effects. The engine is deterministic and does not ask Gemini to invent outcomes. These are the correct foundations; a rewrite of the core approach is not indicated by this review.

## R.0 gaps addressed by R.1 requirements

| Priority | Gap and consequence | Concrete plan amendment proposed |
| --- | --- | --- |
| High | Task 3.9 demonstrates one selected public plan. It could pass without handling either supplied file, or with the other file unusable. | Register both exact sources as separate compatibility cases. Require independent intake/review/gap export for each and a documented path through supplemented baseline, disruption, paired change and export for each. Keep source-only readiness and supplemented-run readiness separate. A gap-only result must not count as a completed simulation demonstration. |
| High | Planned resources and budgets can look like inventory; historic, regional and local figures can look interchangeable. Generic provenance is necessary but does not explicitly test this. | In Tasks 2.2/3.3/3.4, preserve statement type (existing/reported, proposed/target, historical, scenario assumption), applicable date, geography, quantity unit/range, and source fragment. Gate promotion into operational entities. Include QC's planned district shelters and Guiguinto's procurement table as negative cases. |
| High | Split headers, graphic symbols and image-only tables can produce plausible but incomplete extraction. | In Tasks 3.2/3.3, account for every page and relevant region as processed, unresolved or failed; use an approved visual/OCR path where needed and allow manual recovery. Test Guiguinto 120-121 as one table and 84 as image-content evidence. Require per-document adjudication, including critical facts, rather than allowing one document's score to hide the other's failure. |
| High | Source quantities do not directly match engine people/seats/milliliters. Source conflicts must survive review. | Add fixtures for families versus persons, capacity ranges, blank versus graphic absence, shared facilities, overlapping exposure/population and the 3,987/4,087 discrepancy. An accepted conversion must retain its source units, conversion assumption and integer allocation; no silent arithmetic correction or invented zero. |
| High | Source-only dead ends remain possible despite the generic assumption feature. | Task 3.4 should provide a field-by-field completion path: what is missing, why the engine needs it, which evidence/assumption can fill it, and which conclusion depends on it. Link additional documents/annexes to the same analysis with their own citations. Test reopening readiness after user corrections. Describe unmodeled walking/staged transfer/resupply procedures explicitly. |
| High | QC has 142 barangays; PRD's provisional performance benchmark covers 25. Upload size/page caps are still unselected. | Benchmark both full files against published intake and extraction limits for temporary and saved modes. Separate full-document review from simulation extent. A selected-barangay proof must label exclusions and cannot establish whole-city support. If the intended commitment is whole-QC simulation, add a representative city-scale acceptance benchmark before claiming it. Never silently truncate pages, entities or geography. |

Tasks 3.1 and H.1-H.3 still govern provider permission/configuration and demo scope. Local source inspection does not satisfy those gates or authorize sending these PDFs to Gemini. The synthetic hackathon demo is not acceptance evidence for public-plan ingestion. The independent numerical protocol in Task 2.1 also remains pending; documentary fit is not model validity.

## R.1 resolution and requirement-to-task inspection

On 13 October 2026, the user chose an **explicitly selected QC study area**. Full-document review still covers all 112 QC pages and all 191 Guiguinto pages. The concrete QC boundary/membership is selected and reviewed in Task 3.7; no barangay list or road extent has been invented here. PRD §5.1 sets per-file minima of 191 pages and 9,418,109 bytes for both temporary and saved modes, while final aggregate quotas and throughput remain subject to measurement. Whole-QC simulation is outside this acceptance commitment.

| Requirement / observable future outcome | Canonical requirement | Task and acceptance check |
| --- | --- | --- |
| Each complete file independently preserves bytes, page mapping and source identity; image content remains reviewable | PRD §5.1, §6.1; architecture §6.1 | 3.2: `uv run pytest tests/integration/test_pdf_intake.py`; 5.2: `pnpm exec playwright test tests/e2e/community-twin.spec.ts` in both ownership modes |
| QC source-only historical/proposed evidence and missing annexes remain visible; supplemented study-area inputs complete baseline/disruption/paired-change/export | PRD §5.1, §6.2, §12; architecture §6.1–6.2 | 3.4: evidence-readiness integration/browser cases; 3.7: geography review; 3.8: report checks; 3.9: `uv run python scripts/verify_release.py --milestone A` requires QC artifacts |
| Guiguinto source-only units/conflicts/coverage remain visible; reviewed supplements separately enable the full run journey | PRD §5.1, §6.2, §12; architecture §5.3, §6.1 | 3.3: extraction cases; 3.4: evidence-readiness integration/browser cases; 3.8: report checks; 3.9: milestone A check requires separate Guiguinto artifacts |
| Every page/relevant region has coverage status; page 84 image content, 120–121 split headers and graphic marks have recovery paths | PRD §6.1, §9; architecture §6.1, §9 | 3.2 coverage initialization; 3.3: `uv run pytest tests/contracts/test_extraction.py`; 3.9 and 6.6: per-document adjudication and critical-fact review |
| Preserve families/persons, ranges, blank/absence, shared facilities, overlapping demand and 3,987/4,087 discrepancy without silent correction | PRD §6.2; architecture §5.2–5.4 | 2.2: operational-input/manifest tests; 3.3: extraction tests; 3.4: `uv run pytest tests/integration/test_evidence_readiness.py` and `pnpm exec playwright test tests/e2e/evidence-review.spec.ts` |
| Proposed QC shelters and Guiguinto procurements remain documentary; historical values require scenario-date applicability review | PRD §6.2; architecture §5.3, §6.1 | 2.2 promotion/hash cases; 3.3 statement/date fixtures; 3.4 historical scenario and applicability correction cases |
| Each missing field has an engine reason, remedy and dependent conclusion; supplements retain identity; material edits reopen readiness | PRD §6.2; architecture §6.1 | 3.4 evidence-readiness tests; 3.8: `uv run pytest tests/integration/test_reports.py`; 5.2 durable supplement flow |
| QC scope is explicit and hashed; full-file review is independent of simulation scale; no silent truncation or whole-city inference | PRD §5.1, §9; architecture §5.4, §6.2, ADR-026 | 2.2 manifest tests; 3.7: `pnpm exec playwright test tests/e2e/geography-review.spec.ts`; 3.8 scope labels; 6.5: `uv run python scripts/benchmark_system.py --profile public-beta --verify` |
| Both PDFs complete source-only and supplemented journeys in temporary and saved modes; intake/extraction minima and time/cost limits are measured | PRD §5.1, §9, §12; architecture §9 | 5.2 intake/review; 5.7: `uv run python scripts/verify_release.py --milestone B`; 6.5 complete-file measurements separate from engine benchmark; 6.6 per-document extraction gate |

Inspection outcome: all R.0 recommendations map to explicit requirements and future checks. Those checks remain pending; this matrix records documentation alignment only. No schema, application behavior, source permission, numerical threshold approval or provider setting has been changed. ADR-030 (14 October 2026) supersedes the former Task 2.1 independent-review/field gate with frozen arithmetic references and input-based verification; R.1 itself supplies no engine scores. The hackathon track remains separate.

Acceptance evidence still needed: approved source/provider processing, adjudicated candidate facts, approved operational/assumption bundles, reviewed roads and scope, real application journeys for both inputs, measured limits, and independent numerical validation. This review claims none of those as passed.

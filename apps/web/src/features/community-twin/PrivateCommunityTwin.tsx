import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useTemporarySession } from '../../components/session';
import {
  acknowledgeReview, citedPdf, confirmPilotLocation, initializeReview, readBaseline,
  readCoverage, readPilotLocation, readReview, ReviewRequestError, saveReview,
  sealBaseline, sealReview,
  type ArtifactCoverage, type BaselineRecord, type PilotCase, type PrivatePilotLocation,
  type ReviewClaim, type ReviewRecord,
} from '../../lib/durableReview';
import { uploadPdf, type ArtifactStatus } from '../../lib/privateDocuments';

export function PrivateCommunityTwin() {
  const session = useTemporarySession();
  const [record, setRecord] = useState<ReviewRecord | null>(null);
  const [coverage, setCoverage] = useState<ArtifactCoverage | null>(null);
  const [pilotLocation, setPilotLocation] = useState<PrivatePilotLocation | null>(null);
  const [baseline, setBaseline] = useState<BaselineRecord | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [reference, setReference] = useState('');
  const [location, setLocation] = useState('');
  const [scenarioDate, setScenarioDate] = useState(new Date().toISOString().slice(0, 10));
  const [pendingArtifact, setPendingArtifact] = useState<ArtifactStatus | null>(null);
  const [stage, setStage] = useState('Checking private review…');
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [claimField, setClaimField] = useState('');
  const [claimValue, setClaimValue] = useState('');
  const [assumptionField, setAssumptionField] = useState('');
  const [assumptionValue, setAssumptionValue] = useState('');
  const [unit, setUnit] = useState('');
  const [page, setPage] = useState('1');
  const [fragment, setFragment] = useState('');
  const [rationale, setRationale] = useState('');
  const [limitations, setLimitations] = useState('');
  const [selectedClaim, setSelectedClaim] = useState('');
  const [resolution, setResolution] = useState('');
  const [correctionValue, setCorrectionValue] = useState('');
  const [correctionStatement, setCorrectionStatement] = useState<'reported_existing' | 'proposed_target' | 'historical'>('reported_existing');
  const [correctionReason, setCorrectionReason] = useState('');
  const [citationUrl, setCitationUrl] = useState<string | null>(null);
  const [citationPage, setCitationPage] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const latest = await readReview(session);
      setRecord(latest);
      if (latest?.content.draft.sources[0]) {
        const source = latest.content.draft.sources[0];
        setCoverage(await readCoverage(session, source.source_id));
        const pilot = source.sha256 === '95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b'
          ? 'qc' : source.sha256 === 'b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95'
            ? 'guiguinto' : null;
        setPilotLocation(pilot ? await readPilotLocation(session, pilot) : null);
        setBaseline(await readBaseline(session));
      } else {
        setCoverage(null); setPilotLocation(null); setBaseline(null);
      }
      setStage(latest ? 'Private review reconnected.' : 'No private PDF has been reviewed in this session.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load the private review.');
    }
  }, [session]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => () => { if (citationUrl) URL.revokeObjectURL(citationUrl); }, [citationUrl]);

  const fail = async (reason: unknown) => {
    if (reason instanceof ReviewRequestError && reason.status === 409) {
      await refresh();
      setError('This review changed in another tab. The latest revision is shown; inspect it before retrying.');
    } else {
      setError(reason instanceof Error ? reason.message : 'The request failed.');
    }
  };

  async function beginUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) return;
    if (Date.parse(session.expires_at) - Date.now() < 60_000) {
      setError('Less than one minute remains. Renew the session before uploading.');
      return;
    }
    setBusy(true);
    setError(null);
    setProgress(0);
    try {
      setStage('Hashing and transferring the complete PDF…');
      const artifact = await uploadPdf(selectedFile, session, setProgress);
      setPendingArtifact(artifact);
      setStage('PDF stored and checked. Creating the source-only review…');
      await initialize(artifact);
    } catch (reason) { await fail(reason); }
    finally { setBusy(false); }
  }

  async function initialize(artifact: ArtifactStatus) {
    const saved = await initializeReview(session, {
      artifact_id: artifact.artifact_id, title, publication_reference: reference,
      textual_location: location, scenario_date: scenarioDate,
    });
    setRecord(saved);
    setCoverage(await readCoverage(session, artifact.artifact_id));
    const pilot = artifact.sha256 === '95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b'
      ? 'qc' : artifact.sha256 === 'b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95'
        ? 'guiguinto' : null;
    setPilotLocation(pilot ? await readPilotLocation(session, pilot) : null);
    setPendingArtifact(null);
    setStage('Complete PDF received; source-only review is ready.');
  }

  async function mutate(next: ReviewRecord['content']['draft']) {
    if (!record) return;
    setBusy(true);
    setError(null);
    try { setRecord(await saveReview(session, record, next)); }
    catch (reason) { await fail(reason); }
    finally { setBusy(false); }
  }

  function addClaim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!record) return;
    const source = record.content.draft.sources[0];
    const physicalPage = Number(page);
    if (!source || !Number.isInteger(physicalPage) || physicalPage < 1 ||
        physicalPage > source.physical_page_count) {
      setError('The citation page must be within the complete uploaded PDF.');
      return;
    }
    const claim: ReviewClaim = {
      claim_id: crypto.randomUUID(), field: claimField.trim(), value: claimValue.trim(), unit: unit.trim(),
      kind: 'document', source_id: source.source_id, physical_page: physicalPage,
      fragment: fragment.trim(), statement_type: 'reported_existing',
      scope_id: record.content.draft.scope_id, status: 'candidate',
    };
    void mutate({ ...record.content.draft, claims: [...record.content.draft.claims, claim] });
  }

  function resolveClaim(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!record) return;
    const decision = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const status = decision?.value === 'contested' ? 'contested' as const : 'accepted' as const;
    const claims = record.content.draft.claims.map((claim) => claim.claim_id === selectedClaim
      ? { ...claim, status, resolution_note: resolution.trim() }
      : claim);
    void mutate({ ...record.content.draft, claims });
  }

  function addAssumption(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!record) return;
    const requirement = record.content.draft.required_fields.find((item) => item.field === assumptionField);
    if (!requirement || !/^\d+$/.test(assumptionValue)) {
      setError('Select a missing field and enter a nonnegative integer in its displayed unit.');
      return;
    }
    const draft = record.content.draft;
    void mutate({ ...draft, assumptions: [...draft.assumptions, {
      assumption_id: crypto.randomUUID(), field: requirement.field,
      value: assumptionValue, unit: requirement.unit, rationale: rationale.trim(), limitations: limitations.trim(),
      scope_id: draft.scope_id, applicable_from: draft.scenario_date,
      applicable_through: draft.scenario_date, usable: true,
    }] });
  }

  function addCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!record) return;
    const prior = record.content.draft.claims.find((claim) => claim.claim_id === selectedClaim);
    if (!prior || !correctionValue.trim() || !correctionReason.trim()) {
      setError('Select a source claim, corrected value, and explanation.');
      return;
    }
    const draft = record.content.draft;
    const correction: ReviewClaim = {
      claim_id: crypto.randomUUID(), field: prior.field, value: correctionValue.trim(),
      unit: prior.unit, kind: 'correction', source_id: null, physical_page: null,
      fragment: correctionReason.trim(), statement_type: correctionStatement,
      scope_id: draft.scope_id, status: 'accepted', resolution_note: correctionReason.trim(),
    };
    void mutate({ ...draft, claims: [...draft.claims, correction] });
  }

  async function inspect(claim: ReviewClaim) {
    if (!claim.source_id || !claim.physical_page) return;
    setError(null);
    try {
      const blob = await citedPdf(session, claim.source_id);
      if (citationUrl) URL.revokeObjectURL(citationUrl);
      setCitationUrl(URL.createObjectURL(blob));
      setCitationPage(claim.physical_page);
    } catch (reason) { await fail(reason); }
  }

  async function seal() {
    if (!record) return;
    setBusy(true);
    setError(null);
    try { setRecord(await sealReview(session, record)); }
    catch (reason) { await fail(reason); }
    finally { setBusy(false); }
  }

  async function acknowledge() {
    if (!record) return;
    setBusy(true);
    setError(null);
    try { setRecord(await acknowledgeReview(session, record)); }
    catch (reason) { await fail(reason); }
    finally { setBusy(false); }
  }

  async function confirmLocation() {
    if (!record || !pilotLocation) return;
    const pilot = pilotLocation.snapshot.case as PilotCase;
    setBusy(true); setError(null);
    try {
      const confirmed = await confirmPilotLocation(session, record, pilot,
        pilotLocation.snapshot.scope_digest);
      setRecord(confirmed.review);
      setPilotLocation(confirmed.location);
    } catch (reason) { await fail(reason); }
    finally { setBusy(false); }
  }

  async function createBaseline() {
    if (!record || !pilotLocation) return;
    setBusy(true); setError(null);
    try {
      setBaseline(await sealBaseline(session, record, pilotLocation));
      window.dispatchEvent(new Event('private-baseline-sealed'));
    }
    catch (reason) { await fail(reason); }
    finally { setBusy(false); }
  }

  const draft = record?.content.draft;
  const readiness = record?.content.readiness;
  return <section className="panel" aria-labelledby="private-community-heading">
    <p className="eyebrow">Community Twin · private workspace</p>
    <h2 id="private-community-heading">PDF and evidence review</h2>
    <p role="status">{stage}</p>
    {error && <p role="alert">{error}</p>}
    {!record && <form onSubmit={(event) => { void beginUpload(event); }}>
      <p>Upload one complete public plan PDF. Current per-file maximum: 10,000,000 bytes and 200 physical pages. All pages begin unresolved until extraction or manual review. The source PDF remains immutable.</p>
      <label htmlFor="private-pdf">Public plan PDF</label>
      <input id="private-pdf" type="file" accept="application/pdf,.pdf" required
        onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} />
      <label htmlFor="source-title">Source title</label>
      <input id="source-title" required value={title} onChange={(event) => setTitle(event.target.value)} />
      <label htmlFor="source-reference">Publication reference or public URL</label>
      <input id="source-reference" required value={reference} onChange={(event) => setReference(event.target.value)} />
      <label htmlFor="textual-location">Textual study location</label>
      <input id="textual-location" required value={location} onChange={(event) => setLocation(event.target.value)} />
      <label htmlFor="scenario-date">Scenario date</label>
      <input id="scenario-date" type="date" required value={scenarioDate}
        onChange={(event) => setScenarioDate(event.target.value)} />
      <div><button type="submit" disabled={busy || !selectedFile}>Upload and begin review</button></div>
      {busy && <progress aria-label="PDF transfer progress" value={progress} max={1} />}
      {pendingArtifact && <button type="button" disabled={busy} onClick={() => {
        setBusy(true); void initialize(pendingArtifact).catch((reason: unknown) => { void fail(reason); })
          .finally(() => setBusy(false));
      }}>Retry source review creation</button>}
    </form>}
    {record && draft && readiness && <>
      <p>Review revision {record.revision}. {record.sealed ? 'Sealed snapshot.' : 'Editable draft.'} Source hash: {draft.sources[0]?.sha256}.</p>
      <p>Study location: {draft.scope_id}. Location and scenario review: {draft.scenario_reviewed ? 'confirmed' : 'pending'}.</p>
      {coverage && <>
        <p>Complete PDF intake: {coverage.physical_page_count} of {coverage.physical_page_count} physical pages mapped; {coverage.pages.filter((item) => item.coverage_status === 'unresolved').length} pages still need extraction or manual coverage review.</p>
        <p>Coverage basis: {coverage.review_basis}.</p>
        <details><summary>Page coverage list</summary><ol>{coverage.pages.map((item) => <li key={item.physical_page}>
          Page {item.physical_page}: {item.coverage_status} ({item.extraction_method})
        </li>)}</ol></details>
      </>}
      <h3>Source-only documentation gaps</h3>
      <ul>{readiness.source_only_gaps.map((gap) => <li key={gap.field}>
        {gap.field} ({draft.required_fields.find((item) => item.field === gap.field)?.unit}): {gap.reason}. Remedy: {gap.remedy}. Dependent conclusions: {gap.dependent_conclusions.join(', ')}.
      </li>)}</ul>
      <h3>Current simulation blockers</h3>
      <p>Document review remains available. Simulation {readiness.ready_to_run ? 'is ready' : 'is blocked'}; unknown inputs are never treated as zero.</p>
      <ul>{readiness.gaps.map((gap) => <li key={gap.field}>{gap.field}: {gap.engine_reason}. {gap.remedy}</li>)}</ul>
      <h3>Declared modeling assumptions</h3>
      <ul>{draft.assumptions.map((item) => <li key={item.assumption_id}>
        {item.field}: {item.value} {item.unit}. Reason: {item.rationale}. Limitations: {item.limitations}.
      </li>)}</ul>
      {!draft.scenario_reviewed && <p>Review the pinned study area and scenario before running or sealing a baseline.</p>}
      {pilotLocation && <>
        <h3>Study area and road access</h3>
        <p>{pilotLocation.snapshot.area.label}. This is a selected modeling cell, not the whole city or municipality.</p>
        <p>Pinned OSM source: {pilotLocation.snapshot.source_sha256}. Compiled graph: {pilotLocation.snapshot.graph_sha256}. Route status: {pilotLocation.snapshot.route_status}.</p>
        <table><caption>Included scope and access review</caption><thead><tr><th scope="col">Place or cohort</th><th scope="col">Included</th><th scope="col">Review basis</th></tr></thead>
          <tbody>{pilotLocation.snapshot.area.members.map((member) => <tr key={member.id}>
            <th scope="row">{member.label}</th><td>{member.included ? 'Yes' : 'No'}</td><td>{member.reason}</td>
          </tr>)}{pilotLocation.snapshot.area.connectors.map((connector) => <tr key={connector.id}>
            <th scope="row">{connector.point_id}</th><td>{connector.accessible ? 'Access assumed' : 'Unresolved'}</td>
            <td>OSM node {connector.road_node_id ?? 'unresolved'}; {connector.distance_m ?? 'unknown'} m; {connector.source}</td>
          </tr>)}</tbody></table>
        <ul>{pilotLocation.snapshot.area.cross_boundary_assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
        {pilotLocation.snapshot.blockers.length > 0 && <p role="alert">Geography blockers: {pilotLocation.snapshot.blockers.join('; ')}</p>}
        {!draft.scenario_reviewed && <button type="button" disabled={busy || pilotLocation.snapshot.blockers.length > 0}
          onClick={() => { void confirmLocation(); }}>Confirm selected study area and connectors</button>}
        {draft.scenario_reviewed && <p>Reviewed location scope: {draft.scope_id}.</p>}
      </>}
      <h3>Page-cited evidence</h3>
      <ul>{draft.claims.map((claim) => <li key={claim.claim_id}>
        <strong>{claim.field}</strong>: {claim.value} {claim.unit} ({claim.kind}, {claim.statement_type}, {claim.status}).
        {claim.physical_page && <> Source page {claim.physical_page}: “{claim.fragment}”.
          <button type="button" className="text-button" onClick={() => { void inspect(claim); }}>Inspect cited page {claim.physical_page}</button></>}
      </li>)}</ul>
      {citationUrl && citationPage && <div className="citation-preview">
        <button type="button" onClick={() => { URL.revokeObjectURL(citationUrl); setCitationUrl(null); setCitationPage(null); }}>Close citation</button>
        <iframe title={`Source PDF page ${citationPage}`} src={`${citationUrl}#page=${citationPage}`} />
      </div>}
      {!record.sealed && <>
        <h3>Add page-cited evidence</h3>
        <form onSubmit={addClaim} className="review-form">
          <label>Field<input required value={claimField} onChange={(event) => setClaimField(event.target.value)} /></label>
          <label>Value as printed<input required value={claimValue} onChange={(event) => setClaimValue(event.target.value)} /></label>
          <label>Source unit<input required value={unit} onChange={(event) => setUnit(event.target.value)} /></label>
          <label>Physical page<input required type="number" min="1" max={draft.sources[0]?.physical_page_count} value={page} onChange={(event) => setPage(event.target.value)} /></label>
          <label>Exact source excerpt<input required value={fragment} onChange={(event) => setFragment(event.target.value)} /></label>
          <button type="submit" disabled={busy}>Add candidate with citation</button>
        </form>
        <h3>Record a source decision</h3>
        <form onSubmit={resolveClaim} className="review-form">
          <label>Candidate<select required value={selectedClaim} onChange={(event) => setSelectedClaim(event.target.value)}>
            <option value="">Select a claim</option>{draft.claims.filter((claim) => claim.status !== 'accepted').map((claim) =>
              <option key={claim.claim_id} value={claim.claim_id}>{claim.field}, page {claim.physical_page}</option>)}
          </select></label>
          <label>Review decision and limitations<input required value={resolution} onChange={(event) => setResolution(event.target.value)} /></label>
          <button type="submit" value="accepted" disabled={busy || !selectedClaim}>Accept reviewed claim</button>
          <button type="submit" value="contested" disabled={busy || !selectedClaim}>Mark claim contested</button>
        </form>
        <h3>Record a labeled correction</h3>
        <form onSubmit={addCorrection} className="review-form">
          <p>The correction is your interpretation of the selected source claim. It does not change the immutable PDF or claim a new page citation.</p>
          <label>Corrected value<input required value={correctionValue} onChange={(event) => setCorrectionValue(event.target.value)} /></label>
          <label>Corrected statement type<select value={correctionStatement}
            onChange={(event) => setCorrectionStatement(event.target.value as typeof correctionStatement)}>
            <option value="reported_existing">Reported existing</option>
            <option value="proposed_target">Proposed target</option>
            <option value="historical">Historical</option>
          </select></label>
          <label>Correction explanation<input required value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} /></label>
          <button type="submit" disabled={busy || !selectedClaim}>Record correction</button>
        </form>
        <h3>Declare a modeling assumption</h3>
        <form onSubmit={addAssumption} className="review-form">
          <label>Missing input<select required value={assumptionField} onChange={(event) => setAssumptionField(event.target.value)}>
            <option value="">Select a field</option>{draft.required_fields.map((item) =>
              <option key={item.field} value={item.field}>{item.field} ({item.unit})</option>)}
          </select></label>
          <label>Nonnegative integer value<input required value={assumptionValue} onChange={(event) => setAssumptionValue(event.target.value)} /></label>
          <label>Reason<input required value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
          <label>Limitations<input required value={limitations} onChange={(event) => setLimitations(event.target.value)} /></label>
          <button type="submit" disabled={busy}>Declare explicit assumption</button>
        </form>
        <button type="button" disabled={busy} onClick={() => { void seal(); }}>Seal evidence review</button>
      </>}
      {record.sealed && !readiness.ready_to_run && <button type="button" disabled={busy || !readiness.computable || !draft.scenario_reviewed}
        onClick={() => { void acknowledge(); }}>Acknowledge assumptions after location review</button>}
      {record.sealed && readiness.ready_to_run && pilotLocation && !baseline && <>
        <p>The baseline will pin this reviewed graph, the declared water amount at the facility, one illustrative vehicle at the reviewed pickup node, and the exact source/review hashes.</p>
        <button type="button" disabled={busy} onClick={() => { void createBaseline(); }}>Seal immutable baseline</button>
      </>}
      {baseline && <p>Immutable baseline sealed. Baseline hash: {baseline.content.baseline_hash}. Graph hash: {baseline.content.graph_hash}.</p>}
      <p><button type="button" className="secondary" disabled={busy} onClick={() => { void refresh(); }}>Reconnect to latest review</button></p>
    </>}
  </section>;
}

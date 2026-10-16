import { useEffect, useState } from 'react';
import type { paths } from '../../../../../packages/client-generated/skeleton';

type Snapshot = paths['/api/v1/local/review']['get']['responses'][200]['content']['application/json'];
type AssumptionBody = paths['/api/v1/local/review/assumption']['post']['requestBody']['content']['application/json'];
type BundleBody = paths['/api/v1/local/review/assumptions']['post']['requestBody']['content']['application/json'];
type RevisionBody = paths['/api/v1/local/review/seal']['post']['requestBody']['content']['application/json'];

type ReviewCase = 'synthetic' | 'qc' | 'guiguinto';

const ownerHeaders = (reviewCase: ReviewCase) => ({
  'X-Fixture-Owner': 'fixture-a',
  'X-Fixture-Case': reviewCase,
});

export function EvidenceReview() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [reviewCase, setReviewCase] = useState<ReviewCase>('synthetic');
  const [defaultValues, setDefaultValues] = useState<Record<string, string>>({});
  const [water, setWater] = useState('5000');
  const [rationale, setRationale] = useState('Exploratory opening stock for the training case');
  const [limitations, setLimitations] = useState('Not a documented current inventory');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function reload() {
      setSnapshot(null);
      void fetch('/api/v1/local/review', { headers: ownerHeaders(reviewCase) })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Review unavailable (${response.status})`);
        return response.json() as Promise<Snapshot>;
      })
      .then((result) => {
        setSnapshot(result);
        setDefaultValues(Object.fromEntries(result.default_assumptions.map((item) => [item.field, item.value])));
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Review unavailable'));
    }
    reload();
    window.addEventListener('geography-reviewed', reload);
    return () => window.removeEventListener('geography-reviewed', reload);
  }, [reviewCase]);

  async function post(path: string, body: AssumptionBody | BundleBody | RevisionBody) {
    setError(null);
    try {
      const response = await fetch(`/api/v1/local/review/${path}`, {
        method: 'POST',
        headers: { ...ownerHeaders(reviewCase), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`Review update failed (${response.status})`);
      setSnapshot(await response.json() as Snapshot);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Review update failed');
    }
  }

  function declareAssumption() {
    if (!snapshot) return;
    const draft = snapshot.draft;
    const body: AssumptionBody = {
      expected_revision: draft.revision,
      assumption: {
        assumption_id: `water-${draft.revision + 1}`,
        field: 'opening_water_ml', value: water, unit: 'ML', rationale, limitations,
        scope_id: draft.scope_id, applicable_from: draft.scenario_date,
        applicable_through: draft.scenario_date, usable: true,
      },
    };
    void post('assumption', body);
  }

  function applyDefaults() {
    if (!snapshot) return;
    const body: BundleBody = {
      expected_revision: snapshot.draft.revision,
      defaults_version: snapshot.defaults_version,
      assumptions: snapshot.default_assumptions.map((item) => ({
        ...item,
        value: defaultValues[item.field] ?? item.value,
      })),
    };
    void post('assumptions', body);
  }

  return <section aria-labelledby="evidence-heading" className="panel">
    <p className="eyebrow">Local evidence review</p>
    <h2 id="evidence-heading">Evidence and run readiness</h2>
    <label htmlFor="review-case">Review case</label>
    <select id="review-case" value={reviewCase} onChange={(event) => setReviewCase(event.target.value as ReviewCase)}>
      <option value="synthetic">Synthetic training case</option>
      <option value="qc">Quezon City Volume 1</option>
      <option value="guiguinto">Guiguinto plan</option>
    </select>
    {error && <p role="alert">{error}</p>}
    {!snapshot && !error && <p role="status">Loading evidence…</p>}
    {snapshot && <>
      <p>Source: {snapshot.draft.sources.map((source) => source.title).join(', ')}.</p>
      <p>Reviewed scope: {snapshot.draft.scope_id}. Scenario location review: {snapshot.draft.scenario_reviewed ? 'complete' : 'pending'}.</p>
      <p>Document review: {snapshot.readiness.document_review_available ? 'available' : 'unavailable'}</p>
      <p>Run readiness: {snapshot.readiness.ready_to_run ? 'ready to run'
        : !snapshot.readiness.computable ? 'missing inputs'
          : !snapshot.draft.scenario_reviewed ? 'needs location and scenario review' : 'needs acknowledgment'}</p>
      <h3>Source-only gaps</h3>
      <ul>{snapshot.readiness.source_only_gaps.map((gap) => <li key={gap.field}>
        <strong>{gap.field}</strong>: {gap.reason}. {gap.engine_reason}. Remedy: {gap.remedy}.
        Dependent conclusions: {gap.dependent_conclusions.join(', ')}.
      </li>)}</ul>
      <h3>Evidence</h3>
      <ul>{snapshot.draft.claims.map((claim) => <li key={claim.claim_id}>
        {claim.field}: {claim.value} {claim.unit} ({claim.statement_type}, {claim.status}).
        {claim.source_id && <> Source {claim.source_id}, physical page {claim.physical_page}: “{claim.fragment}”.</>}
      </li>)}</ul>
      <h3>Documentation gaps</h3>
      <ul>{snapshot.readiness.documentation_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
      <fieldset>
        <legend>Illustrative defaults ({snapshot.defaults_version})</legend>
        <p>Review every value together. These are assumptions, not facts from the plan.</p>
        {snapshot.default_assumptions.map((item) => <div key={item.field}>
          <label htmlFor={`default-${item.field}`}>{item.field} ({item.unit})</label>
          <input id={`default-${item.field}`} value={defaultValues[item.field] ?? item.value}
            onChange={(event) => setDefaultValues((current) => ({ ...current, [item.field]: event.target.value }))} />
          <small>{item.limitations}</small>
        </div>)}
        <button type="button" onClick={applyDefaults}>Apply reviewed defaults</button>
      </fieldset>
      <div>
        <label htmlFor="water-assumption">Assumed opening water (mL)</label>
        <input id="water-assumption" value={water} onChange={(event) => setWater(event.target.value)} />
        <label htmlFor="assumption-rationale">Rationale</label>
        <input id="assumption-rationale" value={rationale} onChange={(event) => setRationale(event.target.value)} />
        <label htmlFor="assumption-limitations">Limitations</label>
        <input id="assumption-limitations" value={limitations} onChange={(event) => setLimitations(event.target.value)} />
        <button type="button" onClick={declareAssumption}>Declare usable assumption</button>
        <button type="button" onClick={() => void post('seal', { expected_revision: snapshot.draft.revision })} disabled={!snapshot.readiness.computable}>Seal review</button>
        <button type="button" onClick={() => void post('acknowledge', { expected_revision: snapshot.draft.revision })} disabled={!snapshot.draft.sealed_hash}>Acknowledge assumptions</button>
      </div>
      <p>Revision {snapshot.draft.revision}. This is a personal exploratory review, not official approval.</p>
    </>}
  </section>;
}

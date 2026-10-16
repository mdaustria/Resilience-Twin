import { useCallback, useEffect, useState, type FormEvent } from 'react';
import type { components } from '../../../../../packages/client-generated/private-commands';
import { useTemporarySession } from '../../components/session';
import { readReview, type ReviewRecord } from '../../lib/durableReview';

type Comparison = components['schemas']['ComparisonView'];
type Baseline = { content: { baseline_hash: string; resources: {
  water_stores: [string, number][]; vehicle_starts: [string, string][]; shelter_ids: string[];
} } };
type Proposal = { sealed: boolean; content_hash: string; content: {
  operations: Record<string, unknown>[]; variant: {
    variant_hash: string; water_stores: [string, number][];
    declared_added_water_ml: number;
  };
} };

async function result<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const issue = await response.json() as { code?: string; title?: string };
    throw new Error(`${issue.code ?? 'findings_error'}: ${issue.title ?? 'Request failed'}`);
  }
  return response.json() as Promise<T>;
}

function ids(value: string): string[] { return value.split(',').map((item) => item.trim()).filter(Boolean); }

export function FindingsView() {
  const session = useTemporarySession();
  const base = `/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}`;
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [review, setReview] = useState<ReviewRecord | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [operation, setOperation] = useState<'add_water' | 'redistribute_water'>('add_water');
  const [store, setStore] = useState('');
  const [destination, setDestination] = useState('');
  const [amount, setAmount] = useState('500000');
  const [source, setSource] = useState('');
  const [baselineJobs, setBaselineJobs] = useState('');
  const [variantJobs, setVariantJobs] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState('Checking the sealed baseline…');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`${base}/baselines/main`, { credentials: 'same-origin', cache: 'no-store' });
      if (response.status === 404) { setBaseline(null); setStatus('Seal a Community Twin baseline first.'); return; }
      const current = await result<Baseline>(response);
      setBaseline(current);
      setStore((prior) => prior || current.content.resources.water_stores[0]?.[0] || '');
      setDestination((prior) => prior || current.content.resources.water_stores[1]?.[0] || '');
      setReview(await readReview(session));
      const saved = await fetch(`${base}/proposals/main`, { credentials: 'same-origin', cache: 'no-store' });
      setProposal(saved.status === 404 ? null : await result<Proposal>(saved));
      setStatus('Sealed baseline and proposal state loaded.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not load findings.'); }
  }, [base, session]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const update = () => { void refresh(); };
    window.addEventListener('private-baseline-sealed', update);
    window.addEventListener('focus', update);
    return () => { window.removeEventListener('private-baseline-sealed', update); window.removeEventListener('focus', update); };
  }, [refresh]);

  async function saveProposal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!baseline) return;
    setBusy(true); setError(null);
    try {
      const quantity = Number(amount);
      if (!Number.isSafeInteger(quantity) || quantity <= 0) throw new Error('Use a positive whole number of milliliters.');
      const edit = operation === 'add_water'
        ? { type: 'add_water', store_id: store, amount_ml: quantity, source_reference: source.trim() }
        : { type: 'redistribute_water', from_store_id: store, to_store_id: destination, amount_ml: quantity };
      const response = await fetch(`${base}/proposals/main`, { method: 'PUT',
        credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token,
          'If-Match': '0', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ baseline_id: 'main', baseline_hash: baseline.content.baseline_hash,
          operations: [edit] }),
      });
      setProposal(await result<Proposal>(response));
      setComparison(null);
      setStatus('Hypothetical child variant sealed. It remains untested until paired runs complete.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Proposal rejected.'); }
    finally { setBusy(false); }
  }

  async function evaluate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!proposal) return;
    setBusy(true); setError(null);
    try {
      const response = await fetch(`${base}/comparisons/main/evaluate`, { method: 'POST',
        credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseline_job_ids: ids(baselineJobs), variant_job_ids: ids(variantJobs) }),
      });
      setComparison(await result<Comparison>(response));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Paired evaluation unavailable.'); }
    finally { setBusy(false); }
  }

  const waterBefore = new Map(baseline?.content.resources.water_stores ?? []);
  const waterAfter = proposal?.content.variant.water_stores ?? [];
  return <section className="panel" aria-labelledby="findings-heading">
    <p className="eyebrow">Resilience Findings · independent analysis</p>
    <h2 id="findings-heading">Findings and hypothetical changes</h2>
    <p role="status">{status}</p>
    {error && <p role="alert">{error}</p>}
    {review && <><h3>Documentary gaps</h3><p>Missing document facts are separate from simulated failures.</p>
      <ul>{review.content.readiness.source_only_gaps.map((gap) => <li key={gap.field}>{gap.field}: {gap.reason}. {gap.remedy}</li>)}</ul></>}
    {baseline && <>
      {!proposal ? <form onSubmit={(event) => { void saveProposal(event); }} className="review-form">
        <h3>Concrete proposal edit</h3>
        <p>These edits create a hypothetical child variant. They do not change the source document or implement a field action.</p>
        <label>Edit type<select value={operation} onChange={(event) => setOperation(event.target.value as typeof operation)}>
          <option value="add_water">Declare additional opening water</option>
          <option value="redistribute_water">Redistribute existing opening water</option>
        </select></label>
        <label>{operation === 'add_water' ? 'Receiving water store' : 'From water store'}
          <select value={store} onChange={(event) => setStore(event.target.value)}>
            {baseline.content.resources.water_stores.map(([id]) => <option key={id} value={id}>{id}</option>)}
          </select></label>
        {operation === 'redistribute_water' && <label>To water store<select value={destination} onChange={(event) => setDestination(event.target.value)}>
          {baseline.content.resources.water_stores.map(([id]) => <option key={id} value={id}>{id}</option>)}
        </select></label>}
        <label>Water quantity (mL)<input required value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
        {operation === 'add_water' && <label>Declared supply source<input required value={source} onChange={(event) => setSource(event.target.value)} /></label>}
        <button type="submit" disabled={busy}>Seal hypothetical proposal</button>
      </form> : <>
        <h3>Exact resource diff</h3>
        <table><caption>Opening water inventory before and after this hypothetical edit</caption>
          <thead><tr><th scope="col">Store</th><th scope="col">Baseline (mL)</th><th scope="col">Variant (mL)</th><th scope="col">Change (mL)</th></tr></thead>
          <tbody>{waterAfter.map(([id, after]) => <tr key={id}><th scope="row">{id}</th><td>{waterBefore.get(id) ?? 0}</td>
            <td>{after}</td><td>{after - (waterBefore.get(id) ?? 0)}</td></tr>)}</tbody>
        </table>
        <p>Declared added water: {proposal.content.variant.declared_added_water_ml} mL. Proposal hash: {proposal.content_hash}. Variant hash: {proposal.content.variant.variant_hash}.</p>
        <p>Operation: {JSON.stringify(proposal.content.operations)}.</p>
        <p>Untested proposal. No measured improvement is claimed until a matched, completed paired comparison is available.</p>
        <form onSubmit={(event) => { void evaluate(event); }} className="review-form">
          <h3>Inspect paired runs</h3>
          <p>Enter committed run IDs in the sealed suite order. The server verifies baseline, variant, source, graph, scenario and model pins.</p>
          <label>Baseline member run IDs (comma separated)<input required value={baselineJobs} onChange={(event) => setBaselineJobs(event.target.value)} /></label>
          <label>Variant member run IDs (comma separated)<input value={variantJobs} onChange={(event) => setVariantJobs(event.target.value)} /></label>
          <button type="submit" disabled={busy}>Evaluate paired evidence</button>
        </form>
      </>}
      {comparison && <>
        <h3>Paired comparison: {comparison.status}</h3>
        <p>{comparison.reason ?? 'Same pinned scope, scenario suite, engine and policy.'} {comparison.measured_improvement && comparison.status === 'complete'
          ? 'Measured improvement within this modeled suite.' : 'No measured improvement claim.'}</p>
        <p>Completed baseline members: {comparison.completed_baseline_members} of {comparison.planned_members} planned. Excluded pair members: {comparison.excluded_member_ids?.join(', ') || 'none'}.</p>
        <p>Policy: {comparison.policy_version ?? 'unknown'}; priority: {comparison.priority_label}. Results are exploratory and depend on declared resources, scope and response policy. Recurrence is not a real-world probability.</p>
        <h4>Paired gains and regressions</h4>
        <table><caption>Variant minus baseline; negative water unmet and stranded values are gains</caption>
          <thead><tr><th scope="col">Member</th><th scope="col">On-time people Δ</th><th scope="col">Vulnerable on-time people Δ</th><th scope="col">Water unmet Δ (mL)</th><th scope="col">Stranded people Δ</th><th scope="col">Regressions</th><th scope="col">Evidence events</th></tr></thead>
          <tbody>{comparison.deltas.map((item) => <tr key={String(item.member_id)}>
            <th scope="row">{String(item.member_id)}</th><td>{String(item.on_time_people)}</td>
            <td>{String(item.vulnerable_on_time_people)}</td>
            <td>{String(item.water_unmet_ml)}</td><td>{String(item.stranded_people)}</td>
            <td>{(item.regression_keys as string[])?.join(', ') || 'none'}</td>
            <td>{(item.evidence_event_ids as string[])?.join(', ')}</td></tr>)}</tbody>
        </table>
        <h4>Ranked modeled findings</h4>
        <ol>{[...comparison.findings].sort((a, b) => Number(b.distinct_affected_people) - Number(a.distinct_affected_people)).map((item) =>
          <li key={String(item.key)}>{String(item.key)}: {String(item.distinct_affected_people)} distinct modeled people;
            recurrence {String(item.recurrence_numerator)}/{String(item.recurrence_denominator)} completed members
            ({String(item.planned_members)} planned). Evidence: {(item.evidence_event_ids as string[])?.join(', ')}.
          </li>)}</ol>
      </>}
    </>}
  </section>;
}

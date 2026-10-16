import { useCallback, useEffect, useState, type FormEvent } from 'react';
import type { components } from '../../../../../packages/client-generated/private-commands';
import { useTemporarySession } from '../../components/session';
import { formatManila, integerSeconds, manilaLocalToUtc } from '../../lib/formatting';

type Targets = components['schemas']['ScenarioTargets'];
type Effect = 'edge_closed' | 'asset_closed' | 'vehicle_outage' | 'shelter_capacity';
type Event = {
  id: string; effect: Effect; target_id: string; effective_seconds: number;
  known_seconds: number; hazard_reference: string; capacity_people: number | null;
};
type ScenarioRecord = {
  sealed: boolean; content_hash: string;
  content: {
    baseline_hash: string;
    scenario: { id: string; horizon_seconds: number; events: Event[] };
    editor: {
      scenario_title: string; scenario_start_utc: string; demand_people: number;
      deadline_seconds: number; power_event_id: string | null;
      communication_event_id: string | null; assumption_notes: string[];
    };
  };
};
type SuiteRecord = { sealed: boolean; content: {
  scenario_ids: string[]; suite_hash: string; seed: number; baseline_hash: string;
} };

function targetChoices(targets: Targets, effect: Effect): string[] {
  return effect === 'edge_closed' ? targets.edge_ids
    : effect === 'asset_closed' ? targets.asset_ids
      : effect === 'vehicle_outage' ? targets.vehicle_ids : targets.shelter_ids;
}

async function result<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const issue = await response.json() as { code?: string; title?: string; detail?: string };
    throw new Error(`${issue.code ?? 'scenario_error'}: ${issue.title ?? issue.detail ?? 'Request failed'}`);
  }
  return response.json() as Promise<T>;
}

export function ScenarioEditor() {
  const session = useTemporarySession();
  const base = `/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}/scenarios`;
  const [targets, setTargets] = useState<Targets | null>(null);
  const [sealed, setSealed] = useState<ScenarioRecord | null>(null);
  const [suite, setSuite] = useState<SuiteRecord | null>(null);
  const [suiteIds, setSuiteIds] = useState('main');
  const [suiteSeed, setSuiteSeed] = useState('42');
  const [status, setStatus] = useState('Checking the sealed baseline…');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scenarioId, setScenarioId] = useState('main');
  const [title, setTitle] = useState('Reviewed pilot scenario');
  const [startLocal, setStartLocal] = useState('2026-10-16T08:00');
  const [demand, setDemand] = useState('100');
  const [deadlineMinutes, setDeadlineMinutes] = useState('120');
  const [horizonHours, setHorizonHours] = useState('4');
  const [assumptionNote, setAssumptionNote] = useState('Illustrative evacuation demand, available vehicle and facility; not field verified.');
  const [effect, setEffect] = useState<Effect>('edge_closed');
  const [target, setTarget] = useState('');
  const [effectiveMinutes, setEffectiveMinutes] = useState('30');
  const [knownMinutes, setKnownMinutes] = useState('30');
  const [capacity, setCapacity] = useState('0');
  const [hazardReference, setHazardReference] = useState('User-defined scenario condition');
  const [events, setEvents] = useState<Event[]>([]);
  const [powerEventId, setPowerEventId] = useState('');
  const [communicationEventId, setCommunicationEventId] = useState('');

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const response = await fetch(`${base}/targets`, { credentials: 'same-origin', cache: 'no-store' });
      if (response.status === 404) {
        setTargets(null); setSealed(null); setStatus('Seal and acknowledge a Community Twin baseline first.');
        return;
      }
      setTargets(await result<Targets>(response));
      const existing = await fetch(`${base}/${encodeURIComponent(scenarioId)}`, {
        credentials: 'same-origin', cache: 'no-store',
      });
      setSealed(existing.status === 404 ? null : await result<ScenarioRecord>(existing));
      const suiteResponse = await fetch(`/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}/scenario-suites/main`, {
        credentials: 'same-origin', cache: 'no-store',
      });
      setSuite(suiteResponse.status === 404 ? null : await result<SuiteRecord>(suiteResponse));
      setStatus('Owner-scoped baseline and scenario targets loaded.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load scenario targets.');
    }
  }, [base, scenarioId, session.workspace_id]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const update = () => { void refresh(); };
    window.addEventListener('private-baseline-sealed', update);
    window.addEventListener('focus', update);
    return () => {
      window.removeEventListener('private-baseline-sealed', update);
      window.removeEventListener('focus', update);
    };
  }, [refresh]);

  function addEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const next: Event = {
        id: crypto.randomUUID(), effect, target_id: target.trim(),
        effective_seconds: integerSeconds(effectiveMinutes, 60),
        known_seconds: integerSeconds(knownMinutes, 60),
        hazard_reference: hazardReference.trim(),
        capacity_people: effect === 'shelter_capacity' ? integerSeconds(capacity) : null,
      };
      setEvents((prior) => [...prior, next]);
      setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Invalid event input.'); }
  }

  async function seal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!targets) return;
    setBusy(true); setError(null);
    try {
      const body = {
        schema_version: 'scenario.editor.v1', baseline_id: 'main',
        baseline_hash: targets.baseline_hash, scenario_title: title.trim(),
        scenario_start_utc: manilaLocalToUtc(startLocal),
        demand_people: integerSeconds(demand),
        deadline_seconds: integerSeconds(deadlineMinutes, 60),
        horizon_seconds: integerSeconds(horizonHours, 3600), events,
        power_event_id: powerEventId || null,
        communication_event_id: communicationEventId || null,
        assumption_notes: [assumptionNote.trim()],
      };
      const response = await fetch(`${base}/${encodeURIComponent(scenarioId)}`, {
        method: 'PUT', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token,
          'If-Match': '0', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify(body),
      });
      setSealed(await result<ScenarioRecord>(response));
      setSuiteIds((prior) => [...new Set([...prior.split(',').map((item) => item.trim()).filter(Boolean), scenarioId])].join(', '));
      setStatus('Immutable scenario sealed for this temporary analysis.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Scenario rejected.'); }
    finally { setBusy(false); }
  }

  async function sealSuite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      const response = await fetch(`/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}/scenario-suites/main`, {
        method: 'PUT', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token,
          'If-Match': '0', 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ scenario_ids: suiteIds.split(',').map((item) => item.trim()).filter(Boolean),
          seed: integerSeconds(suiteSeed) }),
      });
      setSuite(await result<SuiteRecord>(response));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Suite rejected.'); }
    finally { setBusy(false); }
  }

  const summary = sealed?.content;
  return <section className="panel" aria-labelledby="scenario-editor-heading">
    <p className="eyebrow">Scenario · owner-scoped</p>
    <h2 id="scenario-editor-heading">Structured Scenario editor</h2>
    <p role="status">{status}</p>
    {error && <p role="alert">{error}</p>}
    {targets && <>
      <p>Sealed baseline: {targets.baseline_hash}. Choose only targets in its reviewed graph and resources.</p>
      <label htmlFor="scenario-id">Scenario ID</label>
      <input id="scenario-id" value={scenarioId} onChange={(event) => setScenarioId(event.target.value)} />
      {summary ? <>
        <h3>Sealed deterministic input summary</h3>
        <p>{summary.editor.scenario_title}. Starts {formatManila(summary.editor.scenario_start_utc)} (Asia/Manila).
          Demand: {summary.editor.demand_people} people; deadline: {summary.editor.deadline_seconds} seconds;
          horizon: {summary.scenario.horizon_seconds} seconds.</p>
        <ul>{summary.scenario.events.map((item) => <li key={item.id}>
          {item.effect} on {item.target_id} at {item.effective_seconds} seconds;
          known at {item.known_seconds} seconds. {item.hazard_reference}
          {item.capacity_people !== null && <>; new capacity {item.capacity_people} people</>}.
        </li>)}</ul>
        <p>Power effect event: {summary.editor.power_event_id ?? 'none'}. Communication effect event: {summary.editor.communication_event_id ?? 'none'}.</p>
        <p>Assumption: {summary.editor.assumption_notes.join('; ')}. Sealed hash: {sealed.content_hash}.</p>
      </> : <>
        <form onSubmit={(event) => { void seal(event); }} className="review-form">
          <label>Scenario title (display only)<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
          <label>Start in Asia/Manila<input required type="datetime-local" value={startLocal} onChange={(event) => setStartLocal(event.target.value)} /></label>
          <label>Evacuation demand (people)<input required value={demand} onChange={(event) => setDemand(event.target.value)} /></label>
          <label>Deadline (minutes after start)<input required value={deadlineMinutes} onChange={(event) => setDeadlineMinutes(event.target.value)} /></label>
          <label>Horizon (hours)<input required value={horizonHours} onChange={(event) => setHorizonHours(event.target.value)} /></label>
          <label>Scenario assumptions and limits<input required value={assumptionNote} onChange={(event) => setAssumptionNote(event.target.value)} /></label>
          <label>Power consequence<select value={powerEventId} onChange={(event) => setPowerEventId(event.target.value)}>
            <option value="">No modeled effect</option>{events.map((item) => <option key={item.id} value={item.id}>{item.effect}: {item.target_id}</option>)}
          </select></label>
          <label>Communication consequence<select value={communicationEventId} onChange={(event) => setCommunicationEventId(event.target.value)}>
            <option value="">No modeled effect</option>{events.map((item) => <option key={item.id} value={item.id}>{item.effect}: {item.target_id}</option>)}
          </select></label>
          <button type="submit" disabled={busy}>Review and seal scenario</button>
        </form>
        <h3>Operational events</h3>
        <p>A hazard description has no numeric effect by itself. Add an explicit operational event and target to change the simulation.</p>
        <form onSubmit={addEvent} className="review-form">
          <label>Operational effect<select value={effect} onChange={(event) => { setEffect(event.target.value as Effect); setTarget(''); }}>
            <option value="edge_closed">Road edge closed</option><option value="asset_closed">Road asset closed</option>
            <option value="vehicle_outage">Vehicle outage</option><option value="shelter_capacity">Shelter capacity</option>
          </select></label>
          <label>Reviewed target ID<input required list="scenario-targets" value={target} onChange={(event) => setTarget(event.target.value)} /></label>
          <datalist id="scenario-targets">{targetChoices(targets, effect).map((item) => <option key={item} value={item} />)}</datalist>
          <label>Effective after start (minutes)<input required value={effectiveMinutes} onChange={(event) => setEffectiveMinutes(event.target.value)} /></label>
          <label>Known after start (minutes)<input required value={knownMinutes} onChange={(event) => setKnownMinutes(event.target.value)} /></label>
          {effect === 'shelter_capacity' && <label>New capacity (people)<input required value={capacity} onChange={(event) => setCapacity(event.target.value)} /></label>}
          <label>Hazard or assumption reference<input required value={hazardReference} onChange={(event) => setHazardReference(event.target.value)} /></label>
          <button type="submit">Add structured event</button>
        </form>
        <ul>{events.map((item) => <li key={item.id}>{item.effect} on {item.target_id}; effective {item.effective_seconds} seconds,
          known {item.known_seconds} seconds. {item.hazard_reference}
          <button type="button" className="text-button" onClick={() => setEvents((prior) => prior.filter((entry) => entry.id !== item.id))}>Remove event</button>
        </li>)}</ul>
      </>}
      <h3>Scenario suite</h3>
      {suite ? <p>Immutable suite retained in this temporary session. Members: {suite.content.scenario_ids.join(', ')};
        seed: {suite.content.seed}; suite hash: {suite.content.suite_hash}.</p> :
        <form onSubmit={(event) => { void sealSuite(event); }} className="review-form">
          <label>Sealed scenario IDs (comma separated)<input required value={suiteIds} onChange={(event) => setSuiteIds(event.target.value)} /></label>
          <label>Suite seed (nonnegative integer)<input required value={suiteSeed} onChange={(event) => setSuiteSeed(event.target.value)} /></label>
          <button type="submit" disabled={busy}>Seal selected scenario suite</button>
        </form>}
    </>}
  </section>;
}

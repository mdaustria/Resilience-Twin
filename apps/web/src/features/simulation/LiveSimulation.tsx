import { useEffect, useState, type FormEvent } from 'react';
import type { components } from '../../../../../packages/client-generated/private-commands';
import { useTemporarySession } from '../../components/session';
import { pollingDelay } from '../../lib/polling';

type RunStatus = components['schemas']['RunStatus'];
type RunEvent = components['schemas']['RunEvent'];
type EventPage = components['schemas']['EventPage'];

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const issue = await response.json() as { code?: string; title?: string };
    throw new Error(`${issue.code ?? 'run_error'}: ${issue.title ?? 'Request failed'}`);
  }
  return response.json() as Promise<T>;
}

export function LiveSimulation() {
  const session = useTemporarySession();
  const storageKey = `rt-run:${session.workspace_id}`;
  const [runId, setRunId] = useState(() => sessionStorage.getItem(storageKey) ?? '');
  const [draftId, setDraftId] = useState(runId);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [visibleCount, setVisibleCount] = useState(0);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRunId(sessionStorage.getItem(storageKey) ?? '');
    setDraftId(sessionStorage.getItem(storageKey) ?? '');
  }, [storageKey]);

  useEffect(() => {
    if (!runId) return;
    let stopped = false;
    let timer = 0;
    let cursor = 0;
    let failures = 0;
    const base = `/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}/runs/${encodeURIComponent(runId)}`;
    setStatus(null); setEvents([]); setVisibleCount(0); setSelected(null); setError(null);
    const poll = async () => {
      try {
        const current = await json<RunStatus>(await fetch(base, { credentials: 'same-origin', cache: 'no-store' }));
        if (current.stage !== 'simulation') throw new Error('This job is not a simulation run.');
        let more = true;
        for (let pageNumber = 0; pageNumber < 10 && more; pageNumber += 1) {
          const page = await json<EventPage>(await fetch(`${base}/events?after=${cursor}&limit=100`, {
            credentials: 'same-origin', cache: 'no-store',
          }));
          if (stopped) return;
          if (page.items.length) {
            cursor += page.items.length;
            setEvents((prior) => [...prior, ...page.items]);
          }
          more = page.next !== null;
        }
        if (stopped) return;
        setStatus(current); setError(null); failures = 0;
        timer = window.setTimeout(() => { void poll(); }, pollingDelay(current.status, document.hidden, failures));
      } catch (reason) {
        if (stopped) return;
        failures += 1;
        setError(reason instanceof Error ? reason.message : 'Run polling failed.');
        timer = window.setTimeout(() => { void poll(); }, pollingDelay('running', document.hidden, failures));
      }
    };
    void poll();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [runId, session.workspace_id]);

  useEffect(() => {
    if (paused || visibleCount >= events.length) return;
    const timer = window.setInterval(() => setVisibleCount((count) => Math.min(count + 1, events.length)),
      Math.max(100, 700 / speed));
    return () => window.clearInterval(timer);
  }, [paused, speed, visibleCount, events.length]);

  function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = draftId.trim();
    sessionStorage.setItem(storageKey, value);
    setRunId(value);
  }

  async function cancel() {
    if (!runId) return;
    setBusy(true); setError(null);
    try {
      await json(await fetch(`/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}/runs/${encodeURIComponent(runId)}/cancel`, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'X-CSRF-Token': session.csrf_token },
      }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Cancellation failed.'); }
    finally { setBusy(false); }
  }

  const shown = events.slice(0, visibleCount);
  const lanes = [...new Set(events.map((item) => item.target_id ?? 'system'))].sort();
  const maxTime = Math.max(1, ...events.map((item) => item.time_seconds));
  const detail = selected === null ? null : events[selected];
  return <section className="panel" aria-labelledby="live-simulation-heading">
    <p className="eyebrow">Live Simulation · committed events</p>
    <h2 id="live-simulation-heading">Run playback</h2>
    <form onSubmit={connect} className="review-form">
      <label>Run ID<input required value={draftId} onChange={(event) => setDraftId(event.target.value)} /></label>
      <button type="submit">Connect to run</button>
    </form>
    <p>Playback reads committed events from this temporary workspace. Polling does not renew its expiry.</p>
    {error && <p role="alert">{error}</p>}
    {runId && <>
      <p role="status">{status ? `Job ${status.status}; run ${status.run_status}; attempt ${status.attempt}; checkpoint ${status.checkpoint_sequence}; ${events.length} committed events.` : 'Connecting to run…'}</p>
      {status?.status === 'failed' && <p>Computation failed. Earlier committed events remain inspectable.</p>}
      {status?.status === 'cancelled' && <p>Computation was cancelled. This is a partial result.</p>}
      {status?.run_status === 'partial' && <p>Partial run: checkpointed progress is visible; no completed outcome is claimed.</p>}
      <div className="session-actions">
        <button type="button" onClick={() => setPaused((value) => !value)}>{paused ? 'Resume playback' : 'Pause playback'}</button>
        <label>Playback speed<select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
          <option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option>
        </select></label>
        <button type="button" onClick={() => setVisibleCount(events.length)}>Show latest committed event</button>
        <button type="button" className="secondary" disabled={busy || status?.status === 'complete' || status?.status === 'cancelled'} onClick={() => { void cancel(); }}>Cancel computation</button>
      </div>
      <label>Playback position ({visibleCount} of {events.length} committed events)
        <input type="range" min="0" max={events.length} value={visibleCount}
          onChange={(event) => setVisibleCount(Number(event.target.value))} />
      </label>
      <h3>Event target schematic</h3>
      <p>This diagram uses simulation time and target lanes. It does not claim geographic coordinates.</p>
      <svg role="img" aria-label="Schematic event map by simulation time and target" viewBox={`0 0 600 ${Math.max(80, 30 + lanes.length * 32)}`} width="100%" height={Math.max(80, 30 + lanes.length * 32)}>
        {lanes.map((lane, index) => <g key={lane}><line x1="110" x2="580" y1={25 + index * 32} y2={25 + index * 32} stroke="#859d96" />
          <text x="2" y={30 + index * 32} fontSize="10">{lane.slice(0, 18)}</text></g>)}
        {shown.map((item, index) => <circle key={`${index}-${item.sequence}`} cx={110 + 470 * item.time_seconds / maxTime}
          cy={25 + lanes.indexOf(item.target_id ?? 'system') * 32} r="5" fill="#125e52" />)}
      </svg>
      <h3>Committed event table</h3>
      <table><caption>Same event sequence as the schematic; times are seconds after scenario start</caption>
        <thead><tr><th scope="col">Order</th><th scope="col">Time (s)</th><th scope="col">Event</th><th scope="col">Target</th><th scope="col">Inspect</th></tr></thead>
        <tbody>{shown.map((item, index) => <tr key={`${index}-${item.sequence}`}><td>{index + 1}</td>
          <td>{item.time_seconds}</td><td>{item.kind}</td><td>{item.target_id ?? 'system'}</td>
          <td><button type="button" className="text-button" onClick={() => setSelected(index)}>Inspect event {index + 1}</button></td></tr>)}</tbody>
      </table>
      {detail && <p>Event detail: sequence {detail.sequence}; phase {detail.phase}; {detail.kind} at {detail.time_seconds} seconds; target {detail.target_id ?? 'system'}.</p>}
    </>}
  </section>;
}

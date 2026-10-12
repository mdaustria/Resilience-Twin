import { useCallback, useEffect, useState } from 'react';
import { CaseReview } from '../features/community-twin/CaseReview';
import { RunResult } from '../features/simulation/RunResult';
import { loadCase, runCase, type SkeletonCase, type SkeletonResult } from '../lib/skeletonClient';
import './app.css';

type FailedAction = 'open' | 'run' | null;

export function App() {
  const [caseId, setCaseId] = useState('one-trip-water');
  const [caseData, setCaseData] = useState<SkeletonCase | null>(null);
  const [result, setResult] = useState<SkeletonResult | null>(null);
  const [busy, setBusy] = useState<'open' | 'run' | null>('open');
  const [error, setError] = useState<string | null>(null);
  const [failedAction, setFailedAction] = useState<FailedAction>(null);

  const open = useCallback(async (id: string) => {
    setBusy('open');
    setError(null);
    setFailedAction(null);
    setCaseData(null);
    setResult(null);
    try {
      setCaseData(await loadCase(id.trim()));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not open the case.');
      setFailedAction('open');
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => { void open('one-trip-water'); }, [open]);

  const run = async () => {
    if (!caseData) return;
    setBusy('run');
    setError(null);
    setFailedAction(null);
    setResult(null);
    try {
      setResult(await runCase(caseData));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not run the case.');
      setFailedAction('run');
    } finally {
      setBusy(null);
    }
  };

  return (
    <main className="shell">
      <header className="masthead">
        <p className="eyebrow">Local model proof · synthetic data</p>
        <h1>Resilience Twin</h1>
        <p>Review a case and run a small, deterministic evacuation and water calculation.</p>
      </header>
      <nav aria-label="Analysis stages" className="stages">
        <span>1 · Community Twin</span><span>2 · Scenario</span><span>3 · Live Simulation</span><span>4 · Resilience Findings</span>
      </nav>
      <section aria-labelledby="case-heading" className="case-picker">
        <h2 id="case-heading">Local training case</h2>
        <form onSubmit={(event) => { event.preventDefault(); void open(caseId); }}>
          <label htmlFor="case-id">Case ID</label>
          <input id="case-id" value={caseId} onChange={(event) => setCaseId(event.target.value)} required />
          <button type="submit" disabled={busy !== null}>Open case</button>
        </form>
      </section>
      {busy === 'open' && <p role="status">Opening case…</p>}
      {error && <div role="alert" className="error"><p>{error}</p><button type="button" onClick={() => { if (failedAction === 'run') void run(); else void open(caseId); }}>Try again</button></div>}
      {caseData && <>
        <CaseReview caseData={caseData} />
        <section aria-labelledby="run-heading" className="run-step">
          <h2 id="run-heading">Run this case</h2>
          <p>Results are computed by the local API and simulation engine.</p>
          <button type="button" disabled={busy !== null} onClick={() => { void run(); }}>Run analysis</button>
          {busy === 'run' && <p role="status">Running analysis…</p>}
        </section>
      </>}
      {result && <RunResult result={result} />}
    </main>
  );
}

import { useEffect, useState } from 'react';
import { useTemporarySession } from '../session';

type Kind = 'gap_only' | 'findings' | 'revision';
type ReportJob = { kind: Kind; job_id: string; status: string; report_id: string };
const names: Record<Kind, string> = {
  gap_only: 'Source-only gap report', findings: 'Evaluated findings report',
  revision: 'Hypothetical revision report',
};

export function ReportDownloads() {
  const session = useTemporarySession();
  const base = `/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}/reports`;
  const cacheKey = `rt-report:${session.workspace_id}`;
  const [jobs, setJobs] = useState<ReportJob[]>(() => {
    try { return JSON.parse(sessionStorage.getItem(cacheKey) ?? '[]') as ReportJob[]; }
    catch { return []; }
  });
  const [baselineIds, setBaselineIds] = useState('');
  const [variantIds, setVariantIds] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ids = (value: string) => value.split(',').map((item) => item.trim()).filter(Boolean);

  useEffect(() => { sessionStorage.setItem(cacheKey, JSON.stringify(jobs)); }, [cacheKey, jobs]);
  useEffect(() => {
    if (!jobs.some((job) => job.status === 'queued' || job.status === 'running')) return;
    const timer = window.setInterval(() => {
      void Promise.all(jobs.map(async (job) => {
        if (job.status === 'complete') return job;
        const response = await fetch(`${base}/jobs/${encodeURIComponent(job.job_id)}`,
          { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) return job;
        const state = await response.json() as { status: string };
        return { ...job, status: state.status };
      })).then(setJobs);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [base, jobs]);

  async function create(kind: Kind) {
    setBusy(true); setError(null);
    try {
      const response = await fetch(`${base}/${kind}`, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token,
          'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ baseline_job_ids: ids(baselineIds), variant_job_ids: ids(variantIds) }),
      });
      if (!response.ok) {
        const issue = await response.json() as { code?: string; title?: string };
        throw new Error(`${issue.code ?? 'report_error'}: ${issue.title ?? 'Report request failed'}`);
      }
      const job = await response.json() as ReportJob;
      setJobs((prior) => [...prior.filter((item) => item.kind !== kind), job]);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Report unavailable.'); }
    finally { setBusy(false); }
  }

  async function download(job: ReportJob) {
    setError(null);
    try {
      const response = await fetch(`${base}/jobs/${encodeURIComponent(job.job_id)}/download`,
        { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) throw new Error(`Report download unavailable (${response.status}).`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url; link.download = `independent-${job.kind}.pdf`;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Report download failed.'); }
  }

  return <section className="panel" aria-labelledby="reports-heading">
    <p className="eyebrow">Independent exports</p><h2 id="reports-heading">Download reports</h2>
    <p>Reports preserve the uploaded source hash. Untested changes carry no measured improvement claim. Download before this temporary session expires.</p>
    <label>Baseline member run IDs (for findings)<input value={baselineIds}
      onChange={(event) => setBaselineIds(event.target.value)} /></label>
    <label>Variant member run IDs (for findings)<input value={variantIds}
      onChange={(event) => setVariantIds(event.target.value)} /></label>
    <div>{(Object.keys(names) as Kind[]).map((kind) => <button key={kind} type="button"
      disabled={busy} onClick={() => { void create(kind); }}>Create {names[kind]}</button>)}</div>
    {error && <p role="alert">{error}</p>}
    <ul>{jobs.map((job) => <li key={job.kind}>
      {names[job.kind]}: <span data-report-job={job.job_id}>{job.status}</span>.
      {job.status === 'complete' && <button type="button"
        onClick={() => { void download(job); }}>Download {names[job.kind]} PDF</button>}
    </li>)}</ul>
  </section>;
}

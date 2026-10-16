import type { components } from '../../../../packages/client-generated/private-commands';
import type { SessionStatus } from './sessionClient';

export type ReviewRecord = components['schemas']['DurableReviewRecord'];
export type ReviewDraft = components['schemas']['ReviewDraft'];
export type ReviewClaim = components['schemas']['ReviewClaim'];
export type ReviewAssumption = components['schemas']['ReviewAssumption'];
export type ArtifactCoverage = components['schemas']['ArtifactCoverage'];
export type InitializeReview = components['schemas']['InitializeReviewCommand'];
export type PrivatePilotLocation = components['schemas']['PrivatePilotLocation'];
type ConfirmedPrivateLocation = components['schemas']['ConfirmedPrivateLocation'];
export type PilotCase = 'qc' | 'guiguinto';
export type BaselineRecord = {
  revision: number; sealed: boolean;
  content: { baseline_hash: string; graph_hash: string; review_hash: string };
};

export class ReviewRequestError extends Error {
  constructor(public readonly status: number, public readonly code: string) {
    super(`Review request failed (${status}): ${code.replaceAll('_', ' ')}.`);
  }
}

const base = (session: SessionStatus) =>
  `/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}`;

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code = 'request_failed';
    try {
      const issue = await response.json() as { code?: unknown; detail?: unknown };
      if (typeof issue.code === 'string') code = issue.code;
      else if (typeof issue.detail === 'string') code = issue.detail;
    } catch { /* Keep status and generic code. */ }
    throw new ReviewRequestError(response.status, code);
  }
  return response.json() as Promise<T>;
}

export async function readReview(session: SessionStatus): Promise<ReviewRecord | null> {
  const response = await fetch(`${base(session)}/reviews/main`, {
    credentials: 'same-origin', cache: 'no-store',
  });
  if (response.status === 404) return null;
  return json<ReviewRecord>(response);
}

export async function readCoverage(session: SessionStatus, artifactId: string): Promise<ArtifactCoverage> {
  return json<ArtifactCoverage>(await fetch(
    `${base(session)}/artifacts/${encodeURIComponent(artifactId)}/coverage`,
    { credentials: 'same-origin', cache: 'no-store' }));
}

function commandHeaders(session: SessionStatus, revision: number): Record<string, string> {
  return {
    'X-CSRF-Token': session.csrf_token,
    'If-Match': String(revision),
    'Idempotency-Key': crypto.randomUUID(),
  };
}

export async function initializeReview(session: SessionStatus, body: InitializeReview): Promise<ReviewRecord> {
  return json<ReviewRecord>(await fetch(`${base(session)}/reviews/main/initialize`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { ...commandHeaders(session, 0), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }));
}

export async function saveReview(session: SessionStatus, record: ReviewRecord,
                                 draft: ReviewDraft): Promise<ReviewRecord> {
  return json<ReviewRecord>(await fetch(`${base(session)}/reviews/main`, {
    method: 'PUT', credentials: 'same-origin', cache: 'no-store',
    headers: { ...commandHeaders(session, record.revision), 'Content-Type': 'application/json' },
    body: JSON.stringify(draft),
  }));
}

export async function sealReview(session: SessionStatus, record: ReviewRecord): Promise<ReviewRecord> {
  return json<ReviewRecord>(await fetch(`${base(session)}/reviews/main/seal`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: commandHeaders(session, record.revision),
  }));
}

export async function acknowledgeReview(session: SessionStatus, record: ReviewRecord): Promise<ReviewRecord> {
  return json<ReviewRecord>(await fetch(`${base(session)}/reviews/main/acknowledge`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: commandHeaders(session, record.revision),
  }));
}

export async function citedPdf(session: SessionStatus, artifactId: string): Promise<Blob> {
  const response = await fetch(`${base(session)}/artifacts/${encodeURIComponent(artifactId)}/download`, {
    credentials: 'same-origin', cache: 'no-store',
  });
  if (!response.ok) throw new ReviewRequestError(response.status, 'citation_unavailable');
  return response.blob();
}

export async function readPilotLocation(session: SessionStatus, pilot: PilotCase): Promise<PrivatePilotLocation> {
  return json<PrivatePilotLocation>(await fetch(`${base(session)}/geography/pilot/${pilot}`, {
    credentials: 'same-origin', cache: 'no-store',
  }));
}

export async function confirmPilotLocation(session: SessionStatus, record: ReviewRecord,
                                            pilot: PilotCase, scopeDigest: string): Promise<{
  location: PrivatePilotLocation; review: ReviewRecord;
}> {
  const result = await json<ConfirmedPrivateLocation>(await fetch(
    `${base(session)}/geography/pilot/${pilot}/confirm`, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { ...commandHeaders(session, record.revision), 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_scope_digest: scopeDigest }),
    }));
  return { location: { snapshot: result.snapshot, graph_artifact_id: result.graph_artifact_id },
    review: result.review };
}

export async function readBaseline(session: SessionStatus): Promise<BaselineRecord | null> {
  const response = await fetch(`${base(session)}/baselines/main`, {
    credentials: 'same-origin', cache: 'no-store',
  });
  if (response.status === 404) return null;
  return json<BaselineRecord>(response);
}

export async function sealBaseline(session: SessionStatus, record: ReviewRecord,
                                    location: PrivatePilotLocation): Promise<BaselineRecord> {
  const assumptions = new Map(record.content.draft.assumptions.map((item) => [item.field, item.value]));
  const water = assumptions.get('opening_water_ml');
  const pickup = location.snapshot.area.connectors[0];
  const facility = location.snapshot.area.connectors[1];
  if (!record.content.readiness.ready_to_run || !water || !pickup || !facility) {
    throw new Error('Seal and acknowledge a complete reviewed pilot before creating a baseline.');
  }
  const body = {
    review_id: 'main', review_revision: record.revision,
    graph_artifact_id: location.graph_artifact_id,
    resources: {
      water_stores: [[facility.id, Number(water)]],
      vehicle_starts: [['pilot-vehicle', pickup.road_node_id]],
      shelter_ids: [facility.id],
    },
  };
  return json<BaselineRecord>(await fetch(`${base(session)}/baselines/main`, {
    method: 'PUT', credentials: 'same-origin', cache: 'no-store',
    headers: { ...commandHeaders(session, 0), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }));
}

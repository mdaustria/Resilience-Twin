import type { paths } from '../../../../packages/client-generated/skeleton';

export type SkeletonCase = paths['/api/v1/local/cases/{case_id}']['get']['responses'][200]['content']['application/json'];
export type SkeletonResult = paths['/api/v1/local/cases/{case_id}/run']['post']['responses'][200]['content']['application/json'];
type RunBody = paths['/api/v1/local/cases/{case_id}/run']['post']['requestBody']['content']['application/json'];

const owner = 'fixture-a';

async function checkedJson<T>(response: Response, action: string): Promise<T> {
  if (!response.ok) {
    throw new Error(`${action} failed (${response.status}). Check the case and try again.`);
  }
  return response.json() as Promise<T>;
}

export async function loadCase(caseId: string): Promise<SkeletonCase> {
  const response = await fetch(`/api/v1/local/cases/${encodeURIComponent(caseId)}`, {
    headers: { 'X-Fixture-Owner': owner },
  });
  return checkedJson<SkeletonCase>(response, 'Opening the case');
}

export async function runCase(caseData: SkeletonCase): Promise<SkeletonResult> {
  const body: RunBody = caseData;
  const response = await fetch(`/api/v1/local/cases/${encodeURIComponent(caseData.case_id)}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Fixture-Owner': owner },
    body: JSON.stringify(body),
  });
  return checkedJson<SkeletonResult>(response, 'Running the case');
}

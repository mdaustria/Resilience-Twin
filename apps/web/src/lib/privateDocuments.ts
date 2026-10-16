import type { components } from '../../../../packages/client-generated/private-commands';
import type { SessionStatus } from './sessionClient';

export type ArtifactStatus = components['schemas']['ArtifactStatus'];
type UploadStatus = components['schemas']['UploadStatus'];
type UploadReceipt = components['schemas']['UploadReceipt'];

export class PrivateDocumentError extends Error {
  constructor(public readonly status: number, public readonly code: string) {
    super(`PDF upload failed (${status}): ${code.replaceAll('_', ' ')}.`);
  }
}

async function requireJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let code = 'request_failed';
    try {
      const problem = await response.json() as { detail?: string };
      if (typeof problem.detail === 'string') code = problem.detail;
    } catch { /* The response may have no body. */ }
    throw new PrivateDocumentError(response.status, code);
  }
  return response.json() as Promise<T>;
}

function uploadBytes(url: string, bytes: ArrayBuffer, session: SessionStatus, token: string,
                     onProgress: (fraction: number) => void): Promise<UploadReceipt> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.withCredentials = true;
    xhr.setRequestHeader('X-CSRF-Token', session.csrf_token);
    xhr.setRequestHeader('X-Upload-Token', token);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total);
    };
    xhr.onerror = () => reject(new Error('PDF transfer interrupted. Try the upload again.'));
    xhr.onload = () => {
      if (xhr.status !== 200) {
        let code = 'transfer_failed';
        try { code = (JSON.parse(xhr.responseText) as { detail?: string }).detail ?? code; }
        catch { /* Keep generic error. */ }
        reject(new PrivateDocumentError(xhr.status, code));
        return;
      }
      try { resolve(JSON.parse(xhr.responseText) as UploadReceipt); }
      catch { reject(new Error('The server returned an invalid upload receipt.')); }
    };
    xhr.send(bytes);
  });
}

export async function uploadPdf(file: File, session: SessionStatus,
                                onProgress: (fraction: number) => void): Promise<ArtifactStatus> {
  const bytes = await file.arrayBuffer();
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
    .map((value) => value.toString(16).padStart(2, '0')).join('');
  const base = `/api/v1/workspaces/${encodeURIComponent(session.workspace_id)}/documents/uploads`;
  const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token };
  const grant = await requireJson<UploadStatus>(await fetch(base, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', headers,
    body: JSON.stringify({ sha256: digest, byte_count: file.size }),
  }));
  const receipt = await uploadBytes(`${base}/${encodeURIComponent(grant.upload_id)}/content`,
    bytes, session, grant.token, onProgress);
  const artifact = await requireJson<ArtifactStatus>(await fetch(
    `${base}/${encodeURIComponent(grant.upload_id)}/finalize`, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { ...headers, 'If-Match': '0' },
      body: JSON.stringify({ token: grant.token, quarantine_generation: receipt.generation }),
    }));
  if (artifact.sha256 !== digest || artifact.byte_count !== file.size) {
    throw new Error('The stored PDF identity differs from the selected file.');
  }
  onProgress(1);
  return artifact;
}

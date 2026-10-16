import type { components } from '../../../../packages/client-generated/private-commands';

export type SessionStatus = components['schemas']['SessionStatus'];

const endpoint = '/api/v1/temporary-sessions';

export class SessionRequestError extends Error {
  constructor(public readonly status: number, action: string) {
    super(`${action} failed (${status}). Please try again.`);
  }
}

async function checked(response: Response, action: string): Promise<SessionStatus> {
  if (!response.ok) throw new SessionRequestError(response.status, action);
  return response.json() as Promise<SessionStatus>;
}

export async function currentSession(): Promise<SessionStatus> {
  return checked(await fetch(`${endpoint}/current`, { credentials: 'same-origin', cache: 'no-store' }), 'Checking the temporary session');
}

export async function startSession(): Promise<SessionStatus> {
  return checked(await fetch(endpoint, { method: 'POST', credentials: 'same-origin', cache: 'no-store' }), 'Starting the analysis');
}

export async function renewSession(csrfToken: string): Promise<SessionStatus> {
  return checked(await fetch(`${endpoint}/current/activity`, {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken },
  }), 'Renewing the session');
}

export async function endSession(csrfToken: string): Promise<void> {
  const response = await fetch(`${endpoint}/current`, {
    method: 'DELETE', credentials: 'same-origin', cache: 'no-store',
    headers: { 'X-CSRF-Token': csrfToken },
  });
  if (!response.ok) throw new SessionRequestError(response.status, 'Ending the session');
}

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  currentSession, endSession, renewSession, SessionRequestError, startSession,
  type SessionStatus,
} from '../../lib/sessionClient';
import limits from '../../../../../release/limits.json';

type Phase = 'checking' | 'ready' | 'active' | 'unavailable';
const SessionContext = createContext<SessionStatus | null>(null);

export function useTemporarySession(): SessionStatus {
  const session = useContext(SessionContext);
  if (!session) throw new Error('Temporary session unavailable');
  return session;
}

export function TemporarySession({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<Phase>('checking');
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());

  const check = useCallback(async () => {
    try {
      const found = await currentSession();
      setSession(found);
      setPhase('active');
      setMessage(null);
    } catch (error) {
      setSession(null);
      if (error instanceof SessionRequestError && error.status === 401) {
        setPhase('ready');
      } else {
        setPhase('unavailable');
        setMessage(error instanceof Error ? error.message : 'Could not check the temporary session.');
      }
    }
  }, []);

  useEffect(() => { void check(); }, [check]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    const channel = new BroadcastChannel('resilience-twin-session');
    channel.onmessage = () => { void check(); };
    const onFocus = () => { void check(); };
    window.addEventListener('focus', onFocus);
    return () => { channel.close(); window.removeEventListener('focus', onFocus); };
  }, [check]);

  const announce = () => {
    const channel = new BroadcastChannel('resilience-twin-session');
    channel.postMessage('changed');
    channel.close();
  };
  const unavailable = (error: unknown) => {
    if (error instanceof SessionRequestError && (error.status === 401 || error.status === 403)) {
      setSession(null);
      setPhase('ready');
      setMessage('This analysis is unavailable or expired. Lost session credentials cannot be recovered. Start a new analysis.');
      announce();
    } else {
      setMessage(error instanceof Error ? error.message : 'The request failed. Please try again.');
    }
  };
  const start = async () => {
    setBusy(true);
    setMessage(null);
    try {
      setSession(await startSession());
      setPhase('active');
      announce();
    } catch (error) { unavailable(error); }
    finally { setBusy(false); }
  };
  const renew = async () => {
    if (!session) return;
    setBusy(true);
    setMessage(null);
    try { setSession(await renewSession(session.csrf_token)); }
    catch (error) { unavailable(error); }
    finally { setBusy(false); }
  };
  const end = async () => {
    if (!session) return;
    setBusy(true);
    setMessage(null);
    try {
      await endSession(session.csrf_token);
      setSession(null);
      setPhase('ready');
      setMessage('Analysis ended and deletion requested. Start again for a fresh workspace.');
      announce();
    } catch (error) { unavailable(error); }
    finally { setBusy(false); }
  };

  const remaining = session ? Math.min(Date.parse(session.expires_at), Date.parse(session.absolute_expires_at)) - now : 0;
  const active = phase === 'active' && session !== null && remaining > 0;
  const expired = phase === 'active' && session !== null && remaining <= 0;

  return <>
    <section aria-labelledby="session-heading" className="session-panel">
      <h2 id="session-heading">Temporary analysis</h2>
      {phase === 'checking' && <p role="status">Checking for an active analysis…</p>}
      {(phase === 'ready' || expired) && <>
        {expired && <p role="alert">This analysis has expired. Its workspace cannot be reopened; start fresh.</p>}
        <p>Start without an account. Your plan and results are stored temporarily on the server while this session is active. This is not zero storage.</p>
        <p>The session ends after 2 hours without deliberate activity or 24 hours from creation, whichever comes first. Refresh and other tabs on this browser can reconnect while its credential is valid. Closing a tab does not delete it. If the credential is lost, the analysis cannot be recovered.</p>
        <p>Download reports before expiry. Ending the analysis revokes access and requests deletion; active copies are designed for purge within 24 hours and backups within 7 days. Provider retention still needs verification before public upload. A new session starts an empty workspace; there is no saved history.</p>
        <p className="small">Current local demonstration uses synthetic data. PDF extraction is designed to use a backend AI provider; source uploads and provider terms must be cleared before public use. Full PDF and textual-location/OSM processing is connected in later stages. The full-file acceptance target is at least {limits.full_file_minimum.pdf_pages} pages and {limits.full_file_minimum.pdf_bytes.toLocaleString()} bytes per PDF. Current local caps are {limits.guest_daily_units} estimated compute units per guest per day and {limits.global_active_jobs} simultaneous jobs systemwide; these limits are provisional until measured.</p>
        <button type="button" disabled={busy} onClick={() => { void start(); }}>Start analysis</button>
      </>}
      {active && <>
        <p role="status">Analysis active · workspace {session.workspace_id}</p>
        <p>Time remaining: {Math.ceil(remaining / 60_000)} minutes (until {new Date(Math.min(Date.parse(session.expires_at), Date.parse(session.absolute_expires_at))).toLocaleString()}).</p>
        {remaining <= 30 * 60_000 && <p role="alert">This analysis expires soon. Download reports before it expires. Renewing can extend idle time, but never past the 24-hour limit.</p>}
        <p>Activity and background jobs do not extend this timer automatically. Renew only when you want more time.</p>
        <div className="session-actions">
          <button type="button" disabled={busy} onClick={() => { void renew(); }}>Renew session</button>
          <button type="button" disabled={busy} className="secondary" onClick={() => { void end(); }}>End and delete</button>
        </div>
      </>}
      {phase === 'unavailable' && <button type="button" onClick={() => { void check(); }}>Retry connection</button>}
      {message && <p role="alert">{message}</p>}
    </section>
    {active && <SessionContext.Provider value={session}>{children}</SessionContext.Provider>}
  </>;
}

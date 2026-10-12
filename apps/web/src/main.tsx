import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { paths } from './generated/bootstrap';

type BootstrapStatus = paths['/api/v1/bootstrap']['get']['responses'][200]['content']['application/json'];

function App() {
  const [status, setStatus] = useState<BootstrapStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/v1/bootstrap', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`API returned ${response.status}`);
        return response.json() as Promise<BootstrapStatus>;
      })
      .then(setStatus)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(String(reason));
      });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <h1>Resilience Twin</h1>
      <p>Local proof of concept bootstrap</p>
      <p role="status">{status ? `API ${status.status} (${status.schema_version})` : error ?? 'Connecting to API…'}</p>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);

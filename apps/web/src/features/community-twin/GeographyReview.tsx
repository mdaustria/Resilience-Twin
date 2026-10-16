import { useEffect, useState } from 'react';
import type { paths } from '../../../../../packages/client-generated/skeleton';
import { GeographyMap } from '../../components/map';

type GeographySnapshot = paths['/api/v1/local/geography/{case}']['get']['responses'][200]['content']['application/json'];
type PilotCase = 'qc' | 'guiguinto';

const points = [
  { id: 'training-pickup', label: 'Training pickup', x: 80, y: 60, included: true },
  { id: 'training-neighbor', label: 'Neighboring facility', x: 215, y: 55, included: false },
];

export function GeographyReview() {
  const [basemapAvailable, setBasemapAvailable] = useState(false);
  const [connectorReviewed, setConnectorReviewed] = useState(false);
  const [reviewCase, setReviewCase] = useState<'synthetic' | PilotCase>('synthetic');
  const [geography, setGeography] = useState<GeographySnapshot | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setGeography(null);
    setReviewed(false);
    setError(null);
    if (reviewCase === 'synthetic') return;
    void fetch(`/api/v1/local/geography/${reviewCase}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Geography unavailable (${response.status})`);
        return response.json() as Promise<GeographySnapshot>;
      })
      .then(setGeography)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'Geography unavailable'));
  }, [reviewCase]);

  async function confirmPilot() {
    if (!geography || reviewCase === 'synthetic') return;
    setError(null);
    try {
      const headers = { 'X-Fixture-Owner': 'fixture-a', 'X-Fixture-Case': reviewCase };
      const reviewResponse = await fetch('/api/v1/local/review', { headers });
      if (!reviewResponse.ok) throw new Error(`Review unavailable (${reviewResponse.status})`);
      const review = await reviewResponse.json() as { draft: { revision: number } };
      const response = await fetch(`/api/v1/local/geography/${reviewCase}/review`, {
        method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: review.draft.revision,
          expected_scope_digest: geography.scope_digest }),
      });
      if (!response.ok) throw new Error(`Geography review failed (${response.status})`);
      setReviewed(true);
      window.dispatchEvent(new Event('geography-reviewed'));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Geography review failed');
    }
  }

  const pilotPoints = geography?.area.connectors.map((connector) => {
    const polygon = geography.area.boundary_lon_lat;
    const west = Math.min(...polygon.map(([lon]) => lon));
    const east = Math.max(...polygon.map(([lon]) => lon));
    const south = Math.min(...polygon.map(([, lat]) => lat));
    const north = Math.max(...polygon.map(([, lat]) => lat));
    return { id: connector.id, label: connector.point_id,
      x: 30 + ((connector.longitude ?? west) - west) / (east - west) * 170,
      y: 100 - ((connector.latitude ?? south) - south) / (north - south) * 80,
      included: true };
  });
  return <section aria-label="Geography review" className="panel">
    <h2>Study area and access review</h2>
    <label htmlFor="geography-case">Geography case</label>
    <select id="geography-case" value={reviewCase}
      onChange={(event) => setReviewCase(event.target.value as 'synthetic' | PilotCase)}>
      <option value="synthetic">Synthetic training case</option>
      <option value="qc">Talayan-centered QC pilot</option>
      <option value="guiguinto">Poblacion-centered Guiguinto pilot</option>
    </select>
    {error && <p role="alert">{error}</p>}
    {reviewCase === 'synthetic' ? <>
    <p>Synthetic schematic only. Select a pilot case to review its pinned road extent.</p>
    <label><input type="checkbox" checked={basemapAvailable}
      onChange={(event) => setBasemapAvailable(event.target.checked)} /> Basemap available</label>
    <GeographyMap points={points} basemapAvailable={basemapAvailable} />
    <table><caption>Matching map table</caption><thead><tr><th scope="col">Place</th><th scope="col">Scope</th><th scope="col">Access</th></tr></thead>
      <tbody><tr><th scope="row">Training pickup</th><td>Included in schematic</td><td>{connectorReviewed ? 'Manually reviewed for training only' : 'Connector unresolved'}</td></tr>
        <tr><th scope="row">Neighboring facility</th><td>Excluded</td><td>Availability and permission unknown</td></tr></tbody></table>
    <label><input type="checkbox" checked={connectorReviewed}
      onChange={(event) => setConnectorReviewed(event.target.checked)} /> Review training connector</label>
    <p role="status">{connectorReviewed ? 'Training connector reviewed; real study area remains unresolved.' : 'Run readiness: unresolved connector and real study area.'}</p>
    </> : geography && <>
      <p>{geography.area.label}. This rectangle is a modeled cell, not a barangay boundary.</p>
      <p>OSM snapshot SHA-256: {geography.source_sha256}. Routing buffer: {geography.area.routing_buffer_m} m.</p>
      <label><input type="checkbox" checked={basemapAvailable}
        onChange={(event) => setBasemapAvailable(event.target.checked)} /> Basemap available</label>
      <GeographyMap points={pilotPoints ?? []} basemapAvailable={basemapAvailable} />
      <table><caption>Matching map table</caption><thead><tr>
        <th scope="col">Place</th><th scope="col">Scope</th><th scope="col">Access</th>
      </tr></thead><tbody>
        {geography.area.members.map((member) => <tr key={member.id}><th scope="row">{member.label}</th>
          <td>{member.included ? `Included: ${member.population} hypothetical people` : 'Excluded'}</td>
          <td>{member.reason}</td></tr>)}
        {geography.area.connectors.map((connector) => <tr key={connector.id}>
          <th scope="row">{connector.point_id}</th><td>Included anchor</td>
          <td>{connector.distance_m} m to OSM node {connector.road_node_id}; {connector.source}</td></tr>)}
      </tbody></table>
      <p>Reviewed road route: {geography.route_status}, {geography.route_seconds} s, {geography.route_distance_mm} mm.</p>
      <ul>{geography.area.cross_boundary_assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
      <p>Geography blockers: {geography.blockers.length ? geography.blockers.join('; ') : 'none under recorded assumptions'}.</p>
      <button type="button" onClick={() => void confirmPilot()} disabled={reviewed || geography.blockers.length > 0}>
        Confirm pilot scope and reset pending assumptions
      </button>
      <p role="status">{reviewed ? 'Pilot geography reviewed for this local case.'
        : 'Pilot geography awaits personal scenario review.'}</p>
    </>}
  </section>;
}

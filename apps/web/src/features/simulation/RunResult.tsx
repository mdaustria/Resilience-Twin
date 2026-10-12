import type { SkeletonResult } from '../../lib/skeletonClient';

export function RunResult({ result }: { result: SkeletonResult }) {
  return (
    <section aria-labelledby="result-heading" className="panel result">
      <p className="eyebrow">Live Simulation · Result</p>
      <h2 id="result-heading">Computed outcome</h2>
      <div className="metrics">
        <div><strong>{result.arrived_people.toLocaleString()}</strong><span>people arrived</span></div>
        <div><strong>{result.water_shortfall_ml.toLocaleString()} mL</strong><span>water shortfall</span></div>
      </div>
      <p>{result.unserved_people.toLocaleString()} people were not served. {result.water_sufficient_people.toLocaleString()} arrivals had sufficient water.</p>
      <p className="small">Source: {result.source_label}. Assumption: {result.assumption_label}.</p>
    </section>
  );
}

import type { SkeletonCase } from '../../lib/skeletonClient';

export function CaseReview({ caseData }: { caseData: SkeletonCase }) {
  return (
    <section aria-labelledby="review-heading" className="panel">
      <p className="eyebrow">Community Twin · Review</p>
      <h2 id="review-heading">Review the synthetic case</h2>
      <p>This local proof of concept uses a training fixture. It is not an assessment of a real plan.</p>
      <dl className="details">
        <div><dt>Source</dt><dd>{caseData.source_label}</dd></div>
        <div><dt>Assumption</dt><dd>{caseData.assumption_label}</dd></div>
        <div><dt>People</dt><dd>{caseData.cohort_people}</dd></div>
        <div><dt>Vehicle seats</dt><dd>{caseData.vehicle_seats}</dd></div>
        <div><dt>Shelter spaces</dt><dd>{caseData.shelter_spaces}</dd></div>
        <div><dt>Shelter water</dt><dd>{caseData.shelter_water_ml.toLocaleString()} mL</dd></div>
      </dl>
    </section>
  );
}

type Point = { id: string; label: string; x: number; y: number; included: boolean };

export function GeographyMap({ points, basemapAvailable }: {
  points: Point[]; basemapAvailable: boolean;
}) {
  return <div aria-label="Study area map" role="img">
    <svg viewBox="0 0 240 120" width="360" height="180" aria-hidden="true">
      <rect width="240" height="120" fill="#edf3f2" />
      <path d="M 30 20 L 200 20 L 200 100 L 30 100 Z" fill="none" stroke="#236259" strokeWidth="2" />
      {points.map((point) => <circle key={point.id} cx={point.x} cy={point.y} r="6"
        fill={point.included ? '#236259' : '#ad655b'} />)}
    </svg>
    <p>{basemapAvailable ? 'Local schematic overlay' : 'Basemap unavailable; schematic and table remain available.'}</p>
  </div>;
}

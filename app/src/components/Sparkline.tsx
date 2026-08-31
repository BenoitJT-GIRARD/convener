export function Sparkline({ values, height = 28, width = 120 }: {
  values: (number | null)[]; height?: number; width?: number;
}) {
  const v = values.map(n => n ?? 0);
  const max = Math.max(1, ...v);
  const step = width / Math.max(1, v.length - 1);
  const points = v.map((n, i) => `${i * step},${height - (n / max) * (height - 4) - 2}`).join(' ');
  return (
    <svg width={width} height={height} className="text-dominant">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

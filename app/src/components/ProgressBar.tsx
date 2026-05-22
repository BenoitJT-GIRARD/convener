export function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="w-full h-2 bg-border rounded-full overflow-hidden">
      <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
    </div>
  );
}

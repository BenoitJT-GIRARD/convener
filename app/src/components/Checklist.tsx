import { RUNBOOK } from '../data/runbook';

const WINDOW_LABEL = {
  'T-6w': '6 weeks before',
  'T-4w': '4 weeks before',
  'T-2w': '2 weeks before',
  'T-1w': '1 week before',
  'T-1d': 'The day before',
} as const;

export function Checklist({ progress, onToggle }: {
  progress: Record<string, boolean>;
  onToggle: (key: string, value: boolean) => void;
}) {
  const windows = ['T-6w','T-4w','T-2w','T-1w','T-1d'] as const;
  return (
    <div className="space-y-6">
      {windows.map(w => {
        const items = RUNBOOK.filter(s => s.window === w);
        if (items.length === 0) return null;
        return (
          <section key={w}>
            <h3 className="text-xs uppercase tracking-wider text-ink-muted mb-2">{w} — {WINDOW_LABEL[w]}</h3>
            <ul className="space-y-1">
              {items.map(s => (
                <li key={s.key} className="flex items-start gap-2">
                  <input
                    type="checkbox" checked={!!progress[s.key]}
                    onChange={e => onToggle(s.key, e.target.checked)}
                    className="mt-1 accent-primary"
                  />
                  <span className={progress[s.key] ? 'line-through text-ink-muted' : ''}>{s.label}</span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

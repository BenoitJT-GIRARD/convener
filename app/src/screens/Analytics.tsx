import { useData } from '../data/DataContext';
import { Sparkline } from '../components/Sparkline';
import { HandbookLink } from '../components/HandbookLink';
import type { VwsEvent } from '../data/types';

export function Analytics() {
  const { events, speakers, loading, error } = useData();
  if (loading) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;
  const past = events
    .filter(e => e.status !== 'upcoming')
    .sort((a, b) => a.date.localeCompare(b.date));

  const metrics = [
    { label: 'Registrations',      get: (e: VwsEvent) => e.metrics.registrations },
    { label: 'Live peak',          get: (e: VwsEvent) => e.metrics.live_peak },
    { label: 'YouTube views @30d', get: (e: VwsEvent) => e.metrics.youtube_views_30d },
    { label: 'Forum replies',      get: (e: VwsEvent) => e.metrics.forum_replies },
  ];

  const byCountry: Record<string, number> = {};
  past.forEach(e => {
    const sp = speakers.find(s => s.id === e.speaker_id);
    if (sp?.country) byCountry[sp.country] = (byCountry[sp.country] || 0) + 1;
  });

  return (
    <div className="max-w-3xl">
      <div className="flex items-baseline justify-between mb-6">
        <h1 className="font-serif text-3xl">Analytics</h1>
        <HandbookLink to="/governance/editorial-board/">season review</HandbookLink>
      </div>

      <h2 className="font-serif text-xl mb-3">Trends</h2>
      <div className="grid grid-cols-2 gap-4 mb-10">
        {metrics.map(m => {
          const values = past.map(m.get);
          const last = values[values.length - 1];
          return (
            <div key={m.label} className="p-3 bg-surface border border-border rounded-md">
              <div className="text-xs uppercase tracking-wider text-ink-muted">{m.label}</div>
              <div className="flex items-end justify-between mt-2">
                <span className="font-serif text-2xl">{last ?? '—'}</span>
                <Sparkline values={values} />
              </div>
            </div>
          );
        })}
      </div>

      <h2 className="font-serif text-xl mb-3">Past speakers by country</h2>
      {past.length === 0 && <p className="text-ink-muted text-sm">No past events yet.</p>}
      <ul className="space-y-1">
        {Object.entries(byCountry).sort(([,a],[,b])=>b-a).map(([c, n]) => (
          <li key={c} className="flex items-center gap-3">
            <span className="text-sm w-20">{c}</span>
            <div className="flex-1 h-3 bg-border rounded">
              <div className="h-full bg-primary rounded" style={{ width: `${(n / Math.max(1, past.length)) * 100}%` }} />
            </div>
            <span className="font-mono text-xs text-ink-muted">{n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

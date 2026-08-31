import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { SpeakerCard } from '../components/Card';
import { effectiveStatus, parisToday } from '../state/derived';
import { byUrgency, lateness } from '../state/sla';
import { LoadError } from '../components/LoadError';
import type { SpeakerStatus } from '../data/types';

const ACTIVE_COLUMNS: { key: SpeakerStatus; label: string }[] = [
  { key: 'lead', label: 'Leads' },
  { key: 'approved', label: 'Approved' },
  { key: 'invited', label: 'Invited' },
  { key: 'confirmed', label: 'Confirmed' },
  { key: 'scheduled', label: 'Scheduled' },
];

export function Pipeline() {
  const { speakers, loading, error, config } = useData();
  if (loading) return <p className="text-ink-muted">Reading the records from GitHub…</p>;
  if (error) return <LoadError message={error} />;
  const now = new Date();
  const today = parisToday();
  return (
    <div>
      <div className="flex items-baseline justify-between mb-8 flex-wrap gap-3">
        <div>
          <p className="text-xs font-bold tracking-[0.14em] uppercase text-accent mb-2 flex items-center gap-3">
            <span className="h-0.5 bg-accent w-8" />
            Active pipeline
          </p>
          <h1 className="font-display font-extrabold text-3xl uppercase tracking-tight">
            Pipeline
          </h1>
        </div>
        <Link
          to="/speakers/new"
          className="font-display font-bold tracking-widest uppercase text-xs bg-primary text-white border-2 border-primary px-4 py-2.5 hover:bg-primary-hover hover:border-primary-hover transition-colors"
        >
          + New speaker
        </Link>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-4">
        {ACTIVE_COLUMNS.map(col => {
          // Each column is ordered by how long its step has been waiting:
          // longest first, and records whose step has no applicable turnaround
          // time -- or no recorded day to count one from -- last, so they can
          // never push what is genuinely waiting off the top of the column.
          const items = speakers
            .filter(s => s.status === col.key)
            .map(s => ({ s, late: config ? lateness(s, config, today) : ({ state: 'none' } as const) }))
            .sort((a, b) => byUrgency(a.late, b.late));
          return (
            <div key={col.key} className="min-w-[240px] flex-1">
              <div className="flex items-baseline gap-2 mb-3 pb-2 border-b-2 border-ink">
                <span className="font-display font-extrabold text-xs uppercase tracking-[0.14em]">
                  {col.label}
                </span>
                <span className="font-mono text-xs text-ink-faint ml-auto">{items.length}</span>
              </div>
              <div className="flex flex-col gap-2">
                {items.map(({ s, late }) => (
                  <SpeakerCard
                    key={s.id}
                    s={s}
                    displayStatus={config ? effectiveStatus(s, config, now) : undefined}
                    lateness={late}
                  />
                ))}
                {items.length === 0 && (
                  <p className="text-xs text-ink-faint italic py-2">— empty</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-ink-muted mt-8 italic">
        Parked, declined, and past webinars live in{' '}
        <Link to="/archive" className="text-accent underline">Archive</Link>.
      </p>
    </div>
  );
}

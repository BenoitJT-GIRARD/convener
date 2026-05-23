import { useData } from '../data/DataContext';
import { SpeakerCard } from '../components/Card';
import type { SpeakerStatus } from '../data/types';

const ACTIVE_COLUMNS: { key: SpeakerStatus; label: string }[] = [
  { key: 'lead', label: 'Leads' },
  { key: 'approved', label: 'Approved' },
  { key: 'invited', label: 'Invited' },
  { key: 'confirmed', label: 'Confirmed' },
  { key: 'scheduled', label: 'Scheduled' },
];

const INACTIVE_COLUMNS: { key: SpeakerStatus; label: string }[] = [
  { key: 'parked', label: 'Parked' },
  { key: 'decline-board', label: 'Declined (board)' },
  { key: 'decline-speaker', label: 'Declined (speaker)' },
];

export function Pipeline() {
  const { speakers, loading, error } = useData();
  if (loading) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;
  return (
    <div>
      <h1 className="font-serif text-3xl mb-6">Pipeline</h1>
      <div className="flex gap-4 overflow-x-auto pb-4">
        {ACTIVE_COLUMNS.map(col => {
          const items = speakers.filter(s => s.status === col.key);
          return (
            <div key={col.key} className="min-w-[240px] flex-1">
              <div className="text-xs uppercase tracking-wider text-ink-muted mb-2">
                {col.label} <span className="text-ink-muted">· {items.length}</span>
              </div>
              <div className="flex flex-col gap-2">
                {items.map(s => (
                  <SpeakerCard key={s.id} s={s} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <details className="mt-8">
        <summary className="cursor-pointer text-sm text-ink-muted">Inactive columns</summary>
        <div className="flex gap-4 mt-4 overflow-x-auto pb-4">
          {INACTIVE_COLUMNS.map(col => {
            const items = speakers.filter(s => s.status === col.key);
            return (
              <div key={col.key} className="min-w-[240px] flex-1">
                <div className="text-xs uppercase tracking-wider text-ink-muted mb-2">
                  {col.label} <span className="text-ink-muted">· {items.length}</span>
                </div>
                <div className="flex flex-col gap-2">
                  {items.map(s => (
                    <SpeakerCard key={s.id} s={s} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
}

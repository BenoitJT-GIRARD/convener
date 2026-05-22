import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { SpeakerCard } from '../components/Card';
import { Button } from '../components/Button';
import type { SpeakerStatus } from '../data/types';

const COLUMNS: { key: SpeakerStatus; label: string }[] = [
  { key: 'lead', label: 'Leads' },
  { key: 'approved', label: 'Approved' },
  { key: 'invited', label: 'Invited' },
  { key: 'confirmed', label: 'Confirmed' },
  { key: 'scheduled', label: 'Scheduled' },
  { key: 'parking-lot', label: 'Parking Lot' },
  { key: 'declined', label: 'Declined' },
];

export function Pipeline() {
  const { speakers, loading, error } = useData();
  if (loading) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;
  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-serif text-3xl">Pipeline</h1>
        <Link to="/speakers/new"><Button>+ New speaker</Button></Link>
      </div>
      <div className="flex gap-4 overflow-x-auto pb-4">
        {COLUMNS.map(col => {
          const items = speakers.filter(s => s.status === col.key);
          return (
            <div key={col.key} className="min-w-[240px] flex-1">
              <div className="text-xs uppercase tracking-wider text-ink-muted mb-2">
                {col.label} <span className="text-ink-muted">· {items.length}</span>
              </div>
              <div className="flex flex-col gap-2">
                {items.map(s => <SpeakerCard key={s.id} s={s} />)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

import { Link } from 'react-router-dom';
import type { Speaker } from '../data/types';

export function SpeakerCard({ s }: { s: Speaker }) {
  const subtitle = s.title || s.affiliation;
  return (
    <Link
      to={`/speakers/${s.id}`}
      className="block p-3 rounded-md bg-surface border border-border hover:border-primary transition-colors"
    >
      <div className="font-medium text-sm">{s.name || '(no name)'}</div>
      {subtitle && <div className="text-xs text-ink-muted mt-1 line-clamp-2">{subtitle}</div>}
      <div className="flex justify-between mt-2 text-xs text-ink-muted">
        <span>{s.edition_code || s.host || '— no host'}</span>
        <span className="font-mono">{s.id}</span>
      </div>
    </Link>
  );
}

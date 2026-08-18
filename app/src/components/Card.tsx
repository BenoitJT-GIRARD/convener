import { Link } from 'react-router-dom';
import type { Speaker, SpeakerStatus } from '../data/types';

interface Props {
  s: Speaker;
  /** Derived status (see src/state/derived.ts), shown only when it differs
   *  from the column/section the card sits in -- filtering stays on the raw
   *  stored status, but the label should never lie about a talk that has
   *  already ended. Omit where the caller has no `Config` to derive it. */
  displayStatus?: SpeakerStatus;
}

export function SpeakerCard({ s, displayStatus }: Props) {
  const subtitle = s.title || s.affiliation;
  return (
    <Link
      to={`/speakers/${s.id}`}
      className="block p-3 rounded-md bg-surface border border-border hover:border-primary transition-colors"
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="font-medium text-sm">{s.name || '(no name)'}</div>
        {displayStatus && displayStatus !== s.status && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-accent shrink-0">
            now {displayStatus}
          </span>
        )}
      </div>
      {subtitle && <div className="text-xs text-ink-muted mt-1 line-clamp-2">{subtitle}</div>}
      <div className="flex justify-between mt-2 text-xs text-ink-muted">
        <span>{s.edition_code || s.host_1 || '— no host'}</span>
        <span className="font-mono">{s.id}</span>
      </div>
    </Link>
  );
}

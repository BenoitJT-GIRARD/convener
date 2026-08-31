import { Link } from 'react-router-dom';
import { overdueText, waitingSince, type Lateness } from '../state/sla';
import type { Speaker, SpeakerStatus } from '../data/types';

interface Props {
  s: Speaker;
  /** Derived status (see src/state/derived.ts), shown only when it differs
   *  from the column/section the card sits in -- filtering stays on the raw
   *  stored status, but the label should never lie about a talk that has
   *  already ended. Omit where the caller has no `Config` to derive it. */
  displayStatus?: SpeakerStatus;
  /** How long this record's current step has been waiting (src/state/sla.ts).
   *  Only the `overdue` arm draws anything: a step that is on time, or that has
   *  no applicable turnaround time, carries no day count for this card to
   *  render, so no "0 days overdue" is constructible here. */
  lateness?: Lateness;
}

export function SpeakerCard({ s, displayStatus, lateness }: Props) {
  const subtitle = s.title || s.affiliation;
  return (
    <Link
      to={`/speakers/${s.id}`}
      className="block p-3 rounded-md bg-surface border border-border hover:border-field transition-colors"
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="font-medium text-sm">{s.name || '(no name)'}</div>
        {displayStatus && displayStatus !== s.status && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-dominant shrink-0">
            now {displayStatus}
          </span>
        )}
      </div>
      {subtitle && <div className="text-xs text-ink-muted mt-1 line-clamp-2">{subtitle}</div>}
      {lateness?.state === 'overdue' && (
        // The step is the subject of both lines, and the second one names the
        // day the step has been waiting since. On this repository's data that
        // day is identical across the leads whose vote window was opened in
        // one backfill, which is how a reader can tell a bulk opening from
        // twenty-four separate slips.
        <div className="mt-1.5">
          <div className="text-xs font-medium text-danger">{overdueText(lateness)}</div>
          <div className="text-[10px] text-ink-faint">{waitingSince(lateness)}</div>
        </div>
      )}
      <div className="flex justify-between mt-2 text-xs text-ink-muted">
        <span>{s.edition_code || s.host_1 || '— no host'}</span>
        <span className="font-mono">{s.id}</span>
      </div>
    </Link>
  );
}

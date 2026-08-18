import { useState } from 'react';
import {
  canTransition,
  applyTransition,
  type Transition,
  type Role,
  type LockDatePayload,
  type OverridePayload,
} from '../state/transitions';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import { findOverlaps, nextEditionCode } from '../state/agenda';
import type { Speaker } from '../data/types';

interface Props {
  speaker: Speaker;
  role: Role;
}

export function ActionButtons({ speaker, role }: Props) {
  const { config, mutateSpeakers } = useData();
  const { login } = useAuth();
  const [busy, setBusy] = useState(false);

  const today = new Date().toISOString().slice(0, 10);
  const threshold = config?.vote_threshold ?? 3;

  async function fire(t: Transition, payload?: LockDatePayload | OverridePayload) {
    if (!login || !canTransition(speaker, t, role)) return;
    setBusy(true);
    try {
      await mutateSpeakers(
        current =>
          current.map(sp =>
            sp.id === speaker.id ? applyTransition(sp, t, login, threshold, today, payload) : sp,
          ),
        `data: ${speaker.id} → ${t}`,
      );
    } finally {
      setBusy(false);
    }
  }

  const btnCls = (variant: 'primary' | 'danger' | 'ghost') =>
    variant === 'danger'
      ? 'px-3 py-1.5 text-sm rounded border border-danger text-danger hover:bg-danger hover:text-white disabled:opacity-50'
      : variant === 'ghost'
        ? 'px-3 py-1.5 text-sm rounded border border-border text-ink-muted hover:text-ink disabled:opacity-50'
        : 'px-3 py-1.5 text-sm rounded bg-primary text-white hover:opacity-90 disabled:opacity-50';

  function btn(
    label: string,
    t: Transition,
    variant: 'primary' | 'danger' | 'ghost' = 'primary',
  ) {
    if (!canTransition(speaker, t, role)) return null;
    return (
      <button key={label} disabled={busy} onClick={() => fire(t)} className={btnCls(variant)}>
        {label}
      </button>
    );
  }

  const buttons: React.ReactNode[] = [];
  switch (speaker.status) {
    case 'lead':
      if (role === 'board') {
        const voted = login && speaker.selection.votes_for.includes(login);
        if (!voted) buttons.push(btn('Vote yes', 'lead-vote'));
        else buttons.push(btn('Withdraw vote', 'lead-vote-withdraw', 'ghost'));
        buttons.push(btn('Park', 'lead-park', 'ghost'));
        buttons.push(btn('Decline', 'lead-decline', 'danger'));
      } else {
        buttons.push(
          <span className="text-sm text-ink-muted" key="msg">
            Awaiting board vote ({speaker.selection.votes_for.length} / {threshold}).
          </span>,
        );
      }
      break;
    case 'approved': {
      const hostsSet = !!speaker.host_1 && !!speaker.host_2;
      if (!hostsSet) {
        buttons.push(
          <span className="text-sm text-ink-muted" key="msg">
            Assign Host 1 and Host 2 in the form below before sending the invitation.
          </span>,
        );
      } else {
        buttons.push(btn('Mark invitation sent →', 'send-invitation'));
      }
      break;
    }
    case 'invited':
      buttons.push(btn('Speaker accepted', 'invited-accept'));
      buttons.push(btn('Speaker declined', 'invited-decline', 'danger'));
      break;
    case 'confirmed':
      buttons.push(
        <LockDateForm
          key="lock"
          speaker={speaker}
          disabled={busy}
          onSubmit={(d, e, t) => fire('lock-date', { date: d, edition_code: e, time: t })}
        />,
      );
      break;
    case 'parked':
    case 'decline-board':
      if (role === 'board') buttons.push(btn('Reactivate', 'reactivate'));
      break;
    default:
      break;
  }
  return <div className="flex flex-wrap gap-2 items-center">{buttons}</div>;
}

function LockDateForm({
  speaker,
  onSubmit,
  disabled,
}: {
  speaker: Speaker;
  onSubmit: (date: string, edition: string, time: string) => void;
  disabled: boolean;
}) {
  const { speakers, config } = useData();
  const [date, setDate] = useState('');
  const [time, setTime] = useState('12:30');
  const [edition, setEdition] = useState('');
  const [err, setErr] = useState<string | null>(null);

  function suggestEdition() {
    if (!config) return;
    setEdition(nextEditionCode(speakers, config.vw_counter));
  }

  function attempt() {
    setErr(null);
    if (!date || !edition || !time || !config) return;
    const hits = findOverlaps(date, speakers, config.overlap_window_days, speaker.id);
    if (hits.length) {
      const h = hits[0];
      setErr(
        `Overlap: ${h.speaker.edition_code || h.speaker.id} is on ${h.speaker.date} (${h.daysApart}d apart). Choose another date.`,
      );
      return;
    }
    onSubmit(date, edition, time);
  }

  const titleMissing = !speaker.title || !speaker.abstract;
  const formIncomplete = !date || !edition || !time;
  const locked = disabled || formIncomplete || titleMissing;

  return (
    <div className="space-y-2 w-full">
      <div className="flex gap-2 items-center flex-wrap">
        <label className="flex items-center gap-1.5">
          <span className="text-xs font-mono uppercase text-ink-muted">Date</span>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className="px-2 py-1 text-sm" />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs font-mono uppercase text-ink-muted">Time (Paris)</span>
          <input
            type="time"
            value={time}
            onChange={e => setTime(e.target.value)}
            className="px-2 py-1 text-sm font-mono w-24"
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-xs font-mono uppercase text-ink-muted">№</span>
          <input
            type="text"
            placeholder="MRG-N"
            value={edition}
            onChange={e => setEdition(e.target.value)}
            className="px-2 py-1 text-sm font-mono w-20"
          />
        </label>
        <button onClick={suggestEdition} className="text-xs text-primary-hover underline" type="button">
          suggest
        </button>
        <button
          disabled={locked}
          onClick={attempt}
          className="px-3 py-1.5 text-sm font-display font-bold tracking-widest uppercase bg-primary text-white border-2 border-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed"
          type="button"
        >
          Lock date →
        </button>
      </div>
      {titleMissing && (
        <p className="text-xs text-danger italic">
          Title and abstract are required before locking the date. Fill them in the checklist above.
        </p>
      )}
      {err && <p className="text-danger text-xs">{err}</p>}
    </div>
  );
}

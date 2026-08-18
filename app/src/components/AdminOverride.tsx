import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import type { Speaker, SpeakerStatus, Gender } from '../data/types';

const ALL_STATUSES: SpeakerStatus[] = [
  'lead',
  'approved',
  'invited',
  'confirmed',
  'scheduled',
  'delivered',
  'archived',
  'parked',
  'decline-board',
  'decline-speaker',
];
const GENDERS: Gender[] = ['M', 'F', 'NB', 'undisclosed'];

/**
 * Fields this form's inputs actually write (see the `up`/`upMetrics` calls
 * below). Status, selection, runbook_progress, and links are edited by other
 * writers (ForceStatus, ActionButtons, the checklist, the archive metrics
 * editor) and must never be overwritten by this form's stale snapshot — see
 * `pickEdited`.
 */
const EDITABLE_FIELDS = [
  'name', 'gender', 'email', 'affiliation', 'country', 'title', 'abstract',
  'conflicts_of_interest', 'source', 'proposed_by', 'host_1', 'host_2',
  'edition_code', 'date', 'time', 'zoom_link', 'youtube_url', 'forum_thread',
  'notes', 'metrics',
] as const satisfies readonly (keyof Speaker)[];

/** Extracts only the fields this form edits, so a save can merge them onto a
 *  freshly-read record instead of overwriting fields other writers own. */
function pickEdited(draft: Speaker): Pick<Speaker, (typeof EDITABLE_FIELDS)[number]> {
  return Object.fromEntries(EDITABLE_FIELDS.map(k => [k, draft[k]])) as Pick<
    Speaker,
    (typeof EDITABLE_FIELDS)[number]
  >;
}

export function AdminOverride({ speaker }: { speaker: Speaker }) {
  return (
    <div className="space-y-10 mt-4">
      <EditFields speaker={speaker} />
      <ForceStatus speaker={speaker} />
      <DeleteSpeaker speaker={speaker} />
    </div>
  );
}

function L({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="font-display font-bold text-[11px] uppercase tracking-widest text-ink-muted">
        {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function EditFields({ speaker }: { speaker: Speaker }) {
  const { mutateSpeakers } = useData();
  const { login } = useAuth();
  const [draft, setDraft] = useState<Speaker>(speaker);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  function up<K extends keyof Speaker>(k: K, v: Speaker[K]) {
    setDraft(d => ({ ...d, [k]: v }));
    setSaved(false);
  }
  function upMetrics<K extends keyof Speaker['metrics']>(k: K, v: Speaker['metrics'][K]) {
    setDraft(d => ({ ...d, metrics: { ...d.metrics, [k]: v } }));
    setSaved(false);
  }

  async function save() {
    if (!login) return;
    setBusy(true);
    try {
      await mutateSpeakers(
        current => current.map(s => (s.id === draft.id ? { ...s, ...pickEdited(draft) } : s)),
        `data: ${draft.id} admin edit by ${login}`,
      );
      setSaved(true);
    } finally {
      setBusy(false);
    }
  }

  const input = 'w-full px-2 py-1.5 text-sm';
  return (
    <div>
      <h3 className="font-display font-bold uppercase tracking-widest text-xs text-ink mb-3">
        Edit fields
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <L label="Name">
          <input className={input} value={draft.name} onChange={e => up('name', e.target.value)} />
        </L>
        <L label="Gender">
          <select
            className={input}
            value={draft.gender}
            onChange={e => up('gender', e.target.value as Gender)}
          >
            {GENDERS.map(g => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </L>
        <L label="Email">
          <input
            className={input}
            type="email"
            value={draft.email}
            onChange={e => up('email', e.target.value)}
          />
        </L>
        <L label="Affiliation">
          <input className={input} value={draft.affiliation} onChange={e => up('affiliation', e.target.value)} />
        </L>
        <L label="Country">
          <input className={input} value={draft.country} onChange={e => up('country', e.target.value)} />
        </L>
        <L label="Source">
          <select
            className={input}
            value={draft.source}
            onChange={e => up('source', e.target.value as Speaker['source'])}
          >
            <option value="form">form</option>
            <option value="outreach">outreach</option>
            <option value="organizer">organizer</option>
          </select>
        </L>
        <L label="Proposed by">
          <input className={input} value={draft.proposed_by} onChange={e => up('proposed_by', e.target.value)} />
        </L>
        <L label="Host 1">
          <input className={input} value={draft.host_1} onChange={e => up('host_1', e.target.value)} />
        </L>
        <L label="Host 2">
          <input className={input} value={draft.host_2} onChange={e => up('host_2', e.target.value)} />
        </L>
        <L label="Edition code">
          <input
            className={`${input} font-mono`}
            value={draft.edition_code}
            onChange={e => up('edition_code', e.target.value)}
          />
        </L>
        <L label="Date (YYYY-MM-DD)">
          <input
            className={`${input} font-mono`}
            value={draft.date}
            onChange={e => up('date', e.target.value)}
            placeholder="YYYY-MM-DD"
          />
        </L>
        <L label="Time (HH:MM Paris)">
          <input
            className={`${input} font-mono`}
            value={draft.time}
            onChange={e => up('time', e.target.value)}
            placeholder="HH:MM"
          />
        </L>
        <L label="Zoom link">
          <input className={input} value={draft.zoom_link} onChange={e => up('zoom_link', e.target.value)} />
        </L>
        <L label="YouTube URL">
          <input className={input} value={draft.youtube_url} onChange={e => up('youtube_url', e.target.value)} />
        </L>
        <L label="Forum thread">
          <input className={input} value={draft.forum_thread} onChange={e => up('forum_thread', e.target.value)} />
        </L>
        <L label="Registrations">
          <input
            className={input}
            type="number"
            value={draft.metrics.registrations ?? ''}
            onChange={e =>
              upMetrics('registrations', e.target.value === '' ? null : Number(e.target.value))
            }
          />
        </L>
        <L label="Live peak">
          <input
            className={input}
            type="number"
            value={draft.metrics.live_peak ?? ''}
            onChange={e =>
              upMetrics('live_peak', e.target.value === '' ? null : Number(e.target.value))
            }
          />
        </L>
        <L label="YouTube views (30d)">
          <input
            className={input}
            type="number"
            value={draft.metrics.youtube_views_30d ?? ''}
            onChange={e =>
              upMetrics('youtube_views_30d', e.target.value === '' ? null : Number(e.target.value))
            }
          />
        </L>
        <L label="Forum replies">
          <input
            className={input}
            type="number"
            value={draft.metrics.forum_replies ?? ''}
            onChange={e =>
              upMetrics('forum_replies', e.target.value === '' ? null : Number(e.target.value))
            }
          />
        </L>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3">
        <L label="Title">
          <input className={input} value={draft.title} onChange={e => up('title', e.target.value)} />
        </L>
        <L label="Abstract">
          <textarea
            className={input}
            rows={3}
            value={draft.abstract}
            onChange={e => up('abstract', e.target.value)}
          />
        </L>
        <L label="Conflicts of interest">
          <textarea
            className={input}
            rows={2}
            value={draft.conflicts_of_interest}
            onChange={e => up('conflicts_of_interest', e.target.value)}
          />
        </L>
        <L label="Notes">
          <textarea
            className={input}
            rows={2}
            value={draft.notes}
            onChange={e => up('notes', e.target.value)}
          />
        </L>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={save}
          disabled={busy}
          className="font-display font-bold tracking-widest uppercase text-xs bg-ink text-white border-2 border-ink px-4 py-2 disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Save changes'}
        </button>
        {saved && <span className="text-xs text-primary-hover">✓ saved</span>}
      </div>
    </div>
  );
}

function ForceStatus({ speaker }: { speaker: Speaker }) {
  const { mutateSpeakers } = useData();
  const { login } = useAuth();
  const [target, setTarget] = useState<SpeakerStatus>(speaker.status);
  const [busy, setBusy] = useState(false);

  async function apply() {
    if (!login || target === speaker.status) return;
    setBusy(true);
    try {
      await mutateSpeakers(
        current => current.map(s => (s.id === speaker.id ? { ...s, status: target } : s)),
        `data: ${speaker.id} admin override status ${speaker.status}→${target} by ${login}`,
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h3 className="font-display font-bold uppercase tracking-widest text-xs text-ink mb-3">
        Force status
      </h3>
      <div className="flex gap-2 items-center flex-wrap">
        <select
          value={target}
          onChange={e => setTarget(e.target.value as SpeakerStatus)}
          className="px-2 py-1 text-sm"
        >
          {ALL_STATUSES.map(st => (
            <option key={st} value={st}>
              {st}
            </option>
          ))}
        </select>
        <button
          disabled={busy || target === speaker.status}
          onClick={apply}
          className="px-3 py-1.5 text-sm rounded border border-danger text-danger hover:bg-danger hover:text-white disabled:opacity-50"
        >
          Force status
        </button>
        <span className="text-xs text-ink-muted">Logged in commit message.</span>
      </div>
    </div>
  );
}

function DeleteSpeaker({ speaker }: { speaker: Speaker }) {
  const { mutateSpeakers } = useData();
  const { login } = useAuth();
  const nav = useNavigate();
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);
  const armed = typed === speaker.name && !busy;

  async function del() {
    if (!login || !armed) return;
    setBusy(true);
    try {
      await mutateSpeakers(
        current => current.filter(s => s.id !== speaker.id),
        `data: deleted ${speaker.id} (${speaker.name}) by ${login}`,
      );
      nav('/pipeline');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-2 border-danger p-4">
      <h3 className="font-display font-bold uppercase tracking-widest text-xs text-danger mb-3">
        Danger zone — delete speaker
      </h3>
      <p className="text-sm text-ink-muted mb-3">
        Removes the entry permanently from <code className="font-mono">data/speakers.yml</code>.
        The Git commit is the audit trail. Type the exact name{' '}
        <strong>{speaker.name}</strong> to confirm.
      </p>
      <div className="flex gap-2 items-center flex-wrap">
        <input
          type="text"
          value={typed}
          onChange={e => setTyped(e.target.value)}
          placeholder={speaker.name}
          className="px-2 py-1 text-sm font-mono flex-1 min-w-[16rem]"
        />
        <button
          disabled={!armed}
          onClick={del}
          className="font-display font-bold tracking-widest uppercase text-xs bg-danger text-white border-2 border-danger px-4 py-2 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? 'Deleting…' : 'Delete permanently'}
        </button>
      </div>
    </div>
  );
}

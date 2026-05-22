import { useParams, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useData } from '../data/DataContext';
import { Field } from '../components/Field';
import { Button } from '../components/Button';
import type { Speaker, SpeakerStatus } from '../data/types';

const STATUSES: SpeakerStatus[] = ['lead','approved','invited','confirmed','scheduled','parking-lot','declined'];

function emptySpeaker(): Speaker {
  return {
    id: '', name: '', status: 'lead', owner: '', email: '', affiliation: '', country: '',
    topic: '', source: 'organizer', proposed_by: '', links: [],
    selection: { votes_for: [], decided_on: '' },
    next_action: '', next_action_date: '', event_id: '', notes: '',
  };
}

function nextId(speakers: Speaker[]): string {
  const nums = speakers
    .map(s => /spk-(\d+)/.exec(s.id)?.[1])
    .filter(Boolean).map(n => parseInt(n!, 10));
  const max = nums.length ? Math.max(...nums) : 0;
  return `spk-${String(max + 1).padStart(3, '0')}`;
}

export function SpeakerPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { speakers, saveSpeakers } = useData();
  const isNew = id === 'new';
  const initial = isNew ? emptySpeaker() : speakers.find(s => s.id === id);
  const [draft, setDraft] = useState<Speaker | null>(initial ?? null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!isNew) setDraft(speakers.find(s => s.id === id) ?? null);
  }, [id, speakers, isNew]);

  if (!draft) return <p className="text-danger">Speaker not found.</p>;

  function up<K extends keyof Speaker>(k: K, v: Speaker[K]) {
    setDraft(d => d ? { ...d, [k]: v } : d);
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    try {
      let next: Speaker[];
      let toSave: Speaker;
      if (isNew) {
        toSave = { ...draft, id: nextId(speakers) };
        next = [...speakers, toSave];
      } else {
        toSave = draft;
        next = speakers.map(s => s.id === toSave.id ? toSave : s);
      }
      await saveSpeakers(next, `data: update speaker ${toSave.id}`);
      nav(`/speakers/${toSave.id}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="font-serif text-3xl mb-2">{isNew ? 'New speaker' : draft.name || '(unnamed)'}</h1>
      <p className="text-xs text-ink-muted font-mono mb-6">{draft.id || '(new id at save)'}</p>

      <Field label="Name" value={draft.name} onChange={v => up('name', v)} />
      <Field label="Email" value={draft.email} type="email" onChange={v => up('email', v)} />
      <Field label="Affiliation" value={draft.affiliation} onChange={v => up('affiliation', v)} />
      <Field label="Country" value={draft.country} onChange={v => up('country', v)} />
      <Field label="Topic" value={draft.topic} as="textarea" onChange={v => up('topic', v)} />
      <label className="block mb-3">
        <span className="text-xs uppercase tracking-wider text-ink-muted">Status</span>
        <select className="mt-1 w-full px-3 py-2 border border-border rounded-md bg-surface text-sm"
          value={draft.status} onChange={e => up('status', e.target.value as SpeakerStatus)}>
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <Field label="Owner" value={draft.owner} onChange={v => up('owner', v)} />
      <Field label="Next action" value={draft.next_action} onChange={v => up('next_action', v)} />
      <Field label="Next action date (YYYY-MM-DD)" value={draft.next_action_date} onChange={v => up('next_action_date', v)} />
      <Field label="Notes" value={draft.notes} as="textarea" onChange={v => up('notes', v)} />

      <div className="mt-6 flex gap-3">
        <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
        <Button variant="outline" onClick={() => nav(-1)}>Cancel</Button>
      </div>
    </div>
  );
}

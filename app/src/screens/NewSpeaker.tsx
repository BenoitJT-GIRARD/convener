import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { useAuth } from '../auth/AuthContext';
import type { Speaker, Gender } from '../data/types';

function nextSpeakerId(speakers: Speaker[]): string {
  const nums = speakers
    .map(s => /^spk-(\d+)/.exec(s.id)?.[1])
    .filter((n): n is string => !!n)
    .map(n => parseInt(n, 10));
  const max = nums.length ? Math.max(...nums) : 0;
  return `spk-${String(max + 1).padStart(3, '0')}`;
}

export function NewSpeaker() {
  const { speakers, mutateSpeakers } = useData();
  const { login } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);

  const [form, setForm] = useState({
    name: '',
    email: '',
    affiliation: '',
    country: '',
    gender: 'undisclosed' as Gender,
    title: '',
    abstract: '',
    links: '',
    notes: '',
    conflicts_of_interest: '',
    source: 'organizer' as Speaker['source'],
    proposed_by: login ?? '',
  });

  function up<K extends keyof typeof form>(k: K, v: (typeof form)[K]) {
    setForm(f => ({ ...f, [k]: v }));
  }

  function onSource(v: Speaker['source']) {
    setForm(f => ({
      ...f,
      source: v,
      proposed_by: v === 'organizer' ? login ?? f.proposed_by : f.proposed_by,
    }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name.trim() || !login) return;
    setBusy(true);
    try {
      const id = nextSpeakerId(speakers);
      const lead: Speaker = {
        id,
        name: form.name.trim(),
        gender: form.gender,
        email: form.email.trim(),
        affiliation: form.affiliation.trim(),
        country: form.country.trim(),
        title: form.title.trim(),
        abstract: form.abstract.trim(),
        conflicts_of_interest: form.conflicts_of_interest.trim(),
        source: form.source,
        proposed_by: form.proposed_by.trim(),
        links: form.links.split(/[\s,]+/).map(s => s.trim()).filter(Boolean),
        host_1: '',
        host_2: '',
        status: 'lead',
        selection: { votes_for: [], decided_on: '' },
        edition_code: '',
        date: '',
        time: '',
        zoom_link: '',
        youtube_url: '',
        forum_thread: '',
        runbook_progress: {},
        metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
        notes: form.notes.trim(),
      };
      await mutateSpeakers(current => [...current, lead], `data: add lead ${id} (${lead.name})`);
      nav(`/speakers/${id}`);
    } finally {
      setBusy(false);
    }
  }

  const inputCls = 'w-full px-3 py-2 text-sm';

  return (
    <div className="max-w-xl">
      <h1 className="font-serif text-3xl mb-2">New speaker</h1>
      <p className="text-ink-muted text-sm mb-6">
        Add a lead manually. The Tally public form does the same with{' '}
        <code className="font-mono">source: 'form'</code>. The board will vote next.
      </p>

      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">Name *</span>
          <input
            type="text"
            value={form.name}
            onChange={e => up('name', e.target.value)}
            required
            className={`${inputCls} mt-1`}
            autoFocus
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-ink-muted">Source</span>
            <select
              className={`${inputCls} mt-1`}
              value={form.source}
              onChange={e => onSource(e.target.value as Speaker['source'])}
            >
              <option value="organizer">organizer (added by team member)</option>
              <option value="outreach">outreach (contacted by email)</option>
              <option value="form">form (Tally public submission)</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-ink-muted">Proposed by</span>
            <input
              type="text"
              value={form.proposed_by}
              onChange={e => up('proposed_by', e.target.value)}
              className={`${inputCls} mt-1`}
              placeholder={form.source === 'organizer' ? 'your login' : 'name'}
            />
          </label>
        </div>

        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">Email</span>
          <input
            type="email"
            value={form.email}
            onChange={e => up('email', e.target.value)}
            className={`${inputCls} mt-1`}
          />
        </label>

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-ink-muted">Affiliation</span>
            <input
              type="text"
              value={form.affiliation}
              onChange={e => up('affiliation', e.target.value)}
              className={`${inputCls} mt-1`}
            />
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-ink-muted">Country</span>
            <input
              type="text"
              value={form.country}
              onChange={e => up('country', e.target.value)}
              className={`${inputCls} mt-1`}
            />
          </label>
        </div>

        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">Gender</span>
          <select
            value={form.gender}
            onChange={e => up('gender', e.target.value as Gender)}
            className={`${inputCls} mt-1`}
          >
            <option value="undisclosed">undisclosed</option>
            <option value="F">F</option>
            <option value="M">M</option>
            <option value="NB">NB</option>
          </select>
        </label>

        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">
            Title (preliminary)
          </span>
          <input
            type="text"
            value={form.title}
            onChange={e => up('title', e.target.value)}
            className={`${inputCls} mt-1`}
          />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">Abstract</span>
          <textarea
            value={form.abstract}
            onChange={e => up('abstract', e.target.value)}
            rows={4}
            className={`${inputCls} mt-1 font-sans`}
          />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">
            Conflicts of interest
          </span>
          <textarea
            value={form.conflicts_of_interest}
            onChange={e => up('conflicts_of_interest', e.target.value)}
            rows={2}
            className={`${inputCls} mt-1 font-sans`}
            placeholder="Disclosed conflicts (visible to all)"
          />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">
            Links (comma or whitespace separated)
          </span>
          <input
            type="text"
            value={form.links}
            onChange={e => up('links', e.target.value)}
            placeholder="https://orcid.org/..., https://lab.example/..."
            className={`${inputCls} mt-1 font-mono text-xs`}
          />
        </label>
        <label className="block">
          <span className="text-xs uppercase tracking-wider text-ink-muted">Notes</span>
          <textarea
            value={form.notes}
            onChange={e => up('notes', e.target.value)}
            rows={3}
            className={`${inputCls} mt-1`}
          />
        </label>

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={busy || !form.name.trim()}
            className="px-4 py-2 bg-primary text-white border-2 border-primary hover:bg-primary-hover disabled:opacity-50 font-display font-bold tracking-widest uppercase text-sm"
          >
            {busy ? 'Creating…' : 'Create lead'}
          </button>
          <button
            type="button"
            onClick={() => nav(-1)}
            className="px-4 py-2 border-2 border-border text-ink-muted hover:text-ink font-display font-bold tracking-widest uppercase text-sm"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

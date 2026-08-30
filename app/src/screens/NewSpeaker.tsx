import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { assignLead } from '../state/board';
import { parisToday } from '../state/derived';
import { useAuth } from '../auth/AuthContext';
import { formatDecision, identifier } from '../state/decisions';
import { CAREER_STAGES } from '../data/types';
import type { Speaker, Gender, CareerStage } from '../data/types';

function nextSpeakerId(speakers: Speaker[]): string {
  const nums = speakers
    .map(s => /^spk-(\d+)/.exec(s.id)?.[1])
    .filter((n): n is string => !!n)
    .map(n => parseInt(n, 10));
  const max = nums.length ? Math.max(...nums) : 0;
  return `spk-${String(max + 1).padStart(3, '0')}`;
}

export function NewSpeaker() {
  const { config, mutateSpeakers } = useData();
  const { login } = useAuth();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);

  const [form, setForm] = useState({
    name: '',
    email: '',
    affiliation: '',
    country: '',
    gender: 'undisclosed' as Gender,
    career_stage: 'undisclosed' as CareerStage,
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
    if (!form.name.trim() || !login || !config) return;
    setBusy(true);
    const today = parisToday();
    try {
      const fields: Omit<Speaker, 'id'> = {
        name: form.name.trim(),
        gender: form.gender,
        career_stage: form.career_stage,
        email: form.email.trim(),
        affiliation: form.affiliation.trim(),
        country: form.country.trim(),
        // Written as answers, not left out. This form does not ask for the
        // portrait, the biography or the handle -- they are asked for once
        // the speaker is invited, not while the board is still deciding --
        // and `''` says "none on record" where an absent key would say the
        // file is incomplete.
        photo_url: '',
        bio: '',
        linkedin: '',
        title: form.title.trim(),
        abstract: form.abstract.trim(),
        seed_questions: '',
        conflicts_of_interest: form.conflicts_of_interest.trim(),
        source: form.source,
        proposed_by: form.proposed_by.trim(),
        // Who submitted the lead, not who will handle it. The owner is
        // computed inside the transform below and overwrites this placeholder;
        // `proposed_by` is never touched by that, because it is the only
        // record of who has to be told if the board declines.
        assigned_to: '',
        links: form.links.split(/[\s,]+/).map(s => s.trim()).filter(Boolean),
        host_1: '',
        host_2: '',
        status: 'lead',
        // The vote window runs from `opened_on` (see tools/convener_ops/maintenance/sweep.py), and
        // it opens the day the lead is recorded.
        selection: { ballots: [], opened_on: today, decided_on: '' },
        publication: {
          consent: 'pending',
          approved_by: '',
          approved_on: '',
          objections: [],
          outcome: '',
        },
        edition_code: '',
        // No slot has been put to anyone yet: the board has not voted.
        candidate_dates: [],
        date: '',
        time: '',
        zoom_link: '',
        youtube_url: '',
        forum_thread: '',
        // A new record starts with the survey off, the same "absent means
        // off" default the migration gives every existing speaker --
        // turning it on is a deliberate, later edit.
        survey_enabled: false,
        runbook_progress: {},
        // Nobody is down for any line, which is where every record starts and
        // where most lines stay: an item with no owner is the hosts'.
        checklist: {},
        metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
        notes: form.notes.trim(),
      };
      // The id must be computed from `current` inside the transform — not
      // from a `speakers` list snapshotted at render time — so a retry
      // against a fresher read (someone else added a speaker meanwhile)
      // picks a fresh id instead of colliding with theirs. `assignedId`
      // records whatever id the transform that actually got written used,
      // for navigation below.
      let assignedId = '';
      const ok = await mutateSpeakers(
        current => {
          assignedId = nextSpeakerId(current);
          // A lead created here gets an owner by the same rotation the public
          // form uses (`tools/convener_ops/journey/proposal.py::to_lead`), so the two intake
          // routes cannot produce differently-owned leads. Computed from
          // `current`, since the rotation counts the open leads that exist at
          // write time -- not the ones a stale render remembered. `config` is
          // read from the load cycle instead: the board lives in config.yml and
          // `mutate` operates on speakers.yml alone, and board composition
          // changes a handful of times a year. `assignLead` returns '' when no
          // member is available, which leaves the lead unassigned rather than
          // failing the creation.
          const owner = assignLead(current, config, today);
          return [...current, { ...fields, id: assignedId, assigned_to: owner }];
        },
        // The subject is a function of what is about to be written, because
        // that is the only moment `assignedId` is the id that actually got
        // saved. It names that id and not the researcher: their full name is
        // on this form, and `data: add lead Jane Doe` -- which is what stood
        // here -- would put it in a subject line nothing rewrites and every
        // watcher is mailed. That is the defect `state/decisions.ts` exists
        // to make unconstructible, so the line is written through the
        // grammar like every other act.
        () =>
          formatDecision({
            kind: 'speaker-create',
            entity: identifier(assignedId),
            actor: identifier(login),
          }),
      );
      if (ok) nav(`/speakers/${assignedId}`);
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

        <div className="grid grid-cols-2 gap-3">
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
            <span className="text-xs uppercase tracking-wider text-ink-muted">Career stage</span>
            <select
              value={form.career_stage}
              onChange={e => up('career_stage', e.target.value as CareerStage)}
              className={`${inputCls} mt-1`}
            >
              {CAREER_STAGES.map(stage => (
                <option key={stage} value={stage}>
                  {stage}
                </option>
              ))}
            </select>
          </label>
        </div>

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

        {/* Submitting waits for `config`: the owner of a new lead comes from
            the board in config.yml, and creating the lead before that file has
            arrived would write an unowned lead for no better reason than the
            volunteer being quick off the mark. */}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={busy || !config || !form.name.trim()}
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

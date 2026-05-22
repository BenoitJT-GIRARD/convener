import { useParams } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useData } from '../data/DataContext';
import { Checklist } from '../components/Checklist';
import { ProgressBar } from '../components/ProgressBar';
import { Field } from '../components/Field';
import { HandbookLink } from '../components/HandbookLink';
import { computeProgress } from '../data/runbook';
import type { VwsEvent } from '../data/types';

export function EventPage() {
  const { id } = useParams();
  const { events, speakers, saveEvents } = useData();
  const ev = events.find(e => e.id === id);
  const [draft, setDraft] = useState<VwsEvent | null>(ev ?? null);

  useEffect(() => { setDraft(events.find(e => e.id === id) ?? null); }, [id, events]);

  if (!draft) return <p className="text-danger">Event not found.</p>;
  const speaker = speakers.find(s => s.id === draft.speaker_id);
  const progress = draft.runbook_progress ?? {};
  const { done, total, pct } = computeProgress(progress);

  async function toggle(key: string, value: boolean) {
    if (!draft) return;
    const next = { ...draft, runbook_progress: { ...progress, [key]: value } };
    setDraft(next);
    await saveEvents(events.map(e => e.id === next.id ? next : e),
      `data: ${next.id} step ${key} ${value ? 'done' : 'undone'}`);
  }

  async function setField<K extends keyof VwsEvent>(k: K, v: VwsEvent[K]) {
    if (!draft) return;
    const next = { ...draft, [k]: v };
    setDraft(next);
    await saveEvents(events.map(e => e.id === next.id ? next : e),
      `data: ${next.id} update ${String(k)}`);
  }

  return (
    <div className="max-w-3xl">
      <p className="text-xs text-ink-muted font-mono mb-1">{draft.id}</p>
      <h1 className="font-serif text-3xl">{draft.title || '(no title)'}</h1>
      <p className="text-ink-muted mt-1">
        {speaker?.name || '(speaker?)'} · {draft.date || '(date?)'} · {draft.status}
      </p>

      <div className="my-6">
        <div className="flex justify-between text-sm mb-1">
          <span>Preparation</span>
          <span className="font-mono">{done} / {total} · {pct}%</span>
        </div>
        <ProgressBar pct={pct} />
      </div>

      <div className="flex items-baseline justify-between mt-8 mb-4">
        <h2 className="font-serif text-xl">Countdown</h2>
        <HandbookLink to="/workflow/2-preparation/">full T-minus runbook</HandbookLink>
      </div>
      <Checklist progress={progress} onToggle={toggle} />

      <h2 className="font-serif text-xl mt-10 mb-4">Details</h2>
      <Field label="Title" value={draft.title} onChange={v => setField('title', v)} />
      <Field label="Date (YYYY-MM-DD)" value={draft.date} onChange={v => setField('date', v)} />
      <Field label="Zoom link" value={draft.zoom_link} onChange={v => setField('zoom_link', v)} />
      <Field label="YouTube URL" value={draft.youtube_url} onChange={v => setField('youtube_url', v)} />
      <Field label="Forum thread" value={draft.forum_thread} onChange={v => setField('forum_thread', v)} />

      <div className="flex items-baseline justify-between mt-10 mb-4">
        <h2 className="font-serif text-xl">Metrics</h2>
        <HandbookLink to="/workflow/4-after/">after the webinar</HandbookLink>
      </div>
      <Field label="Registrations" value={String(draft.metrics.registrations ?? '')}
        onChange={v => setField('metrics', { ...draft.metrics, registrations: v ? parseInt(v) : null })} />
      <Field label="Live peak" value={String(draft.metrics.live_peak ?? '')}
        onChange={v => setField('metrics', { ...draft.metrics, live_peak: v ? parseInt(v) : null })} />
      <Field label="YouTube views @30d" value={String(draft.metrics.youtube_views_30d ?? '')}
        onChange={v => setField('metrics', { ...draft.metrics, youtube_views_30d: v ? parseInt(v) : null })} />
      <Field label="Forum replies" value={String(draft.metrics.forum_replies ?? '')}
        onChange={v => setField('metrics', { ...draft.metrics, forum_replies: v ? parseInt(v) : null })} />
    </div>
  );
}

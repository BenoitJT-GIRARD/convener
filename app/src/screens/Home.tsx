import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { computeProgress } from '../data/runbook';
import { voteState } from '../data/voting';
import { ProgressBar } from '../components/ProgressBar';
import { HandbookLink } from '../components/HandbookLink';

const BOARD_SIZE = 6;

export function Home() {
  const { speakers, events, loading, error } = useData();
  if (loading) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;
  const today = new Date().toISOString().slice(0, 10);

  if (speakers.length === 0 && events.length === 0) {
    return (
      <div className="max-w-xl mx-auto mt-16">
        <div className="rounded-md bg-surface border border-border p-8 shadow-card">
          <h1 className="font-serif text-2xl mb-3">Welcome.</h1>
          <p className="text-ink-muted mb-4">
            As speakers and events are added to the series, they will appear here.
          </p>
          <p>
            <HandbookLink to="/start-here/first-webinar/">handbook · your first webinar</HandbookLink>
          </p>
        </div>
      </div>
    );
  }

  const upcoming = events
    .filter(e => e.status === 'upcoming' || (e.date && e.date >= today))
    .sort((a, b) => a.date.localeCompare(b.date));

  const openVotes = speakers.filter(s => s.status === 'lead');
  const overdue = speakers.filter(s => s.next_action_date && s.next_action_date < today);

  return (
    <div className="max-w-3xl">
      <div className="flex items-baseline justify-between mb-8">
        <h1 className="font-serif text-3xl">Dashboard</h1>
        <HandbookLink to="/start-here/">handbook · start here</HandbookLink>
      </div>

      <section className="mb-10">
        <h2 className="font-serif text-xl mb-3">Upcoming</h2>
        {upcoming.length === 0 && <p className="text-ink-muted text-sm">No upcoming webinars.</p>}
        <ul className="space-y-3">
          {upcoming.map(ev => {
            const sp = speakers.find(s => s.id === ev.speaker_id);
            const { pct, done, total } = computeProgress(ev.runbook_progress);
            return (
              <li key={ev.id}>
                <Link to={`/events/${ev.id}`} className="block p-3 rounded-md bg-surface border border-border hover:border-primary">
                  <div className="flex justify-between">
                    <div>
                      <div className="font-medium">{ev.title || '(no title)'}</div>
                      <div className="text-xs text-ink-muted mt-1">{sp?.name} · {ev.date}</div>
                    </div>
                    <div className="font-mono text-xs text-ink-muted">{ev.id}</div>
                  </div>
                  <div className="mt-2">
                    <ProgressBar pct={pct} />
                    <div className="text-xs text-ink-muted mt-1">{done} / {total} steps</div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="mb-10">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="font-serif text-xl">Open votes</h2>
          <HandbookLink to="/governance/editorial-board/">how votes work</HandbookLink>
        </div>
        {openVotes.length === 0 && <p className="text-ink-muted text-sm">No leads awaiting a vote.</p>}
        <ul className="space-y-2">
          {openVotes.map(s => {
            const v = voteState(s.selection.votes_for, BOARD_SIZE);
            return (
              <li key={s.id}>
                <Link to={`/speakers/${s.id}`} className="flex justify-between p-3 rounded-md bg-surface border border-border hover:border-primary">
                  <div>
                    <div className="font-medium">{s.name || '(no name)'}</div>
                    <div className="text-xs text-ink-muted">{s.topic}</div>
                  </div>
                  <div className="font-mono text-xs">{v.count} / {v.threshold}</div>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <h2 className="font-serif text-xl mb-3">Overdue</h2>
        {overdue.length === 0 && <p className="text-ink-muted text-sm">Nothing overdue.</p>}
        <ul className="space-y-2">
          {overdue.map(s => (
            <li key={s.id}>
              <Link to={`/speakers/${s.id}`} className="flex justify-between p-3 rounded-md bg-surface border border-border hover:border-primary">
                <div>
                  <div className="font-medium">{s.name}</div>
                  <div className="text-xs text-ink-muted">{s.next_action}</div>
                </div>
                <div className="font-mono text-xs text-danger">{s.next_action_date}</div>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

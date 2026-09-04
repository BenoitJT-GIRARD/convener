import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import { ARCHIVE_GROUPS, type ArchiveGroup } from '../state/agenda';
import { effectiveStatus } from '../state/derived';
import { viewCountLabel } from '../state/phases';
import { dataEdit, identifier } from '../state/decisions';
import { LoadError } from '../components/LoadError';
import type { Config, Speaker } from '../data/types';

export function Archive() {
  const { speakers, loading, error, config } = useData();
  const [q, setQ] = useState('');
  const [active, setActive] = useState<ArchiveGroup['key'] | 'all'>('all');

  const grouped = useMemo(() => {
    const matches = (s: Speaker) => {
      if (!q) return true;
      const hay = (s.name + ' ' + s.title + ' ' + s.affiliation + ' ' + s.country).toLowerCase();
      return hay.includes(q.toLowerCase());
    };
    const result: Record<ArchiveGroup['key'], Speaker[]> = {
      past: [],
      parked: [],
      'declined-board': [],
      'declined-speaker': [],
    };
    for (const s of speakers) {
      for (const c of ARCHIVE_GROUPS) {
        if (c.statuses.includes(s.status) && matches(s)) {
          result[c.key].push(s);
          break;
        }
      }
    }
    for (const c of ARCHIVE_GROUPS) {
      result[c.key].sort((a, b) =>
        c.sortDesc ? b.date.localeCompare(a.date) : a.name.localeCompare(b.name),
      );
    }
    return result;
  }, [speakers, q]);

  if (loading) return <p className="text-ink-muted">Reading the records from GitHub…</p>;
  if (error) return <LoadError message={error} />;

  const visible = active === 'all' ? ARCHIVE_GROUPS : ARCHIVE_GROUPS.filter(c => c.key === active);
  const total = visible.reduce((n, c) => n + grouped[c.key].length, 0);

  return (
    <div>
      <div className="mb-8">
        <p className="text-xs font-bold tracking-[0.14em] uppercase text-dominant mb-2 flex items-center gap-3">
          <span className="h-0.5 bg-dominant w-8" />
          History
        </p>
        <h1 className="font-display font-extrabold text-3xl uppercase tracking-tight">Archive</h1>
        <p className="text-ink-muted text-sm mt-3">
          What is closed. Anything still owing something — booked, or delivered and not yet
          wrapped up — is on the Agenda until it is archived.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-8 pb-6 border-b border-border">
        <input
          type="search"
          placeholder="Search by name, title, affiliation, country…"
          value={q}
          onChange={e => setQ(e.target.value)}
          className="flex-1 min-w-[16rem] px-3 py-2 text-sm"
        />
        <div className="flex flex-wrap gap-1">
          <FilterChip active={active === 'all'} onClick={() => setActive('all')}>
            All
          </FilterChip>
          {ARCHIVE_GROUPS.map(c => (
            <FilterChip
              key={c.key}
              active={active === c.key}
              onClick={() => setActive(c.key)}
            >
              {c.label} <span className="font-mono ml-1">{grouped[c.key].length}</span>
            </FilterChip>
          ))}
        </div>
        <p className="font-mono text-xs text-ink-faint ml-auto whitespace-nowrap">
          {total} {total === 1 ? 'entry' : 'entries'}
        </p>
      </div>

      {visible.map(c => (
        <CategorySection key={c.key} category={c} speakers={grouped[c.key]} config={config} />
      ))}
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`font-display font-bold text-[11px] tracking-widest uppercase px-3 py-1.5 border-2 transition-colors ${
        active
          ? 'bg-dominant text-white border-dominant'
          : 'bg-transparent text-ink-muted border-border hover:border-dominant hover:text-dominant'
      }`}
    >
      {children}
    </button>
  );
}

function CategorySection({
  category,
  speakers,
  config,
}: {
  category: ArchiveGroup;
  speakers: Speaker[];
  config: Config | null;
}) {
  return (
    <section className="mb-10">
      <header className="flex items-baseline gap-3 mb-4">
        <span className="font-mono text-xs text-dominant">{category.num}</span>
        <h2 className="font-display font-extrabold text-xs uppercase tracking-[0.16em] text-ink">
          {category.label}
        </h2>
        <span className="text-xs text-ink-muted italic">{category.hint}</span>
        <span className="ml-auto font-mono text-xs text-ink-faint tracking-wider">
          {speakers.length} {speakers.length === 1 ? 'entry' : 'entries'}
        </span>
      </header>

      {speakers.length === 0 ? (
        <p className="text-ink-muted text-sm pl-7 italic">Nothing here.</p>
      ) : (
        <ol className="divide-y divide-border border-y border-border">
          {speakers.map(s => (
            <ArchiveRow key={s.id} speaker={s} category={category} config={config} />
          ))}
        </ol>
      )}
    </section>
  );
}

function ArchiveRow({
  speaker: s,
  category,
  config,
}: {
  speaker: Speaker;
  category: ArchiveGroup;
  config: Config | null;
}) {
  const [editing, setEditing] = useState(false);
  const showMetricsEdit =
    category.key === 'past' &&
    s.status === 'archived' &&
    (s.metrics.youtube_views_30d === null ||
      s.metrics.forum_replies === null ||
      !s.youtube_url ||
      !s.forum_thread);
  // Filtering into this category is (deliberately) on the raw stored
  // status; the label shown for it is not -- see effectiveStatus.
  const displayStatus = config ? effectiveStatus(s, config, new Date()) : s.status;
  return (
    <li>
      <div className="grid grid-cols-[7rem_1fr_auto] gap-4 items-center py-3 px-2 hover:bg-field-tint transition-colors">
        <Link
          to={`/speakers/${s.id}`}
          className="font-mono text-xs text-dominant uppercase tracking-wider truncate no-underline"
        >
          {s.edition_code || s.id}
        </Link>
        <div className="min-w-0">
          <Link to={`/speakers/${s.id}`} className="block min-w-0 no-underline">
            <p className="font-medium text-sm text-ink truncate">{s.title || s.name}</p>
            <p className="text-xs text-ink-muted truncate">
              <strong className="font-semibold">{s.name}</strong>
              {s.affiliation && ` · ${s.affiliation}`}
              {s.country && ` · ${s.country}`}
            </p>
          </Link>
        </div>
        <div className="text-right flex items-center justify-end gap-3">
          {displayStatus !== s.status && (
            <span className="font-mono text-[10px] uppercase tracking-wider text-dominant shrink-0">
              now {displayStatus}
            </span>
          )}
          {category.key === 'past' && s.date ? (
            <span className="font-mono text-xs text-ink-muted">
              {s.date.replace(/-/g, ' / ')}
            </span>
          ) : s.notes ? (
            <span className="font-mono text-[11px] text-ink-faint italic line-clamp-1 max-w-[20ch]">
              {s.notes.slice(0, 60)}
            </span>
          ) : null}
          {showMetricsEdit && (
            <button
              onClick={() => setEditing(!editing)}
              className="font-display font-bold text-[10px] tracking-widest uppercase text-field-text border border-border px-2 py-0.5 hover:bg-paper-soft"
            >
              {editing ? 'Hide' : 'Edit metrics'}
            </button>
          )}
        </div>
      </div>
      {editing && <ArchiveMetricsEdit speaker={s} />}
    </li>
  );
}

function ArchiveMetricsEdit({ speaker }: { speaker: Speaker }) {
  const { mutateSpeakers, config } = useData();
  const [yt30, setYt30] = useState<string | number>(speaker.metrics.youtube_views_30d ?? '');
  const [fr, setFr] = useState<string | number>(speaker.metrics.forum_replies ?? '');
  const [ytUrl, setYtUrl] = useState(speaker.youtube_url);
  const [forum, setForum] = useState(speaker.forum_thread);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const ok = await mutateSpeakers(
        current =>
          current.map(s =>
            s.id === speaker.id
              ? {
                  ...s,
                  youtube_url: ytUrl,
                  forum_thread: forum,
                  metrics: {
                    ...s.metrics,
                    youtube_views_30d: yt30 === '' ? null : Number(yt30),
                    forum_replies: fr === '' ? null : Number(fr),
                  },
                }
              : s,
          ),
        // Bookkeeping, not a decision: the numbers are read off elsewhere
        // and written down here, and nothing about a person is said.
        dataEdit(identifier(speaker.id), { part: 'post-archive-metrics' }),
      );
      // A failure is surfaced via the saveError banner (see Layout) -- never
      // report success here unless the write actually went through.
      setSaved(ok);
    } finally {
      setBusy(false);
    }
  }

  const input = 'w-full px-2 py-1.5 text-sm';
  return (
    <div className="ml-[7.25rem] mr-2 my-2 p-3 bg-surface border border-border grid grid-cols-1 md:grid-cols-2 gap-3">
      <label className="block">
        <span className="font-display font-bold text-[11px] uppercase tracking-widest text-ink-muted">
          YouTube URL
        </span>
        <input className={`${input} mt-1`} value={ytUrl} onChange={e => setYtUrl(e.target.value)} />
      </label>
      <label className="block">
        <span className="font-display font-bold text-[11px] uppercase tracking-widest text-ink-muted">
          {config ? viewCountLabel(config) : 'Video views'}
        </span>
        <input
          className={`${input} mt-1`}
          type="number"
          value={yt30}
          onChange={e => setYt30(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="font-display font-bold text-[11px] uppercase tracking-widest text-ink-muted">
          Forum thread URL
        </span>
        <input
          className={`${input} mt-1`}
          value={forum}
          onChange={e => setForum(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="font-display font-bold text-[11px] uppercase tracking-widest text-ink-muted">
          Forum replies
        </span>
        <input
          className={`${input} mt-1`}
          type="number"
          value={fr}
          onChange={e => setFr(e.target.value)}
        />
      </label>
      <div className="md:col-span-2 flex gap-3 items-center">
        <button
          onClick={save}
          disabled={busy}
          className="font-display font-bold tracking-widest uppercase text-xs bg-ink text-white border-2 border-ink px-3 py-1.5 disabled:opacity-50"
        >
          {busy ? 'Saving…' : 'Save metrics'}
        </button>
        {saved && <span className="text-xs text-field-text">✓ saved</span>}
      </div>
    </div>
  );
}

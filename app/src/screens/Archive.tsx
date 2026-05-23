import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useData } from '../data/DataContext';
import type { Speaker, SpeakerStatus } from '../data/types';

type Category = {
  key: 'past' | 'parked' | 'declined-board' | 'declined-speaker';
  num: string;
  label: string;
  hint: string;
  statuses: SpeakerStatus[];
  sortDesc: boolean;
};

const CATEGORIES: Category[] = [
  {
    key: 'past',
    num: '01',
    label: 'Past webinars',
    hint: 'Delivered, wrapped, archived',
    statuses: ['delivered', 'wrapped', 'archived'],
    sortDesc: true,
  },
  {
    key: 'parked',
    num: '02',
    label: 'Parked',
    hint: 'Set aside by the board — can be reactivated',
    statuses: ['parked'],
    sortDesc: false,
  },
  {
    key: 'declined-board',
    num: '03',
    label: 'Declined (board)',
    hint: 'The board chose not to invite',
    statuses: ['decline-board'],
    sortDesc: false,
  },
  {
    key: 'declined-speaker',
    num: '04',
    label: 'Declined (speaker)',
    hint: 'Speaker turned down the invitation',
    statuses: ['decline-speaker'],
    sortDesc: false,
  },
];

export function Archive() {
  const { speakers, loading, error } = useData();
  const [q, setQ] = useState('');
  const [active, setActive] = useState<Category['key'] | 'all'>('all');

  const grouped = useMemo(() => {
    const matches = (s: Speaker) => {
      if (!q) return true;
      const hay = (s.name + ' ' + s.title + ' ' + s.affiliation + ' ' + s.country).toLowerCase();
      return hay.includes(q.toLowerCase());
    };
    const result: Record<Category['key'], Speaker[]> = {
      past: [], parked: [], 'declined-board': [], 'declined-speaker': [],
    };
    for (const s of speakers) {
      for (const c of CATEGORIES) {
        if (c.statuses.includes(s.status) && matches(s)) {
          result[c.key].push(s);
          break;
        }
      }
    }
    for (const c of CATEGORIES) {
      result[c.key].sort((a, b) =>
        c.sortDesc ? b.date.localeCompare(a.date) : a.name.localeCompare(b.name),
      );
    }
    return result;
  }, [speakers, q]);

  if (loading) return <p className="text-ink-muted">Loading…</p>;
  if (error) return <p className="text-danger">Error: {error}</p>;

  const visible = active === 'all' ? CATEGORIES : CATEGORIES.filter(c => c.key === active);
  const total = visible.reduce((n, c) => n + grouped[c.key].length, 0);

  return (
    <div>
      <div className="mb-8">
        <p className="text-xs font-bold tracking-[0.14em] uppercase text-accent mb-2 flex items-center gap-3">
          <span className="h-0.5 bg-accent w-8" />
          History
        </p>
        <h1 className="font-display font-extrabold text-3xl uppercase tracking-tight">
          Archive
        </h1>
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
          {CATEGORIES.map(c => (
            <FilterChip
              key={c.key}
              active={active === c.key}
              onClick={() => setActive(c.key)}
            >
              {c.label}{' '}
              <span className="font-mono opacity-70 ml-1">{grouped[c.key].length}</span>
            </FilterChip>
          ))}
        </div>
        <p className="font-mono text-xs text-ink-faint ml-auto whitespace-nowrap">
          {total} {total === 1 ? 'entry' : 'entries'}
        </p>
      </div>

      {visible.map(c => (
        <CategorySection key={c.key} category={c} speakers={grouped[c.key]} />
      ))}
    </div>
  );
}

function FilterChip({
  active, onClick, children,
}: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`font-display font-bold text-[11px] tracking-widest uppercase px-3 py-1.5 border-2 transition-colors ${
        active
          ? 'bg-accent text-white border-accent'
          : 'bg-transparent text-ink-muted border-border hover:border-accent hover:text-accent'
      }`}
    >
      {children}
    </button>
  );
}

function CategorySection({ category, speakers }: { category: Category; speakers: Speaker[] }) {
  return (
    <section className="mb-10">
      <header className="flex items-baseline gap-3 mb-4">
        <span className="font-mono text-xs text-accent">{category.num}</span>
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
            <ArchiveRow key={s.id} speaker={s} category={category} />
          ))}
        </ol>
      )}
    </section>
  );
}

function ArchiveRow({ speaker: s, category }: { speaker: Speaker; category: Category }) {
  return (
    <li>
      <Link
        to={`/speakers/${s.id}`}
        className="grid grid-cols-[7rem_1fr_auto] gap-4 items-center py-3 px-2 hover:bg-primary-soft transition-colors"
      >
        <span className="font-mono text-xs text-accent uppercase tracking-wider truncate">
          {s.edition_code || s.id}
        </span>
        <div className="min-w-0">
          <p className="font-medium text-sm text-ink truncate">
            {s.title || s.name}
          </p>
          <p className="text-xs text-ink-muted truncate">
            <strong className="font-semibold">{s.name}</strong>
            {s.affiliation && ` · ${s.affiliation}`}
            {s.country && ` · ${s.country}`}
          </p>
        </div>
        <div className="text-right">
          {category.key === 'past' && s.date ? (
            <span className="font-mono text-xs text-ink-muted">{s.date.replace(/-/g, ' / ')}</span>
          ) : s.notes ? (
            <span className="font-mono text-[11px] text-ink-faint italic line-clamp-1 max-w-[20ch]">
              {s.notes.slice(0, 60)}
            </span>
          ) : (
            <span className="font-mono text-[11px] text-ink-faint">View →</span>
          )}
        </div>
      </Link>
    </li>
  );
}

import { NavLink } from 'react-router-dom';

const LINKS = [
  { to: '/', label: 'Inbox' },
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/agenda', label: 'Agenda' },
  { to: '/archive', label: 'Archive' },
  { to: '/board', label: 'Board' },
  { to: '/diversity', label: 'Diversity' },
  { to: '/consent', label: 'Consent' },
  { to: '/handbook', label: 'Handbook' },
  { to: '/templates', label: 'Templates' },
  { to: '/settings', label: 'Settings' },
];

export function TopTabs() {
  return (
    <nav className="flex gap-1 border-b border-border mb-6">
      {LINKS.map(l => (
        <NavLink
          key={l.to}
          to={l.to}
          end={l.to === '/'}
          className={({ isActive }) =>
            `px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              isActive
                ? 'border-field-text text-field-text'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}

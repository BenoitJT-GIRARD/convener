import { NavLink } from 'react-router-dom';

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/analytics', label: 'Analytics' },
];

export function TopTabs() {
  return (
    <nav className="flex gap-1 border-b border-border mb-6">
      {links.map(l => (
        <NavLink key={l.to} to={l.to} end
          className={({ isActive }) =>
            `px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              isActive
                ? 'border-primary text-primary'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}>
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}

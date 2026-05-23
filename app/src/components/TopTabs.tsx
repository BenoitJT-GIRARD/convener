import { NavLink } from 'react-router-dom';

const links = [
  { to: '/', label: 'Home' },
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/analytics', label: 'Analytics' },
];

export function TopTabs() {
  return (
    <nav className="flex gap-1 border-b border-border pb-2 mb-6">
      {links.map(l => (
        <NavLink key={l.to} to={l.to} end
          className={({ isActive }) =>
            `px-3 py-1.5 rounded-md text-sm font-medium ${
              isActive ? 'bg-primary text-paper' : 'text-ink-muted hover:bg-paper'
            }`}>
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}

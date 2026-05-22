import { NavLink } from 'react-router-dom';

const links = [
  { to: '/', label: 'Home' },
  { to: '/pipeline', label: 'Pipeline' },
  { to: '/analytics', label: 'Analytics' },
];

export function Nav() {
  return (
    <nav className="flex flex-col gap-1 p-4 border-r border-border bg-surface w-56 min-h-screen">
      <div className="font-serif text-lg mb-4">TEC · Workshop Series</div>
      {links.map(l => (
        <NavLink
          key={l.to}
          to={l.to}
          end
          className={({ isActive }) =>
            `px-3 py-2 rounded-md text-sm ${
              isActive ? 'bg-paper text-primary font-medium' : 'hover:bg-paper text-ink-muted'
            }`
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  );
}

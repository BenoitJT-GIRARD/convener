import { useState } from 'react';
import { InlineContent } from '../content/InlineContent';

const SECTIONS = [
  { key: 'handbook/overview', label: 'Overview' },
  { key: 'handbook/glossary', label: 'Glossary' },
  { key: 'handbook/roles', label: 'Roles' },
  { key: 'handbook/first-webinar', label: 'Your first webinar' },
  { key: 'handbook/workflow-overview', label: 'Workflow overview' },
  { key: 'handbook/sourcing', label: '1 · Finding & validating speakers' },
  { key: 'handbook/preparation', label: '2 · Preparing the webinar' },
  { key: 'handbook/hosting', label: '3 · Hosting day' },
  { key: 'handbook/after', label: '4 · After the webinar' },
  { key: 'governance/editorial-line', label: 'Editorial line' },
  { key: 'governance/editorial-board', label: 'The editorial board' },
  { key: 'governance/board-rules', label: "The Board's rules" },
  { key: 'governance/selection-criteria', label: 'How we validate speakers' },
  { key: 'governance/conflict-of-interest', label: 'Conflicts of interest' },
  { key: 'governance/decisions', label: 'Decision log' },
  { key: 'handbook/workspace', label: 'The workspace' },
  { key: 'handbook/tools', label: 'Tools & access' },
  { key: 'handbook/contacts', label: 'Contacts' },
  { key: 'handbook/schema', label: 'Data schema' },
];

export function Handbook() {
  const [active, setActive] = useState<string>(SECTIONS[0].key);
  return (
    <div className="flex gap-6">
      <nav className="w-64 shrink-0 sticky top-4 self-start">
        <ul className="space-y-1 text-sm">
          {SECTIONS.map(s => (
            <li key={s.key}>
              <button
                onClick={() => setActive(s.key)}
                className={`w-full text-left px-2 py-1 rounded ${
                  active === s.key
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                {s.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="flex-1 min-w-0">
        <InlineContent contentKey={active} variant="page" />
      </div>
    </div>
  );
}

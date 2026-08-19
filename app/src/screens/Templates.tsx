import { useState } from 'react';
import { InlineContent } from '../content/InlineContent';

const TEMPLATES = [
  { key: 'toolkit/emails/invitation', label: 'Invitation email' },
  { key: 'toolkit/emails/talk-details', label: 'Talk details email' },
  { key: 'toolkit/emails/zoom-request', label: 'Zoom request' },
  { key: 'toolkit/emails/reminder', label: 'Reminder email' },
  { key: 'toolkit/emails/thank-you', label: 'Thank-you email' },
  { key: 'toolkit/emails/consent-request', label: 'Recording consent request' },
  { key: 'toolkit/emails/outreach-sourcing', label: 'Outreach sourcing' },
  { key: 'toolkit/emails/registration-confirmation', label: 'Registration confirmation' },
  { key: 'toolkit/emails/decision-declined', label: 'Decision: declined' },
  { key: 'toolkit/emails/decision-parked', label: 'Decision: parked' },
  { key: 'toolkit/forum-post-announce', label: 'Forum: announcement' },
  { key: 'toolkit/forum-post-summary', label: 'Forum: summary' },
  { key: 'toolkit/linkedin-post', label: 'LinkedIn post' },
  { key: 'toolkit/intro-scripts', label: 'Intro scripts' },
];

export function Templates() {
  const [active, setActive] = useState<string>(TEMPLATES[0].key);
  return (
    <div className="flex gap-6">
      <nav className="w-64 shrink-0 sticky top-4 self-start">
        <ul className="space-y-1 text-sm">
          {TEMPLATES.map(t => (
            <li key={t.key}>
              <button
                onClick={() => setActive(t.key)}
                className={`w-full text-left px-2 py-1 rounded ${
                  active === t.key
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                {t.label}
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

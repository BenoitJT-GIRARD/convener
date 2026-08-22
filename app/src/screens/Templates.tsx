import { useState } from 'react';
import { InlineContent } from '../content/InlineContent';

/** Every template, in the order of the journey they belong to: a volunteer
 *  who opens this screen is usually looking for the next message to send, not
 *  for one they can already name. */
const TEMPLATES = [
  { key: 'toolkit/emails/proposal-received', label: 'Proposal received' },
  { key: 'toolkit/emails/invitation', label: 'Invitation email' },
  { key: 'toolkit/emails/talk-details', label: 'Talk details email' },
  { key: 'toolkit/emails/promotion-starting', label: 'Promotion starting' },
  { key: 'toolkit/emails/reminder', label: 'Reminder email' },
  { key: 'toolkit/emails/thank-you', label: 'Thank-you email' },
  { key: 'toolkit/emails/consent-request', label: 'Recording consent request' },
  { key: 'toolkit/emails/video-online', label: 'Video online' },
  { key: 'toolkit/emails/outreach-sourcing', label: 'Outreach sourcing' },
  { key: 'toolkit/emails/registration-confirmation', label: 'Registration confirmation' },
  { key: 'toolkit/emails/decision-declined', label: 'Decision: declined' },
  { key: 'toolkit/emails/decision-parked', label: 'Decision: parked' },
  { key: 'toolkit/forum-post-announce', label: 'Forum: announcement' },
  { key: 'toolkit/forum-post-summary', label: 'Forum: summary' },
  { key: 'toolkit/linkedin-post', label: 'LinkedIn post' },
  { key: 'toolkit/mailing-list-announce', label: 'Mailing list / newsletter' },
  { key: 'toolkit/recording-announce', label: 'Recording announcement' },
  { key: 'toolkit/intro-scripts', label: 'Intro scripts' },
  { key: 'toolkit/run-of-show', label: 'Run of show' },
  { key: 'toolkit/slides/presentation-template', label: 'Slide template' },
  { key: 'toolkit/visual-kit', label: 'Visual kit' },
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

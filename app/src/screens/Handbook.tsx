import { useEffect } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { InlineContent } from '../content/InlineContent';
import { CONTENT_REGISTRY } from '../content/registry';

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
  { key: 'governance/data-protection-record', label: 'Data protection record' },
  {
    key: 'governance/candidate-data-protection',
    label: 'Data protection record — speaker candidates',
  },
  { key: 'handbook/workspace', label: 'The workspace' },
  { key: 'handbook/tools', label: 'Tools & access' },
  { key: 'handbook/contacts', label: 'Contacts' },
  { key: 'engineering/schema', label: 'Data schema' },
];

/** The page this screen opens on when the address names none. */
const DEFAULT_SECTION = SECTIONS[0].key;

/**
 * The handbook, as a page of the cockpit with an address of its own.
 *
 * Which page is being read used to be `useState` here, which made this
 * screen the one part of the cockpit nothing could link to: every
 * cross-reference the handbook writes had to resolve to the markdown file
 * instead, outside the application (`content/fetch.ts::handbookUrl`). The
 * page is a route now -- `#/handbook/<content key>`, the key exactly as
 * `CONTENT_REGISTRY` spells it, slashes included -- so a link inside a
 * rendered page reaches another rendered page, the browser's own Back
 * button works between them, and a volunteer can send somebody the
 * address of what they are reading.
 *
 * Any registered key, not only the ones the rail lists. The rail is the
 * volunteer's own reading order and it is deliberately shorter than the
 * registry -- nobody browses the decision records front to back -- but a
 * link into one of them still has to land on a page rather than on a
 * file, so the route renders whatever the registry holds and the rail
 * simply shows nothing selected.
 */
export function Handbook() {
  const { '*': fromRoute } = useParams();
  const { hash } = useLocation();
  const requested = fromRoute && fromRoute !== '' ? fromRoute : DEFAULT_SECTION;
  const active = requested in CONTENT_REGISTRY ? requested : DEFAULT_SECTION;

  // The one thing a fragment can still be asked for once the route itself
  // lives in one: a section of the page being opened
  // (`conflict-of-interest.md` links to a heading of the run of show).
  // `InlineContent` gives every heading of a page-variant render the
  // anchor `content/transclude.ts::slugify` computes, which is GitHub's
  // own, so the anchor written in the prose is the anchor rendered here.
  useEffect(() => {
    if (!hash) return;
    const target = document.getElementById(hash.slice(1));
    if (target) target.scrollIntoView();
  }, [hash, active]);

  return (
    <div className="flex gap-6">
      <nav className="w-64 shrink-0 sticky top-4 self-start">
        <ul className="space-y-1 text-sm">
          {SECTIONS.map(s => (
            <li key={s.key}>
              <Link
                to={`/handbook/${s.key}`}
                className={`block w-full text-left px-2 py-1 rounded no-underline ${
                  active === s.key
                    ? 'bg-field/10 text-field-text font-medium'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                {s.label}
              </Link>
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

/**
 * Every tab this workspace has, in the order it shows them.
 *
 * A module of its own rather than a constant beside the component that
 * draws it: `docs/handbook/the-workspace.md` is where a volunteer reads
 * what each tab answers, and that page had been left describing nine of
 * ten -- the one it omitted being Settings, the screen whose whole
 * difficulty is that a reader cannot tell from it what it is for.
 * `app/tests/content/workspace-tabs.test.ts` holds the page against this
 * list, and a list exported from `TopTabs.tsx` would be a second export
 * from a file of components (`react-refresh/only-export-components`).
 */
export interface Tab {
  to: string;
  label: string;
}

export const TABS: readonly Tab[] = [
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

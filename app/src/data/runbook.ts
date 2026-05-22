export interface RunbookStep {
  key: string;
  window: 'T-6w' | 'T-4w' | 'T-2w' | 'T-1w' | 'T-1d';
  label: string;
}

export const RUNBOOK: readonly RunbookStep[] = [
  { key: 'both-hosts',    window: 'T-6w', label: 'Both Event Hosts signed up' },
  { key: 'invitation',    window: 'T-6w', label: 'Invitation sent to speaker' },
  { key: 'talk-details',  window: 'T-6w', label: 'Talk details collected (title, abstract, bio)' },
  { key: 'zoom-link',     window: 'T-6w', label: 'Zoom link + recording requested' },
  { key: 'access',        window: 'T-6w', label: 'Canva and LinkedIn access in place' },
  { key: 'visuals',       window: 'T-4w', label: 'Visuals + flyer made in Canva' },
  { key: 'linkedin',      window: 'T-4w', label: 'LinkedIn post published' },
  { key: 'forum-announce',window: 'T-4w', label: 'Forum announcement + discussion seeded' },
  { key: 'seed-questions',window: 'T-2w', label: 'Seeded a question or two on the forum' },
  { key: 'reminder',      window: 'T-1w', label: 'Reminder sent to speaker' },
  { key: 'plan-day',      window: 'T-1w', label: 'Plan for the day agreed between hosts' },
  { key: 'final-reminder',window: 'T-1d', label: 'Final reminder + registration link check' },
] as const;

export function computeProgress(map: Record<string, boolean> = {}) {
  const total = RUNBOOK.length;
  const done = RUNBOOK.filter(s => map[s.key]).length;
  return { done, total, pct: Math.round((done / total) * 100) };
}

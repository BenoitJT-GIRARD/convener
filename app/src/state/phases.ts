import type { SpeakerStatus } from '../data/types';

export interface RunbookItem {
  /** unique key persisted in speaker.runbook_progress, e.g. "approved/hosts-decided" */
  key: string;
  label: string;
  /** if true, completing this item is a gate towards the next phase */
  gate: boolean;
  /** for scheduled phase: days before event when this item becomes due */
  window?: number;
  /** content registry lookup key (Phase E) */
  contentKey?: string;
}

export interface PhaseDef {
  status: SpeakerStatus;
  label: string;
  items: RunbookItem[];
  /** transitions automatically when all gate items are checked */
  autoAdvance?: SpeakerStatus;
}

export const PHASES: PhaseDef[] = [
  {
    status: 'lead',
    label: 'Lead — awaiting board review',
    items: [
      {
        key: 'lead/research-speaker',
        label: 'Read selection criteria before voting',
        gate: false,
        contentKey: 'governance/selection-criteria',
      },
    ],
  },
  {
    status: 'approved',
    label: 'Approved — prepare invitation',
    items: [
      { key: 'approved/hosts-decided', label: 'Host + 2 co-hosts assigned', gate: true },
      {
        key: 'approved/invitation-sent',
        label: 'Invitation email sent',
        gate: true,
        contentKey: 'toolkit/emails/invitation',
      },
    ],
    autoAdvance: 'invited',
  },
  {
    status: 'invited',
    label: 'Invited — waiting for reply',
    items: [
      {
        key: 'invited/response-logged',
        label: 'Speaker reply logged (accepted or declined)',
        gate: true,
      },
    ],
    // transition handled by accept/decline buttons explicitly
  },
  {
    status: 'confirmed',
    label: 'Confirmed — schedule a date',
    items: [
      {
        key: 'confirmed/collect-abstract',
        label: 'Collect title + abstract from speaker',
        gate: false,
        contentKey: 'toolkit/emails/talk-details',
      },
      {
        key: 'confirmed/date-locked',
        label: 'Date locked with anti-overlap check',
        gate: true,
      },
    ],
    // transition handled by lock-date button explicitly
  },
  {
    status: 'scheduled',
    label: 'Scheduled — runbook',
    items: [
      { key: 'scheduled/T-30/visuals', label: 'Visuals + flyer made', gate: false, window: 30 },
      {
        key: 'scheduled/T-21/linkedin',
        label: 'LinkedIn post published',
        gate: false,
        window: 21,
        contentKey: 'toolkit/linkedin-post',
      },
      {
        key: 'scheduled/T-14/zoom-link',
        label: 'Zoom link from operations',
        gate: false,
        window: 14,
        contentKey: 'toolkit/emails/zoom-request',
      },
      {
        key: 'scheduled/T-14/access-setup',
        label: 'Canva + LinkedIn access in place',
        gate: false,
        window: 14,
      },
      {
        key: 'scheduled/T-7/forum-announce',
        label: 'Forum announcement seeded',
        gate: false,
        window: 7,
        contentKey: 'toolkit/forum-post-announce',
      },
      {
        key: 'scheduled/T-7/seed-questions',
        label: 'Seeded a question on the forum',
        gate: false,
        window: 7,
      },
      {
        key: 'scheduled/T-3/reminder',
        label: 'Reminder sent to speaker',
        gate: false,
        window: 3,
        contentKey: 'toolkit/emails/reminder',
      },
      {
        key: 'scheduled/T-3/plan-day',
        label: 'Plan for the day agreed between hosts',
        gate: false,
        window: 3,
      },
      {
        key: 'scheduled/T-1/final-reminder',
        label: 'Final reminder + registration check',
        gate: false,
        window: 1,
      },
    ],
    // auto-deliver handled on date pass (DataContext sweep)
  },
  {
    status: 'delivered',
    label: 'Delivered — wrap-up',
    items: [
      { key: 'delivered/youtube', label: 'Recording uploaded to YouTube', gate: true },
      {
        key: 'delivered/forum-summary',
        label: 'Forum summary posted',
        gate: true,
        contentKey: 'toolkit/forum-post-summary',
      },
      {
        key: 'delivered/thank-you',
        label: 'Thank-you email sent to speaker',
        gate: true,
        contentKey: 'toolkit/emails/thank-you',
      },
    ],
    autoAdvance: 'wrapped',
  },
  {
    status: 'wrapped',
    label: 'Wrapped — 30-day window',
    items: [
      {
        key: 'wrapped/metrics-30d',
        label: 'Fill metrics: registrations, peak, YouTube 30d, forum replies',
        gate: false,
      },
    ],
  },
];

export function phaseOf(status: SpeakerStatus): PhaseDef | undefined {
  return PHASES.find(p => p.status === status);
}

export function gatesComplete(phase: PhaseDef, progress: Record<string, boolean>): boolean {
  const gates = phase.items.filter(i => i.gate);
  if (gates.length === 0) return false;
  return gates.every(g => progress[g.key]);
}

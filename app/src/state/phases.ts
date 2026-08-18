import type { SpeakerStatus, Speaker } from '../data/types';

export type ItemForm = 'content' | 'field' | 'checkbox' | 'button-group';

export type FieldKey =
  | 'host_1'
  | 'host_2'
  | 'title'
  | 'abstract'
  | 'registrations'
  | 'live_peak'
  | 'youtube_views_30d'
  | 'forum_replies'
  | 'youtube_url'
  | 'forum_thread';

export interface RunbookItem {
  key: string;
  form: ItemForm;
  label: string;
  required?: boolean;
  contentKey?: string;
  window?: number;
  fieldKey?: FieldKey;
}

export interface PhaseDef {
  status: SpeakerStatus;
  label: string;
  items: RunbookItem[];
}

export const PHASES: PhaseDef[] = [
  {
    status: 'lead',
    label: 'Lead — awaiting board review',
    items: [
      {
        key: 'lead/selection-criteria',
        form: 'content',
        label: 'Selection criteria',
        contentKey: 'governance/selection-criteria',
      },
    ],
  },
  {
    status: 'approved',
    label: 'Approved — prepare invitation',
    items: [
      { key: 'approved/host_1', form: 'field', fieldKey: 'host_1', label: 'Host 1', required: true },
      { key: 'approved/host_2', form: 'field', fieldKey: 'host_2', label: 'Host 2', required: true },
      {
        key: 'approved/invitation-email',
        form: 'content',
        label: 'Invitation email',
        contentKey: 'toolkit/emails/invitation',
      },
    ],
  },
  {
    status: 'invited',
    label: 'Invited — waiting for reply',
    items: [
      {
        key: 'invited/follow-up-template',
        form: 'content',
        label: 'Follow-up template',
        contentKey: 'toolkit/emails/invitation',
      },
    ],
  },
  {
    status: 'confirmed',
    label: 'Confirmed — schedule a date',
    items: [
      { key: 'confirmed/title', form: 'field', fieldKey: 'title', label: 'Title' },
      { key: 'confirmed/abstract', form: 'field', fieldKey: 'abstract', label: 'Abstract' },
      {
        key: 'confirmed/talk-details-template',
        form: 'content',
        label: 'Talk details email',
        contentKey: 'toolkit/emails/talk-details',
      },
    ],
  },
  {
    status: 'scheduled',
    label: 'Scheduled — runbook',
    items: [
      { key: 'scheduled/T-30/visuals', form: 'checkbox', label: 'Visuals + flyer made', window: 30 },
      {
        key: 'scheduled/T-21/linkedin',
        form: 'checkbox',
        label: 'LinkedIn post published',
        window: 21,
        contentKey: 'toolkit/linkedin-post',
      },
      {
        key: 'scheduled/T-14/zoom-link',
        form: 'checkbox',
        label: 'Zoom link from operations',
        window: 14,
        contentKey: 'toolkit/emails/zoom-request',
      },
      {
        key: 'scheduled/T-14/access-setup',
        form: 'checkbox',
        label: 'Canva + LinkedIn access in place',
        window: 14,
      },
      {
        key: 'scheduled/T-7/forum-announce',
        form: 'checkbox',
        label: 'Forum announcement seeded',
        window: 7,
        contentKey: 'toolkit/forum-post-announce',
      },
      {
        key: 'scheduled/T-7/seed-questions',
        form: 'checkbox',
        label: 'Seeded a question on the forum',
        window: 7,
      },
      {
        key: 'scheduled/T-3/reminder',
        form: 'checkbox',
        label: 'Reminder sent to speaker',
        window: 3,
        contentKey: 'toolkit/emails/reminder',
      },
      {
        key: 'scheduled/T-3/plan-day',
        form: 'checkbox',
        label: 'Plan for the day agreed between hosts',
        window: 3,
      },
      {
        key: 'scheduled/T-1/final-reminder',
        form: 'checkbox',
        label: 'Final reminder + registration check',
        window: 1,
      },
    ],
  },
  {
    status: 'delivered',
    label: 'Delivered — wrap-up',
    items: [
      {
        key: 'delivered/registrations',
        form: 'field',
        fieldKey: 'registrations',
        label: 'Registrations',
        required: true,
      },
      {
        key: 'delivered/live-peak',
        form: 'field',
        fieldKey: 'live_peak',
        label: 'Live peak',
        required: true,
      },
      {
        // Records where the recording is. It does not publish it: the
        // public feed links a recording only once `finalize-archive` has
        // written `outcome: 'published'` on the record
        // (`tools/convener_ops/public_data.py`), which is the gate below this
        // checklist, not a field in it.
        key: 'delivered/youtube-url',
        form: 'field',
        fieldKey: 'youtube_url',
        label: 'YouTube URL — recorded here, published only through the gate below',
      },
      {
        key: 'delivered/youtube-views-30d',
        form: 'field',
        fieldKey: 'youtube_views_30d',
        label: 'YouTube views (30d) — can be filled later from Archive',
      },
      {
        key: 'delivered/forum-replies',
        form: 'field',
        fieldKey: 'forum_replies',
        label: 'Forum replies — can be filled later from Archive',
      },
      {
        key: 'delivered/forum-thread',
        form: 'field',
        fieldKey: 'forum_thread',
        label: 'Forum thread URL',
      },
      {
        key: 'delivered/forum-summary',
        form: 'checkbox',
        label: 'Forum summary posted',
        required: true,
        contentKey: 'toolkit/forum-post-summary',
      },
      {
        key: 'delivered/thank-you',
        form: 'checkbox',
        label: 'Thank-you email sent to speaker',
        required: true,
        contentKey: 'toolkit/emails/thank-you',
      },
    ],
  },
];

export function phaseOf(status: SpeakerStatus): PhaseDef | undefined {
  return PHASES.find(p => p.status === status);
}

/** True if all required items (fields + checkboxes) of the delivered phase are satisfied. */
export function canFinalize(s: Speaker): boolean {
  const phase = phaseOf('delivered');
  if (!phase || s.status !== 'delivered') return false;
  for (const item of phase.items) {
    if (!item.required) continue;
    if (item.form === 'field') {
      const val = fieldValue(s, item.fieldKey!);
      if (val === '' || val === null || val === undefined) return false;
    }
    if (item.form === 'checkbox') {
      if (!s.runbook_progress[item.key]) return false;
    }
  }
  return true;
}

/** Read a Speaker field value from a FieldKey (top-level or metrics). */
export function fieldValue(s: Speaker, k: FieldKey): string | number | null {
  switch (k) {
    case 'host_1':
      return s.host_1;
    case 'host_2':
      return s.host_2;
    case 'title':
      return s.title;
    case 'abstract':
      return s.abstract;
    case 'youtube_url':
      return s.youtube_url;
    case 'forum_thread':
      return s.forum_thread;
    case 'registrations':
      return s.metrics.registrations;
    case 'live_peak':
      return s.metrics.live_peak;
    case 'youtube_views_30d':
      return s.metrics.youtube_views_30d;
    case 'forum_replies':
      return s.metrics.forum_replies;
  }
}

/** Immutably set a Speaker field by FieldKey. */
export function setField(s: Speaker, k: FieldKey, v: string): Speaker {
  switch (k) {
    case 'host_1':
      return { ...s, host_1: v };
    case 'host_2':
      return { ...s, host_2: v };
    case 'title':
      return { ...s, title: v };
    case 'abstract':
      return { ...s, abstract: v };
    case 'youtube_url':
      return { ...s, youtube_url: v };
    case 'forum_thread':
      return { ...s, forum_thread: v };
    case 'registrations':
      return { ...s, metrics: { ...s.metrics, registrations: v === '' ? null : Number(v) } };
    case 'live_peak':
      return { ...s, metrics: { ...s.metrics, live_peak: v === '' ? null : Number(v) } };
    case 'youtube_views_30d':
      return { ...s, metrics: { ...s.metrics, youtube_views_30d: v === '' ? null : Number(v) } };
    case 'forum_replies':
      return { ...s, metrics: { ...s.metrics, forum_replies: v === '' ? null : Number(v) } };
  }
}

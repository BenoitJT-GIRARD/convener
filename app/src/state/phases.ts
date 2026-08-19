import type { Config, SpeakerStatus, Speaker } from '../data/types';
import { channelItem, channelsOf } from './channels';

export type ItemForm = 'content' | 'field' | 'checkbox' | 'button-group';

/** The line whose wording carries the view-counting window. */
export const VIEW_COUNT_KEY = 'delivered/youtube-views-30d';

/** The window used only for the wording of a screen drawn before any config
 *  has loaded. `data/config.yml` is the number that governs. */
const DEFAULT_VIEW_WINDOW_DAYS = 30;

/**
 * How the view-count field is named, for the window the config sets.
 *
 * The window is a convention and nothing more -- views arrive for years, so a
 * count means something only next to another count read off the same number
 * of days after its talk -- which is why it is `view_count_window_days` in
 * `data/config.yml` and not a constant here. It is also why the label is
 * built rather than typed: a handbook saying thirty days and a form asking
 * for something else would leave a volunteer to guess which the Board meant,
 * and the guess would be stored as a number nobody could compare afterwards.
 * `docs/workflow/4-after.md` states the convention.
 */
export function viewCountLabel(config: Pick<Config, 'view_count_window_days'>): string {
  return `Video views (${config.view_count_window_days}d)`;
}

/** The wording before a config is in hand; `phaseItems` replaces it. */
const VIEW_COUNT_LABEL = viewCountLabel({
  view_count_window_days: DEFAULT_VIEW_WINDOW_DAYS,
});

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
  /** Must be done before the phase it sits in is finished. On the delivered
   *  phase that is the same thing as blocking the archive, which is why
   *  `blockers` reads it there and `state/inbox.ts` reads it to raise the
   *  wrap-up rows. */
  required?: boolean;
  /** Stops the archive from being finalised *from wherever it sits in the
   *  journey*. Only a line whose absence damages the published record earns
   *  it: `required` is the ordinary "not finished yet", this is "do not
   *  publish without it". */
  blocksFinalisation?: true;
  /** One short sentence, shown under the label, saying why the line is there.
   *  For the handful of steps whose reason is not obvious from the wording
   *  and whose cost, when they are skipped, cannot be paid back afterwards.
   *  A control whose reason nobody knows is a control people tick without
   *  reading it. */
  note?: string;
  /** The key of the line this one comes after. The journey is written in
   *  order everywhere else and nothing enforces it, because ticking the
   *  T-7 forum post before the T-14 one costs nothing. This exists for the
   *  one sequence where being out of order is not a scheduling detail but a
   *  sign that something irreversible has already gone wrong. */
  after?: string;
  contentKey?: string;
  window?: number;
  fieldKey?: FieldKey;
}

export interface PhaseDef {
  status: SpeakerStatus;
  label: string;
  items: RunbookItem[];
  /** Key of the line the promotion channels follow, for the one phase that
   *  promotes. The channels themselves are configuration
   *  (`state/channels.ts`), so where they fall is the only thing this table
   *  can say about them. A key that names no line of this phase would put
   *  them at the front, which the ordering test in `phases.test.ts` catches
   *  by comparing the whole expanded sequence rather than its membership. */
  channelsAfter?: string;
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
      {
        // The only line of the journey whose recipient is not on the team and
        // not the speaker: whoever sent the proposal in, very often somebody
        // outside the series entirely. Nothing else in the pipeline writes to
        // them until the board has decided, which can be weeks -- and silence
        // from a series is not read as "still thinking", it is read as
        // "defunct". So the acknowledgement is a line somebody can be put
        // down for and tick, on the day the proposal arrives.
        key: 'lead/acknowledge-proposal',
        form: 'checkbox',
        label: 'Proposal acknowledged to whoever sent it',
        contentKey: 'toolkit/emails/proposal-received',
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
    // Two weeks out, once the speaker is known to be on the forum, the event
    // is announced everywhere it is announced. Which places those are is read
    // from `data/config.yml`; only their position in the journey is here.
    channelsAfter: 'scheduled/T-14/speaker_registered',
    items: [
      { key: 'scheduled/T-30/visuals', form: 'checkbox', label: 'Visuals + flyer made', window: 30 },
      {
        // The speaker hears that the series is about to start talking about
        // them *before* it does. The announcement carries their name, their
        // title and their abstract, and a speaker who learns of it from a
        // notification has been told last about their own talk.
        key: 'scheduled/T-21/promotion-starting',
        form: 'checkbox',
        label: 'Speaker told the promotion is starting',
        window: 21,
        contentKey: 'toolkit/emails/promotion-starting',
      },
      {
        key: 'scheduled/T-21/linkedin',
        form: 'checkbox',
        label: 'LinkedIn post published',
        window: 21,
        contentKey: 'toolkit/linkedin-post',
      },
      {
        // No template hangs off this line any more. It used to hand over an
        // e-mail asking a contact at another institute to open the room; the
        // series holds the meeting account itself now, so the link is either
        // the platform's or one somebody types in, and there is nobody left
        // to write to. The line itself stays: the link still has to exist.
        key: 'scheduled/T-14/zoom-link',
        form: 'checkbox',
        label: 'Meeting link in hand, recording arranged',
        window: 14,
      },
      {
        key: 'scheduled/T-14/access-setup',
        form: 'checkbox',
        label: 'LinkedIn access in place',
        window: 14,
      },
      {
        // Written in capitals with two exclamation marks in the checklist the
        // volunteers actually keep, and the only line of the runbook that
        // stops the archive. The series promises a discussion around each
        // seminar; a speaker who is not in the thread of their own seminar
        // cannot answer anyone in it, and the promise is published anyway.
        //
        // The last segment of the key is the name `blockers` reports, so the
        // screen and the record cannot end up calling this two things.
        key: 'scheduled/T-14/speaker_registered',
        form: 'checkbox',
        label: 'Speaker registered on the forum and to their own talk',
        window: 14,
        blocksFinalisation: true,
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
        key: 'scheduled/T-7/waiting-room',
        form: 'checkbox',
        label: 'Waiting room and co-host rights set up',
        window: 7,
      },
      {
        // The run of show is offered here, at the moment the two hosts sit
        // down to divide the session between them. It is a template and not a
        // rule: it carries the split the hosts who have run these sessions
        // settled on, nothing reads whether it was followed, and a pair who
        // agree a different split tick this line exactly the same way.
        //
        // T-1 week, which is what spec F-02 says and what the page this line
        // hands over opens with ("At T-1 week, in ten minutes"). It sat at
        // T-3 because the existing T-3 line was reused rather than a T-7 one
        // added, so the app and the page disagreed about when the thing
        // happens. No record carries the old key: `runbook_progress` is empty
        // in `data/speakers.yml`, so renaming it is not a migration.
        key: 'scheduled/T-7/plan-day',
        form: 'checkbox',
        label: 'Plan for the day agreed between hosts',
        window: 7,
        contentKey: 'toolkit/run-of-show',
      },
      {
        key: 'scheduled/T-3/reminder',
        form: 'checkbox',
        label: 'Reminder sent to speaker',
        window: 3,
        contentKey: 'toolkit/emails/reminder',
      },
      {
        // "Registration" means the link the audience uses, which is what the
        // handbook has always said here -- not the speaker's own sign-up,
        // which is the T-14 line above and a different piece of work a week
        // earlier. Two lines a week apart both reading "registration check"
        // is how one of them gets ticked for the other.
        key: 'scheduled/T-1/final-reminder',
        form: 'checkbox',
        label: 'Final reminder sent, registration link checked',
        window: 1,
      },
      // The recording sequence, on the day. Three steps and not one tick,
      // because a single "recording done" box cannot say which of the three
      // was missed, and which one was missed is the whole question: a talk
      // nobody recorded is gone, and a discussion recorded by mistake holds
      // people speaking freely on the understanding that they were not.
      // Neither can be repaired afterwards.
      {
        key: 'scheduled/T-0/recording-talk-started',
        form: 'checkbox',
        label: 'Recording started for the talk',
        window: 0,
      },
      {
        key: 'scheduled/T-0/recording-stopped-before-discussion',
        form: 'checkbox',
        label: 'Recording stopped before the discussion begins',
        window: 0,
        note: 'The discussion is not published, and a discussion recorded by mistake cannot be unrecorded.',
        after: 'scheduled/T-0/recording-talk-started',
      },
      {
        key: 'scheduled/T-0/recording-discussion-started',
        form: 'checkbox',
        label: 'Recording started again for the discussion',
        window: 0,
        after: 'scheduled/T-0/recording-stopped-before-discussion',
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
        // The label carries a number that is configuration, so `phaseItems`
        // rewrites it from the loaded config. What is typed here is only what
        // a screen shows before any config has arrived.
        key: VIEW_COUNT_KEY,
        form: 'field',
        fieldKey: 'youtube_views_30d',
        label: `${VIEW_COUNT_LABEL} — can be filled later from Archive`,
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
      {
        // Only honest once the speaker has answered the consent question and
        // the recorded answer is that they agreed: until then there is no
        // published recording to write about. The message it hands over says
        // so and refuses to be the ask; the ask is `consent-request.md`,
        // which explains what would be published and how to withdraw.
        //
        // Not `after:` the thank-you or anything else, because what this line
        // waits on is not another tick: it is a value on the record
        // (`publication.consent`), and `after` names steps.
        key: 'delivered/video-online',
        form: 'checkbox',
        label: 'Speaker told the video is online',
        note: 'Only after the speaker has agreed to the recording being published — check the recorded answer first.',
        contentKey: 'toolkit/emails/video-online',
      },
      // The conflict declared to the audience during the session (G-16), as
      // three lines and not one.
      //
      // Three, because the decision names three facts -- a slide of its own,
      // said out loud, written into the video description -- and a single box
      // would let all three be asserted by somebody who did one. The problem
      // it answers is observed rather than theoretical: a slide flashed up for
      // two seconds while nobody says anything is what a single tick calls
      // done. Someone who ticks three has had to think about three.
      //
      // This is not the board's conflict of interest. `conflicts_of_interest`
      // on the record is a declaration made to the board so that it can apply
      // its own recusal rules to a vote; these three lines are the speaker's
      // or the hosts' declaration made to the audience, in the room. Different
      // people, a different moment, and nothing here is derived from that
      // field -- a free-text box that may well read "none" cannot be turned
      // into a gate without making volunteers tick a declaration that never
      // happened.
      //
      // None of the three stops the archive, for the same reason: the decision
      // asks for them when a conflict is declared, and the app has no way to
      // know that a conflict was. A control that has to be ticked on every
      // record, including the ones with nothing to declare, is a control
      // people learn to tick without reading -- which is precisely the failure
      // these three lines exist to answer.
      {
        key: 'delivered/coi-slide-shown',
        form: 'checkbox',
        label: 'Conflict of interest: dedicated slide shown in the session',
      },
      {
        key: 'delivered/coi-spoken-aloud',
        form: 'checkbox',
        label: 'Conflict of interest: declaration spoken aloud in the session',
      },
      {
        key: 'delivered/coi-in-video-description',
        form: 'checkbox',
        label: 'Conflict of interest: declaration written in the video description',
      },
    ],
  },
];

export function phaseOf(status: SpeakerStatus): PhaseDef | undefined {
  return PHASES.find(p => p.status === status);
}

/**
 * The lines of one phase, including the ones that are configuration.
 *
 * `PHASES` is a constant; the places an event is announced are not. They live
 * in `data/config.yml` and are read through `state/channels.ts`, so a phase's
 * journey is a function of the loaded config rather than a table. Everything
 * that walks a phase's lines walks them from here -- the checklist screen, the
 * inbox, and the guard in `state/assignment.ts` that decides which keys can
 * carry an owner -- so a channel added to the file is, the same day, a line a
 * volunteer sees, ticks and can be put down for.
 *
 * `null` means no config has loaded yet, which is what a screen holds while
 * the data is being fetched: nothing expands and the phase reads exactly as it
 * did before. That is a different fact from a config whose `channels` cannot
 * be read, which `channelsOf` refuses outright rather than quietly showing a
 * promotion phase with no lines in it.
 */
export function phaseItems(phase: PhaseDef, config: Config | null): RunbookItem[] {
  let items = [...phase.items];
  if (config !== null) {
    items = items.map(item =>
      item.key === VIEW_COUNT_KEY
        ? { ...item, label: item.label.replace(VIEW_COUNT_LABEL, viewCountLabel(config)) }
        : item,
    );
  }
  if (phase.channelsAfter === undefined || config === null) return items;
  const after = items.findIndex(item => item.key === phase.channelsAfter);
  items.splice(after + 1, 0, ...channelsOf(config).map(channelItem));
  return items;
}

/**
 * Whether this record already carries what the item asks for.
 *
 * One reading of "done" for the whole app: `canFinalize` gates the archive on
 * it, and `state/assignment.ts` uses it to decide whether an item someone owns
 * is still waiting on them. A second copy of these two `if`s would have been
 * free to drift, and the drift would show up as a line still nagging somebody
 * after they had filled it in.
 *
 * A `content` item is never "done": it is a template to read, not a thing to
 * complete, so there is nothing about it that could be waiting. It is reported
 * as done for exactly that reason -- nothing outstanding.
 */
export function isItemDone(s: Speaker, item: RunbookItem): boolean {
  if (item.form === 'field') {
    const val = fieldValue(s, item.fieldKey!);
    return !(val === '' || val === null || val === undefined);
  }
  if (item.form === 'checkbox') return !!s.runbook_progress[item.key];
  return true;
}

/** The line the journey knows under this key, from anywhere in it. */
export function itemByKey(key: string): RunbookItem | undefined {
  for (const phase of PHASES) {
    const found = phase.items.find(item => item.key === key);
    if (found) return found;
  }
  return undefined;
}

/**
 * The step this one comes after, when that step has not been ticked yet.
 *
 * `undefined` -- the ordinary case -- means nothing comes before this line and
 * the volunteer is free to work down the list however the day goes. A line
 * that is already ticked is never held back either: the constraint is about
 * ticking the next thing, not about keeping a record from being corrected.
 *
 * This names the step rather than answering yes or no, because the screen has
 * to say *which* one comes first. "You cannot tick this" with no further
 * explanation, on a sequence a volunteer has just lived through, is how a tool
 * teaches people that it is broken.
 */
export function stepBefore(s: Speaker, item: RunbookItem): RunbookItem | undefined {
  if (item.after === undefined) return undefined;
  if (isItemDone(s, item)) return undefined;
  const previous = itemByKey(item.after);
  if (previous === undefined || isItemDone(s, previous)) return undefined;
  return previous;
}

/** One reason the archive cannot be finalised yet. */
export interface Blocker {
  /** Stable name for this obstacle: the last segment of the line's journey
   *  key, so a screen naming it and a record storing it cannot drift. */
  key: string;
  /** One sentence, already readable by a volunteer, about a piece of work
   *  outstanding -- never about a person. */
  why: string;
}

/**
 * A line stops finalisation either because the wrap-up is not finished
 * (`required`, on the delivered phase, which is what that flag has always
 * meant there) or because it is marked as damaging the published record by its
 * absence, wherever it sits. The second exists because the one line that most
 * needs to hold falls three weeks before the talk: the check that the speaker
 * is on the forum and signed up to their own seminar.
 */
function stopsFinalisation(phase: PhaseDef, item: RunbookItem): boolean {
  return item.blocksFinalisation === true || (phase.status === 'delivered' && item.required === true);
}

function whyOutstanding(item: RunbookItem): string {
  return item.form === 'field' ? `${item.label} is still empty.` : `${item.label} is not ticked.`;
}

/**
 * Everything standing between this record and its archive, in journey order.
 *
 * A boolean says the button is off and leaves the volunteer to guess which of
 * a dozen lines is why -- and once a line from three weeks before the talk can
 * be the answer, guessing stops working: nothing in the delivered checklist in
 * front of them would explain it. So the obstacles are named, and the screen
 * renders the sentences as they are.
 *
 * Empty means finalisation is possible; `canFinalize` is exactly that test and
 * not a second reading of the same question.
 */
export function blockers(s: Speaker): Blocker[] {
  if (s.status !== 'delivered') {
    return [{ key: 'not-delivered', why: 'This talk has not been delivered yet.' }];
  }
  const found: Blocker[] = [];
  for (const phase of PHASES) {
    for (const item of phase.items) {
      if (!stopsFinalisation(phase, item)) continue;
      if (isItemDone(s, item)) continue;
      found.push({ key: item.key.slice(item.key.lastIndexOf('/') + 1), why: whyOutstanding(item) });
    }
  }
  return found;
}

/** True when nothing is left in the way of the archive. */
export function canFinalize(s: Speaker): boolean {
  return blockers(s).length === 0;
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

import { describe, it, expect } from 'vitest';
import {
  phaseOf,
  phaseItems,
  blockers,
  canFinalize,
  fieldValue,
  setField,
  PHASES,
  VIEW_COUNT_KEY,
  type FieldKey,
} from '../../src/state/phases';
import type { Config, Speaker } from '../../src/data/types';
import { config, speaker as double } from '../helpers/data-doubles';
import eventChainKeys from '../../../tools/tests/fixtures/event-chain-keys.json';

/** The one line of the runbook that stops the archive, by the name
 *  `blockers` reports it under. */
const REGISTERED = 'scheduled/T-14/speaker_registered';

/** Everything the wrap-up asks for, so a test about one obstacle is not
 *  quietly about five. */
const WRAPPED_UP = {
  metrics: { registrations: 50, live_peak: 40, youtube_views_30d: null, forum_replies: null },
  runbook_progress: {
    [REGISTERED]: true,
    'delivered/forum-summary': true,
    'delivered/thank-you': true,
  },
};

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
const base: Speaker = double({
  id: 'x',
  name: 'X',
  gender: 'undisclosed',
  career_stage: 'undisclosed',
  email: '',
  affiliation: '',
  country: '',
  title: '',
  abstract: '',
  conflicts_of_interest: '',
  source: 'organizer',
  proposed_by: '',
  assigned_to: '',
  links: [],
  host_1: '',
  host_2: '',
  status: 'delivered',
  selection: { ballots: [], opened_on: '', decided_on: '' },
  publication: {
    consent: 'pending',
    approved_by: '',
    approved_on: '',
    objections: [],
    outcome: '',
  },
  edition_code: 'MRG-9',
  date: '2026-06-01',
  time: '12:30',
  zoom_link: '',
  youtube_url: '',
  forum_thread: '',
  runbook_progress: {},
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
});

describe('phases v2', () => {
  it('returns phase by status', () => {
    expect(phaseOf('lead')?.label).toMatch(/Lead/);
    expect(phaseOf('archived')).toBeUndefined();
  });

  it('every runbook key is unique', () => {
    const keys: string[] = [];
    for (const p of PHASES) for (const i of p.items) keys.push(i.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('canFinalize false when required fields missing', () => {
    expect(canFinalize(base)).toBe(false);
  });

  it('canFinalize false when required checkboxes missing', () => {
    const s = { ...base, metrics: { ...base.metrics, registrations: 50, live_peak: 40 } };
    expect(canFinalize(s)).toBe(false);
  });

  it('canFinalize true when all required satisfied', () => {
    const s: Speaker = { ...base, ...WRAPPED_UP };
    expect(canFinalize(s)).toBe(true);
  });

  it('canFinalize ignores optional fields', () => {
    // youtube_url, youtube_views_30d and forum_replies stay empty/null.
    const s: Speaker = { ...base, ...WRAPPED_UP };
    expect(canFinalize(s)).toBe(true);
  });
});

describe('the view-counting window is a convention, so it is configuration', () => {
  /**
   * Views arrive for years; a count is only comparable with another count
   * taken the same number of days out. The number is therefore arbitrary,
   * agreed once and written in `instance/data/config.yml` -- and the field a volunteer
   * fills in has to say which number is in force, or the handbook and the
   * form can end up asking for two different measurements of the same talk.
   * `docs/handbook/workflow/4-after.md` is where the convention is stated.
   */
  const wrapUp = phaseOf('delivered')!;
  const labelFor = (cfg: Config | null) =>
    phaseItems(wrapUp, cfg).find(i => i.key === VIEW_COUNT_KEY)!.label;

  it('names the window the config sets, not the one that was typed', () => {
    expect(labelFor(config({ view_count_window_days: 30 }))).toContain('(30d)');
    expect(labelFor(config({ view_count_window_days: 90 }))).toContain('(90d)');
  });

  it('keeps the rest of the line, so the hint about Archive survives', () => {
    expect(labelFor(config({ view_count_window_days: 90 }))).toContain(
      'can be filled later from Archive',
    );
  });

  it('falls back to a stated window before any config has loaded', () => {
    // A screen drawn while the file is still being fetched shows a number
    // rather than a gap: a blank window reads as "any time you like".
    expect(labelFor(null)).toMatch(/\(\d+d\)/);
  });
});

describe('the journey the volunteers actually keep', () => {
  /**
   * The whole sequence, not its membership.
   *
   * A step present and a step in the right place are two different facts, and
   * only the second is any use to somebody working down a checklist three
   * weeks before a talk: "tell the speaker the promotion is starting" after
   * the announcement has gone out is not the same instruction. So this asserts
   * the order, and it asserts it including the lines that come from
   * configuration -- the promotion channels sit between the registration check
   * and the week-before work, and nowhere else.
   */
  it('runs the scheduled phase in chronological order, channels included', () => {
    const phase = phaseOf('scheduled')!;
    expect(phaseItems(phase, config()).map(i => i.key)).toEqual([
      'scheduled/T-30/visuals',
      'scheduled/T-21/promotion-starting',
      'scheduled/T-21/linkedin',
      'scheduled/T-21/mailing-list',
      'scheduled/T-14/zoom-link',
      'scheduled/T-14/access-setup',
      'scheduled/T-14/speaker_registered',
      'promotion/forum',
      'promotion/linkedin_page',
      'scheduled/T-7/forum-announce',
      'scheduled/T-7/seed-questions',
      'scheduled/T-7/waiting-room',
      'scheduled/T-7/token-renewal',
      'scheduled/T-7/plan-day',
      'scheduled/T-3/reminder',
      'scheduled/T-1/final-reminder',
      'scheduled/T-0/recording-talk-started',
      'scheduled/T-0/recording-stopped-before-discussion',
      'scheduled/T-0/recording-discussion-started',
      'scheduled/mark-delivered',
    ]);
  });

  /**
   * What you need to know, then what you do, then how you record that you
   * did it -- the order the maintainer's three frictions all turn out to be
   * about (R34, R35, R37). It is asserted key by key rather than described,
   * because "the buttons come last" was true of the code that put *Mark
   * invitation sent* in front of the dates the invitation names: the buttons
   * were not in this sequence at all, they were in a block above it.
   */
  it.each([
    [
      'approved' as const,
      [
        'approved/host_1',
        'approved/host_2',
        'approved/offer-dates',
        'approved/invitation-email',
        'approved/send-invitation',
      ],
    ],
    ['invited' as const, ['invited/follow-up-template', 'invited/replies', 'invited/decline']],
    [
      'confirmed' as const,
      [
        'confirmed/talk-details-template',
        'confirmed/title',
        'confirmed/abstract',
        'confirmed/lock-date',
      ],
    ],
    ['lead' as const, ['lead/selection-criteria', 'lead/acknowledge-proposal', 'lead/board-vote']],
  ])('runs %s in the order know, do, record', (status, keys) => {
    expect(phaseItems(phaseOf(status)!, config()).map(i => i.key)).toEqual(keys);
  });

  it('runs the wrap-up in the order the work happens', () => {
    const phase = phaseOf('delivered')!;
    expect(phaseItems(phase, config()).map(i => i.key)).toEqual([
      'delivered/attendance-export-encrypted',
      'delivered/recording-retrieved',
      'delivered/registrations',
      'delivered/live-peak',
      'delivered/youtube-url',
      'delivered/youtube-views-30d',
      'delivered/forum-replies',
      'delivered/forum-thread',
      'delivered/forum-summary',
      'delivered/thank-you',
      'delivered/video-online',
      'delivered/coi-slide-shown',
      'delivered/coi-spoken-aloud',
      'delivered/coi-in-video-description',
    ]);
  });

  it('never sends a volunteer backwards in time within a phase', () => {
    for (const phase of PHASES) {
      const windows = phaseItems(phase, config())
        .map(i => i.window)
        .filter((w): w is number => w !== undefined);
      expect(windows).toEqual([...windows].sort((a, b) => b - a));
    }
  });

  it('leaves the journey as it was when no config has loaded', () => {
    for (const phase of PHASES) {
      expect(phaseItems(phase, null)).toEqual(phase.items);
    }
    expect(phaseItems(phaseOf('lead')!, config())).toEqual(phaseOf('lead')!.items);
  });

  it('follows the file: the channel lines are the ones config lists', () => {
    const cfg = config({ channels: [{ key: 'posters', label: 'Printed posters' }] });
    const keys = phaseItems(phaseOf('scheduled')!, cfg).map(i => i.key);
    expect(keys.filter(k => k.startsWith('promotion/'))).toEqual(['promotion/posters']);
  });

  /**
   * D-14: `tools/convener_ops/journey/platform_fcc.py::RETRIEVED_TICK` is the one
   * `runbook_progress` key Python itself reads (release_recording's own
   * gate) -- if this journey ticked a differently-spelled key, a host
   * could tick this box forever and the release job would never see it,
   * or the reverse: a recording could be released on a tick this journey
   * never shows. Pinned against the same fixture
   * `tools/tests/journey/test_platform_fcc.py::test_retrieved_tick_matches_the_shared_fixture`
   * checks Python-side.
   */
  it('spells the recording-retrieved key the same way release_recording reads it', () => {
    const keys = phaseOf('delivered')!.items.map(i => i.key);
    expect(keys.filter(k => k === eventChainKeys.retrieved_tick_key)).toEqual([
      eventChainKeys.retrieved_tick_key,
    ]);
  });
});

describe('what stands between a record and its archive', () => {
  /**
   * The line the checklist writes in capitals with two exclamation marks. A
   * speaker who is not on the forum and not signed up to their own seminar
   * cannot answer anybody in the thread the series promises around it -- and
   * by the time the wrap-up is being filled in, nothing on the screen would
   * have said so.
   */
  it('blocks finalisation while the speaker registration check is unticked', () => {
    const s: Speaker = {
      ...base,
      ...WRAPPED_UP,
      runbook_progress: { ...WRAPPED_UP.runbook_progress, [REGISTERED]: false },
    };
    expect(blockers(s).map(b => b.key)).toContain('speaker_registered');
    expect(canFinalize(s)).toBe(false);
  });

  it('lets the archive through once it is ticked, everything else being equal', () => {
    expect(canFinalize({ ...base, ...WRAPPED_UP })).toBe(true);
  });

  it('is the only step of the runbook that blocks: the rest inform', () => {
    const s: Speaker = { ...base, ...WRAPPED_UP, runbook_progress: WRAPPED_UP.runbook_progress };
    // None of the new informative steps is ticked on this record, and it
    // finalises all the same.
    for (const key of [
      'scheduled/T-21/promotion-starting',
      'scheduled/T-7/waiting-room',
      'delivered/video-online',
    ]) {
      expect(s.runbook_progress[key]).toBeUndefined();
    }
    expect(blockers(s)).toEqual([]);
  });

  it('names each obstacle in a sentence about the work, not about a person', () => {
    const why = blockers(base).map(b => b.why);
    expect(why).toContain('Speaker registered on the forum and to their own talk is not ticked.');
    expect(why).toContain('Registrations is still empty.');
    expect(why).toContain('Forum summary posted is not ticked.');
    for (const sentence of why) expect(sentence).toMatch(/\.$/);
  });

  it('says so plainly when the talk has not happened yet', () => {
    const s: Speaker = { ...base, ...WRAPPED_UP, status: 'scheduled' };
    expect(blockers(s).map(b => b.key)).toEqual(['not-delivered']);
    expect(canFinalize(s)).toBe(false);
  });

  it('gives each obstacle a name of its own', () => {
    const keys = blockers(base).map(b => b.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  /** `canFinalize` asks the same question as `blockers` and must not answer it
   *  a second way: the two are checked together over records that differ one
   *  requirement at a time. */
  it('keeps canFinalize and blockers the same question', () => {
    const records: Speaker[] = [
      base,
      { ...base, ...WRAPPED_UP },
      { ...base, ...WRAPPED_UP, status: 'scheduled' },
      { ...base, metrics: { ...base.metrics, registrations: 50, live_peak: 40 } },
      { ...base, runbook_progress: { [REGISTERED]: true } },
      {
        ...base,
        ...WRAPPED_UP,
        runbook_progress: { ...WRAPPED_UP.runbook_progress, 'delivered/thank-you': false },
      },
    ];
    for (const s of records) expect(canFinalize(s)).toBe(blockers(s).length === 0);
  });
});

describe('fieldValue', () => {
  const s: Speaker = {
    ...base,
    host_1: 'h1',
    host_2: 'h2',
    title: 't',
    abstract: 'a',
    youtube_url: 'yt',
    forum_thread: 'ft',
    metrics: { registrations: 1, live_peak: 2, youtube_views_30d: 3, forum_replies: 4 },
  };

  it.each<[FieldKey, string | number | null]>([
    ['host_1', 'h1'],
    ['host_2', 'h2'],
    ['title', 't'],
    ['abstract', 'a'],
    ['youtube_url', 'yt'],
    ['forum_thread', 'ft'],
    ['registrations', 1],
    ['live_peak', 2],
    ['youtube_views_30d', 3],
    ['forum_replies', 4],
  ])('reads %s', (key, expected) => {
    expect(fieldValue(s, key)).toBe(expected);
  });
});

describe('setField', () => {
  it.each<FieldKey>(['host_1', 'host_2', 'title', 'abstract', 'youtube_url', 'forum_thread'])(
    'sets the string field %s',
    key => {
      const out = setField(base, key, 'new-value');
      expect(fieldValue(out, key)).toBe('new-value');
    },
  );

  it.each<FieldKey>(['registrations', 'live_peak', 'youtube_views_30d', 'forum_replies'])(
    'sets the numeric metric %s, coercing to a number',
    key => {
      const out = setField(base, key, '42');
      expect(fieldValue(out, key)).toBe(42);
    },
  );

  it.each<FieldKey>(['registrations', 'live_peak', 'youtube_views_30d', 'forum_replies'])(
    'sets the numeric metric %s to null on empty string',
    key => {
      const withValue = setField(base, key, '10');
      const cleared = setField(withValue, key, '');
      expect(fieldValue(cleared, key)).toBeNull();
    },
  );
});

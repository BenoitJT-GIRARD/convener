/**
 * Task 7 -- the ready-to-publish texts, and the two properties that make
 * them safe to draft from the live record rather than a pre-gated feed:
 *
 * - a speaker's biography, portrait and online identities may not appear in
 *   a drafted text until the publication gate has actually opened, exactly
 *   the rule `tools/convener_ops/public_data.py` applies to the public feed
 *   itself (P-4, applied to prose rather than an image);
 * - a room link must never reach a draft, under any name -- structurally,
 *   not merely by the discipline of nobody typing `zoom_link` into a
 *   template.
 *
 * `state/consent.ts::toPublicFields` is the seam: it is the one place a
 * template meant to leave the team may read a speaker's personal fields
 * through, and it is exercised here directly (so a regression is caught
 * before it ever reaches a rendered page) and through the real
 * `recording-announce.md` file (so a regression that only shows up once a
 * template actually uses the seam is caught too).
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { substitute } from '../src/content/render';
import {
  personalDisclosureWithheld,
  recordingWithheld,
  toPublicFields,
} from '../src/state/consent';
import { dateLine, parisStandingStart } from '../src/state/derived';
import type { Publication, Speaker } from '../src/data/types';
import { speaker as double } from './data-doubles';

const DOCS = resolve(__dirname, '../../docs');
function page(relative: string): string {
  return readFileSync(resolve(DOCS, relative), 'utf-8');
}

// The literal value `site/src/_data/events.json`'s own MRG-05 fixture
// carries, kept there specifically as "a synthetic room-link-shaped column
// ... a template-regression canary" (`tools/tests/test_site.py`'s own
// words) for exactly this kind of check. Reused rather than invented afresh,
// so a leak of *this* value is provably a leak and not a coincidence with
// some other string this suite made up.
const POISONED_ROOM_LINK =
  'https://us02web.zoom.us/j/9998887771?pwd=SHOULD-NEVER-APPEAR-IN-BUILT-HTML';

const BIO = 'Ada writes the first published computer program, for a machine that was never built.';
const YOUTUBE = 'https://youtu.be/analytical-engines';

const OPEN_GATE: Publication = {
  consent: 'granted',
  approved_by: 'alice',
  approved_on: '2026-06-15',
  objections: [],
  outcome: 'published',
};

const CLOSED_GATE: Publication = {
  consent: 'pending',
  approved_by: '',
  approved_on: '',
  objections: [],
  outcome: '',
};

function archivedSpeaker(overrides: Partial<Speaker> = {}): Speaker {
  return double({
    id: 'sp-rec',
    name: 'Ada Lovelace',
    affiliation: 'Analytical Engines Institute',
    country: 'UK',
    title: 'On analytical engines',
    abstract: 'An abstract about analytical engines.',
    bio: BIO,
    edition_code: 'MRG-77',
    date: '2026-06-11', // June -- daylight-saving time (CEST)
    time: '12:30',
    zoom_link: POISONED_ROOM_LINK,
    youtube_url: YOUTUBE,
    forum_thread: 'https://forum.example.org/t/77',
    status: 'archived',
    publication: OPEN_GATE,
    ...overrides,
  });
}

describe('toPublicFields -- the gate a drafted text reads through', () => {
  it('carries the programme unconditionally', () => {
    const pub = toPublicFields(archivedSpeaker());
    expect(pub.name).toBe('Ada Lovelace');
    expect(pub.affiliation).toBe('Analytical Engines Institute');
    expect(pub.title).toBe('On analytical engines');
  });

  it('withholds the biography and the recording until the gate opens', () => {
    const pending = archivedSpeaker({ publication: CLOSED_GATE });
    expect(personalDisclosureWithheld(pending)).toBe(true);
    expect(recordingWithheld(pending)).toBe(true);
    const pub = toPublicFields(pending);
    expect(pub.bio).toBe('');
    expect(pub.youtube_url).toBe('');
  });

  it('discloses the biography and the recording once consent is granted and published', () => {
    const open = archivedSpeaker();
    expect(personalDisclosureWithheld(open)).toBe(false);
    expect(recordingWithheld(open)).toBe(false);
    const pub = toPublicFields(open);
    expect(pub.bio).toBe(BIO);
    expect(pub.youtube_url).toBe(YOUTUBE);
  });

  it('withholds the recording outside archived status, even with a granted, published gate', () => {
    const delivered = archivedSpeaker({ status: 'delivered' });
    expect(toPublicFields(delivered).youtube_url).toBe('');
    // The programme is still published at `delivered` -- only the
    // recording waits on the status as well as the gate.
    expect(toPublicFields(delivered).name).toBe('Ada Lovelace');
  });

  it('withholds every personal field when the speaker agreed but the board has not published yet', () => {
    // Approved and waiting on the objection window, or simply never
    // finalised -- `outcome` is `''`, not `'published'`, and the speaker's
    // own `granted` on its own must not be read as the gate having opened.
    const approvedNotYetPublished = archivedSpeaker({
      publication: { consent: 'granted', approved_by: 'alice', approved_on: '2026-06-12', objections: [], outcome: '' },
    });
    expect(personalDisclosureWithheld(approvedNotYetPublished)).toBe(true);
    expect(recordingWithheld(approvedNotYetPublished)).toBe(true);
    expect(toPublicFields(approvedNotYetPublished).bio).toBe('');
  });

  it('withholds every personal field while one objection still stands', () => {
    const objected = archivedSpeaker({
      publication: {
        ...OPEN_GATE,
        objections: [{ member: 'bob', reason: 'a slide was not cleared', date: '2026-06-16', resolved_on: '' }],
      },
    });
    const pub = toPublicFields(objected);
    expect(pub.bio).toBe('');
    expect(pub.youtube_url).toBe('');
  });

  it('blanks every field for a status this project never announces publicly', () => {
    const lead = archivedSpeaker({ status: 'lead', publication: OPEN_GATE });
    const pub = toPublicFields(lead);
    expect(pub.name).toBe('');
    expect(pub.title).toBe('');
    expect(pub.bio).toBe('');
  });

  it('never carries a zoom_link (or a time) field at all -- absent from the shape, not merely empty', () => {
    const pub = toPublicFields(archivedSpeaker());
    expect(Object.keys(pub)).not.toContain('zoom_link');
    expect(Object.keys(pub)).not.toContain('time');
    expect(Object.values(pub)).not.toContain(POISONED_ROOM_LINK);
  });
});

describe('a template that reached for the room link fails loudly instead of leaking it', () => {
  it('{{ public.zoom_link }} resolves to the missing marker, never the address', () => {
    const out = substitute('{{ public.zoom_link }}', { speaker: archivedSpeaker(), today: '2026-06-20' });
    expect(out).toBe('«missing: public.zoom_link»');
    expect(out).not.toContain(POISONED_ROOM_LINK);
  });

  it('{{ speaker.time }} beside a hard-coded zone never appears in a public draft', () => {
    for (const file of [
      'toolkit/forum-post-announce.md',
      'toolkit/linkedin-post.md',
      'toolkit/mailing-list-announce.md',
      'toolkit/recording-announce.md',
    ]) {
      expect(page(file)).not.toMatch(/\{\{\s*(speaker|public)\.time\s*\}\}\s*(CET|CEST)/);
    }
  });
});

describe('the recording announcement (docs/toolkit/recording-announce.md)', () => {
  const RECORDING_ANNOUNCE = 'toolkit/recording-announce.md';

  it('shows the missing marker instead of the biography or the video while the gate is closed', () => {
    const pending = archivedSpeaker({ publication: CLOSED_GATE });
    const out = substitute(page(RECORDING_ANNOUNCE), { speaker: pending, today: '2026-06-20' });
    expect(out).not.toContain(BIO);
    expect(out).not.toContain(YOUTUBE);
    expect(out).toMatch(/«missing: public\.(bio|youtube_url)»/);
  });

  it('carries the real biography and video once the gate is open', () => {
    const open = archivedSpeaker();
    const out = substitute(page(RECORDING_ANNOUNCE), { speaker: open, today: '2026-06-20' });
    expect(out).toContain(BIO);
    expect(out).toContain(YOUTUBE);
    expect(out).not.toMatch(/«missing: /);
  });

  it('never contains the room link, whether the gate is open or closed', () => {
    for (const publication of [OPEN_GATE, CLOSED_GATE]) {
      const out = substitute(page(RECORDING_ANNOUNCE), {
        speaker: archivedSpeaker({ publication }),
        today: '2026-06-20',
      });
      expect(out).not.toContain(POISONED_ROOM_LINK);
      expect(out).not.toContain('zoom');
    }
  });
});

describe('a drafted date names the real Paris offset, never a hard-coded one', () => {
  // Three of this project's own five fixture editions
  // (`site/src/_data/events.json`) fall in daylight-saving time -- a test
  // that only checked a winter date would pass against code that always
  // said CET.
  const SUMMER = ['2026-04-02', '2026-06-11', '2026-09-10'];
  const WINTER = ['2026-02-05', '2026-03-12'];

  it.each(SUMMER)('%s is CEST', iso => {
    expect(parisStandingStart(iso).abbreviation).toBe('CEST');
    expect(parisStandingStart(iso).offset).toBe('+02:00');
    expect(dateLine(iso)).toContain('CEST');
  });

  it.each(WINTER)('%s is CET', iso => {
    expect(parisStandingStart(iso).abbreviation).toBe('CET');
    expect(parisStandingStart(iso).offset).toBe('+01:00');
    expect(dateLine(iso)).toContain('CET');
  });

  it('reads the real weekday off the date, not a fixed one', () => {
    // 12 March 2026 is a Thursday; 11 June 2026 is a Thursday too, but 10
    // September 2026 is not -- so a fixed "Thursday" would only ever be
    // caught by a date the series does not actually use.
    expect(dateLine('2026-09-10')).toMatch(/^Thursday, 10 September 2026 at 12:30 CEST$/);
    expect(dateLine('2026-03-12')).toMatch(/^Thursday, 12 March 2026 at 12:30 CET$/);
  });

  it('every public draft states the date and time as one computed line', () => {
    const open = archivedSpeaker();
    for (const [file, ctx] of [
      ['toolkit/forum-post-announce.md', { speaker: open, today: '2026-06-20' }],
      ['toolkit/linkedin-post.md', { speaker: open, today: '2026-06-20' }],
      ['toolkit/mailing-list-announce.md', { speaker: open, today: '2026-06-20' }],
    ] as const) {
      const out = substitute(page(file), ctx);
      expect(out).toContain('11 June 2026 at 12:30 CEST');
    }
  });
});

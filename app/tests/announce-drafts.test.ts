/**
 * The ready-to-publish texts, and the two properties that make
 * them safe to draft from the live record rather than a pre-gated feed:
 *
 * - a speaker's biography, portrait and online identities may not appear in
 *   a drafted text until the publication gate has actually opened, exactly
 *   the rule `tools/convener_ops/publication/public_data.py` applies to the public feed
 *   itself, applied to prose rather than an image;
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
import parisStandingStartFixture from '../../tools/tests/fixtures/paris-standing-start.json';
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
// ... a template-regression canary" (`tools/tests/repository/test_site.py`'s own
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
      'handbook/toolkit/forum-post-announce.md',
      'handbook/toolkit/linkedin-post.md',
      'handbook/toolkit/mailing-list-announce.md',
      'handbook/toolkit/recording-announce.md',
    ]) {
      expect(page(file)).not.toMatch(/\{\{\s*(speaker|public)\.time\s*\}\}\s*(CET|CEST)/);
    }
  });
});

describe('the recording announcement (docs/handbook/toolkit/recording-announce.md)', () => {
  const RECORDING_ANNOUNCE = 'handbook/toolkit/recording-announce.md';
  const NOTES = '## Notes for the volunteer posting this';

  function notesOf(out: string): string {
    const [, notes] = out.split(NOTES);
    return notes ?? '';
  }

  function bodyOf(out: string): string {
    return out.split(NOTES)[0]!;
  }

  it(
    'drops the biography line (no marker, no gap) and notes it stays withheld, while the ' +
      'video -- a genuinely required field once the gate is closed -- still shows the loud marker',
    () => {
      // This was the finding itself -- `«missing: public.bio»`
      // used to render straight into the body of a page whose own "Copy to
      // clipboard" button copies exactly that text. A withheld biography now
      // leaves no trace in the body a volunteer pastes, and is named, as
      // finished business rather than a task, in "Notes for the volunteer
      // posting this" instead.
      const pending = archivedSpeaker({ publication: CLOSED_GATE });
      const out = substitute(page(RECORDING_ANNOUNCE), { speaker: pending, today: '2026-06-20' });
      expect(out).not.toContain(BIO);
      expect(out).not.toContain(YOUTUBE);
      expect(bodyOf(out)).not.toMatch(/«missing: public\.bio»/);
      expect(bodyOf(out)).not.toMatch(/\n{3,}/); // no empty gap left behind
      expect(out).toMatch(/«missing: public\.youtube_url»/);
      expect(notesOf(out)).toContain('stays withheld');
    },
  );

  it(
    'drops the forum-thread sentence and flags it as a task when no thread has been opened ' +
      'yet, distinctly from a withheld biography',
    () => {
      const open = archivedSpeaker({ forum_thread: '' });
      const out = substitute(page(RECORDING_ANNOUNCE), { speaker: open, today: '2026-06-20' });
      expect(out).toContain(BIO); // the gate is open -- only the thread is unset
      expect(bodyOf(out)).not.toContain('on the forum thread');
      expect(bodyOf(out)).not.toMatch(/«missing: public\.forum_thread»/);
      const notes = notesOf(out);
      expect(notes).toContain('none has been opened yet, so open one and add its link');
      expect(notes).not.toContain('stays withheld'); // the biography is present -- no note for it
    },
  );

  it('carries the real biography and video once the gate is open, with neither conditional note', () => {
    const open = archivedSpeaker();
    const out = substitute(page(RECORDING_ANNOUNCE), { speaker: open, today: '2026-06-20' });
    expect(out).toContain(BIO);
    expect(out).toContain(YOUTUBE);
    expect(out).not.toMatch(/«missing: /);
    expect(notesOf(out)).not.toContain('stays withheld');
    expect(notesOf(out)).not.toContain('none has been opened yet');
  });

  it('still shows the loud missing marker for a genuinely required field left blank', () => {
    // Contrast case: `title` is not one of the two ordinarily-absent
    // fields above, so its absence must keep looking exactly as
    // unfinished as it always has.
    const noTitle = archivedSpeaker({ title: '' });
    const out = substitute(page(RECORDING_ANNOUNCE), { speaker: noTitle, today: '2026-06-20' });
    expect(out).toMatch(/«missing: public\.title»/);
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

describe('an unopened forum thread (linkedin-post.md, mailing-list-announce.md)', () => {
  // `speaker.forum_thread` shares the same shape as
  // `public.forum_thread` above in both templates -- a sentence written
  // only to carry the link. `forum_announcement` (forum-post-announce.md)
  // is not covered here: it never reads `forum_thread` at all, since it is
  // itself posted on that thread.
  it.each([
    ['handbook/toolkit/linkedin-post.md', 'Join the discussion'],
    ['handbook/toolkit/mailing-list-announce.md', 'on the forum thread'],
  ] as const)('%s drops the forum-thread sentence and flags it as a task when unset', (file, sentence) => {
    const open = archivedSpeaker({ forum_thread: '' });
    const out = substitute(page(file), { speaker: open, today: '2026-06-20' });
    expect(out).not.toContain(sentence);
    expect(out).not.toMatch(/«missing: speaker\.forum_thread»/);
    expect(out).toContain('none has been opened yet, so open one and add its link');
  });

  it.each(['handbook/toolkit/linkedin-post.md', 'handbook/toolkit/mailing-list-announce.md'] as const)(
    '%s carries the real link and no conditional note when a thread is open',
    file => {
      const open = archivedSpeaker();
      const out = substitute(page(file), { speaker: open, today: '2026-06-20' });
      expect(out).toContain('https://forum.example.org/t/77');
      expect(out).not.toContain('none has been opened yet');
    },
  );
});

describe('a drafted date names the real Paris offset, never a hard-coded one', () => {
  // D-14: this used to be a hand-typed SUMMER/WINTER pair of
  // date lists, pinned independently of `tools/tests/publication/test_visual.py`'s own
  // -- and they had already drifted (this list once pinned `2026-06-11` as
  // its "CEST" case, while the Python list pins `2025-06-12`; two different
  // dates for the identical claim). `paris-standing-start.json` is the one
  // list every side now reads -- `tools/tests/
  // test_paris_standing_start_fixture.py` runs the identical cases against
  // Python and `.eleventy.js` -- spanning both sides of both DST
  // transitions, in two different years, so a test that only ever checked
  // one season could not pass by accident.
  it.each(parisStandingStartFixture)(
    '$iso_date resolves to $abbreviation ($offset)',
    ({ iso_date: iso, offset, abbreviation, date_line: line }) => {
      expect(parisStandingStart(iso).abbreviation).toBe(abbreviation);
      expect(parisStandingStart(iso).offset).toBe(offset);
      expect(dateLine(iso)).toBe(line);
    },
  );

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
      ['handbook/toolkit/forum-post-announce.md', { speaker: open, today: '2026-06-20' }],
      ['handbook/toolkit/linkedin-post.md', { speaker: open, today: '2026-06-20' }],
      ['handbook/toolkit/mailing-list-announce.md', { speaker: open, today: '2026-06-20' }],
    ] as const) {
      const out = substitute(page(file), ctx);
      expect(out).toContain('11 June 2026 at 12:30 CEST');
    }
  });
});

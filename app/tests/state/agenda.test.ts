import { describe, it, expect } from 'vitest';
import {
  AGENDA_STATUSES,
  ARCHIVE_GROUPS,
  ARCHIVE_STATUSES,
  eventIdOf,
  findOverlaps,
  nextEditionCode,
} from '../../src/state/agenda';
import { SPEAKER_STATUSES } from '../../src/data/validate';
import type { Speaker, SpeakerStatus } from '../../src/data/types';
import { speaker as double } from '../helpers/data-doubles';

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
const mk = (
  id: string,
  status: SpeakerStatus,
  date: string,
  ed = '',
): Speaker => double({
  id,
  name: id,
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
  status,
  selection: { ballots: [], opened_on: '', decided_on: '' },
  publication: {
    consent: 'pending',
    approved_by: '',
    approved_on: '',
    objections: [],
    outcome: '',
  },
  edition_code: ed,
  date,
  time: '',
  zoom_link: '',
  youtube_url: '',
  forum_thread: '',
  runbook_progress: {},
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
});

describe('agenda', () => {
  it('finds overlaps within window', () => {
    const list = [
      mk('a', 'scheduled', '2026-07-01', 'MRG-1'),
      mk('b', 'scheduled', '2026-08-01', 'MRG-2'),
    ];
    expect(findOverlaps('2026-07-05', list, 7).map(h => h.speaker.id)).toEqual(['a']);
    expect(findOverlaps('2026-07-05', list, 30).map(h => h.speaker.id)).toEqual(['a', 'b']);
    expect(findOverlaps('2026-09-01', list, 7)).toEqual([]);
  });

  it('ignores non-scheduled+ statuses', () => {
    const list = [
      mk('a', 'lead', '2026-07-01', ''),
      mk('b', 'scheduled', '2026-07-01', 'MRG-2'),
    ];
    expect(findOverlaps('2026-07-02', list, 7).map(h => h.speaker.id)).toEqual(['b']);
  });

  it('respects excludeId', () => {
    const list = [mk('b', 'scheduled', '2026-07-01', 'MRG-2')];
    expect(findOverlaps('2026-07-02', list, 7, 'b')).toEqual([]);
  });

  it('skips entries with empty date', () => {
    const list = [mk('a', 'confirmed', '', '')];
    expect(findOverlaps('2026-07-02', list, 7)).toEqual([]);
  });

  it('returns next available edition code', () => {
    const list = [
      mk('a', 'scheduled', '2026-01-01', 'MRG-1'),
      mk('b', 'scheduled', '2026-02-01', 'MRG-3'),
    ];
    expect(nextEditionCode(list, 1)).toBe('MRG-2');
    expect(nextEditionCode(list, 4)).toBe('MRG-4');
  });
});

describe('the boundary between the agenda and the archive', () => {
  /**
   * The rule, and the whole of it: **the agenda holds what still owes you
   * something; the archive holds what is closed.**
   *
   * Written as a rule over *every* status the model has, not over the six
   * that existed on the day it was written. The two screens shared
   * `delivered` and the agenda additionally carried `archived`, so the
   * screen a volunteer opens to see what is coming grew by one line for
   * every event the series had ever run. The consequence of the fix is the
   * point of it: the agenda empties as the work is done.
   */
  it('puts no status on both screens', () => {
    const both = AGENDA_STATUSES.filter(status => ARCHIVE_STATUSES.includes(status));
    expect(both).toEqual([]);
  });

  it('keeps a delivered event on the agenda, because it still owes three things', () => {
    // Attendance, recording, certificates. Archiving is the gesture that
    // says there is nothing left, and it is what moves the record across.
    expect(AGENDA_STATUSES).toContain('delivered');
    expect(ARCHIVE_STATUSES).not.toContain('delivered');
    expect(ARCHIVE_STATUSES).toContain('archived');
    expect(AGENDA_STATUSES).not.toContain('archived');
  });

  it('places every status that has left the working board on exactly one of them', () => {
    // The five columns of the pipeline are where a record is still being
    // worked on; `scheduled` is on the board and on the agenda, which is
    // the one deliberate overlap -- a booked talk is both work in hand and
    // a date in the diary. Everything past it belongs to one screen.
    const onTheBoard: SpeakerStatus[] = ['lead', 'approved', 'invited', 'confirmed', 'scheduled'];
    const unplaced = SPEAKER_STATUSES.filter(
      status =>
        !onTheBoard.includes(status) &&
        !AGENDA_STATUSES.includes(status) &&
        !ARCHIVE_STATUSES.includes(status),
    );
    expect(unplaced).toEqual([]);
  });

  it('derives the archive side from the groups the screen actually draws', () => {
    // So a group added to the screen is on this side of the rule the same
    // day, rather than in a second list somebody has to remember.
    expect([...ARCHIVE_STATUSES]).toEqual(ARCHIVE_GROUPS.flatMap(g => g.statuses));
  });
});

describe('the event id of an edition', () => {
  it('is the edition code lower-cased, and nothing else', () => {
    expect(eventIdOf('MRG-12')).toBe('mrg-12');
    expect(eventIdOf('')).toBe('');
  });
});

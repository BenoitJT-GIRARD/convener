import { describe, it, expect } from 'vitest';
import {
  AGENDA_STATUSES,
  ARCHIVE_GROUPS,
  ARCHIVE_STATUSES,
  BOARD_COLUMNS,
  BOARD_STATUSES,
  eventIdOf,
  findOverlaps,
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

  it('places every status on the board, the agenda or the archive', () => {
    // Read from the board's own columns rather than from a list written
    // here: this test used to name the five columns in its own words, and
    // that is exactly how `delivered` came to be placed on the agenda,
    // taken off the archive, and never looked for on the board.
    const unplaced = SPEAKER_STATUSES.filter(
      status =>
        !BOARD_STATUSES.includes(status) &&
        !AGENDA_STATUSES.includes(status) &&
        !ARCHIVE_STATUSES.includes(status),
    );
    expect(unplaced).toEqual([]);
  });

  it('gives every status that still asks for work a column of its own', () => {
    // The whole of R62: a delivered event owes the attendance, the
    // recording and the certificates, and had nowhere to be worked on. The
    // rule is stated over every status the model has, so a status added
    // tomorrow has to be placed rather than forgotten.
    const closed: SpeakerStatus[] = [...ARCHIVE_STATUSES];
    const working = SPEAKER_STATUSES.filter(status => !closed.includes(status));
    expect([...BOARD_STATUSES].sort()).toEqual([...working].sort());
  });

  it('puts nothing that is closed on the working board', () => {
    const both = BOARD_STATUSES.filter(status => ARCHIVE_STATUSES.includes(status));
    expect(both).toEqual([]);
  });

  it('overlaps the agenda only where the same record is both work and a date', () => {
    // `scheduled` and `delivered`: a booked talk and a talk that has been
    // given are each work in hand and a day in the diary. Anything else
    // appearing on both would be a boundary broken rather than a record
    // seen from two sides.
    const shared = BOARD_STATUSES.filter(status => AGENDA_STATUSES.includes(status));
    expect(shared).toEqual(['scheduled', 'delivered']);
  });

  it('labels every column it draws', () => {
    expect(BOARD_COLUMNS.map(c => c.label)).toEqual([
      'Leads',
      'Approved',
      'Invited',
      'Confirmed',
      'Scheduled',
      'Delivered',
    ]);
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

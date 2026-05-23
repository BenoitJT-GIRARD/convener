import { describe, it, expect } from 'vitest';
import { findOverlaps, nextEditionCode } from '../src/state/agenda';
import type { Speaker, SpeakerStatus } from '../src/data/types';

const mk = (
  id: string,
  status: SpeakerStatus,
  date: string,
  ed = '',
): Speaker => ({
  id,
  name: id,
  gender: 'undisclosed',
  email: '',
  affiliation: '',
  country: '',
  title: '',
  abstract: '',
  source: 'organizer',
  proposed_by: '',
  links: [],
  host: '',
  co_hosts: [],
  status,
  selection: { votes_for: [], decided_on: '' },
  edition_code: ed,
  date,
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

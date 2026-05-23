import { describe, it, expect } from 'vitest';
import { deriveInbox } from '../src/state/inbox';
import type { Speaker, SpeakerStatus } from '../src/data/types';

const baseSpk: Speaker = {
  id: 's',
  name: 'S',
  gender: 'undisclosed',
  email: '',
  affiliation: '',
  country: '',
  title: '',
  abstract: '',
  conflicts_of_interest: '',
  source: 'organizer',
  proposed_by: '',
  links: [],
  host_1: 'alice',
  host_2: 'bob',
  status: 'lead',
  selection: { votes_for: [], decided_on: '' },
  edition_code: '',
  date: '',
  time: '',
  zoom_link: '',
  youtube_url: '',
  forum_thread: '',
  runbook_progress: {},
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
};

const mk = (o: Partial<Speaker>): Speaker => ({ ...baseSpk, ...o });

describe('deriveInbox v2', () => {
  it('shows pending votes to board who have not voted', () => {
    const rows = deriveInbox([baseSpk], 'alice', 'board', '2026-05-23');
    expect(rows.some(r => r.kind === 'vote')).toBe(true);
  });

  it('hides votes from organizers', () => {
    const rows = deriveInbox([baseSpk], 'alice', 'organizer', '2026-05-23');
    expect(rows.some(r => r.kind === 'vote')).toBe(false);
  });

  it('proposer sees their lead through approved/invited even if not host', () => {
    const s = mk({ status: 'approved', host_1: '', host_2: '', proposed_by: 'alice' });
    const rows = deriveInbox([s], 'alice', 'organizer', '2026-05-23');
    expect(rows.some(r => r.label === 'Assign Host 1')).toBe(true);
  });

  it('approved surfaces host_1 then host_2 then invitation (board sees all)', () => {
    const s = mk({ status: 'approved' as SpeakerStatus, host_1: '', host_2: '' });
    const r1 = deriveInbox([s], 'alice', 'board', '2026-05-23');
    expect(r1[0].label).toBe('Assign Host 1');

    const s2 = mk({ status: 'approved' as SpeakerStatus, host_1: 'alice', host_2: '' });
    const r2 = deriveInbox([s2], 'alice', 'board', '2026-05-23');
    expect(r2[0].label).toBe('Assign Host 2');

    const s3 = mk({ status: 'approved' as SpeakerStatus, host_1: 'alice', host_2: 'bob' });
    const r3 = deriveInbox([s3], 'alice', 'board', '2026-05-23');
    expect(r3[0].label).toBe('Send invitation');
  });

  it('confirmed asks for title, abstract, lock-date', () => {
    const s = mk({ status: 'confirmed' as SpeakerStatus });
    const labels = deriveInbox([s], 'alice', 'organizer', '2026-05-23').map(r => r.label);
    expect(labels).toContain('Capture talk title');
    expect(labels).toContain('Capture talk abstract');
    expect(labels).toContain('Lock date, time and edition code');
  });

  it('scheduled surfaces checkbox items only inside T-window', () => {
    const s = mk({
      status: 'scheduled' as SpeakerStatus,
      date: '2026-06-22',
      edition_code: 'MRG-1',
      time: '12:30',
    });
    const labels = deriveInbox([s], 'alice', 'organizer', '2026-05-23').map(r => r.label);
    expect(labels.some(l => l.includes('T-30'))).toBe(true);
    expect(labels.some(l => l.includes('T-14'))).toBe(false);
  });

  it('delivered surfaces required fields and required checkboxes', () => {
    const s = mk({
      status: 'delivered' as SpeakerStatus,
      edition_code: 'MRG-1',
      date: '2026-04-01',
      time: '12:30',
    });
    const labels = deriveInbox([s], 'alice', 'organizer', '2026-05-23').map(r => r.label);
    expect(labels).toContain('Fill Registrations');
    expect(labels).toContain('Fill Live peak');
    expect(labels).toContain('Forum summary posted');
    expect(labels).toContain('Thank-you email sent to speaker');
  });

  it('archived speakers do not generate rows', () => {
    const s = mk({ status: 'archived' as SpeakerStatus, edition_code: 'MRG-1', date: '2026-04-01' });
    expect(deriveInbox([s], 'alice', 'board', '2026-05-23')).toEqual([]);
  });
});

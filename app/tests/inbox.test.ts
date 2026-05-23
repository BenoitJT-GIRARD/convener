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
  source: 'organizer',
  proposed_by: '',
  links: [],
  host: 'alice',
  co_hosts: ['bob', 'carol'],
  status: 'lead',
  selection: { votes_for: [], decided_on: '' },
  edition_code: '',
  date: '',
  zoom_link: '',
  youtube_url: '',
  forum_thread: '',
  runbook_progress: {},
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
};

function mk(overrides: Partial<Speaker>): Speaker {
  return { ...baseSpk, ...overrides };
}

describe('deriveInbox', () => {
  it('shows pending votes to board members who have not voted', () => {
    const rows = deriveInbox([baseSpk], 'alice', 'board', '2026-05-23');
    expect(rows.some(r => r.kind === 'vote')).toBe(true);
  });

  it('hides votes from organizers', () => {
    const rows = deriveInbox([baseSpk], 'alice', 'organizer', '2026-05-23');
    expect(rows.some(r => r.kind === 'vote')).toBe(false);
  });

  it('hides votes from board members who already voted', () => {
    const s = mk({ selection: { votes_for: ['alice'], decided_on: '' } });
    const rows = deriveInbox([s], 'alice', 'board', '2026-05-23');
    expect(rows.some(r => r.kind === 'vote')).toBe(false);
  });

  it('surfaces approved gates as actions for the host', () => {
    const s = mk({ status: 'approved' });
    const rows = deriveInbox([s], 'alice', 'organizer', '2026-05-23');
    expect(rows.filter(r => r.kind === 'action').length).toBe(2);
  });

  it('hides approved gates from a non-host organizer', () => {
    const s = mk({ status: 'approved', host: 'someone-else', co_hosts: [] });
    const rows = deriveInbox([s], 'alice', 'organizer', '2026-05-23');
    expect(rows.length).toBe(0);
  });

  it('board sees all approved gates regardless of host', () => {
    const s = mk({ status: 'approved', host: 'someone-else', co_hosts: [] });
    const rows = deriveInbox([s], 'alice', 'board', '2026-05-23');
    expect(rows.filter(r => r.kind === 'action').length).toBe(2);
  });

  it('surfaces scheduled items only inside their T-window', () => {
    const s = mk({
      status: 'scheduled' as SpeakerStatus,
      date: '2026-06-22',
      edition_code: 'MRG-1',
    });
    // today→date = 30 days
    const rows = deriveInbox([s], 'alice', 'organizer', '2026-05-23');
    const labels = rows.map(r => r.label);
    expect(labels.some(l => l.includes('T-30'))).toBe(true);
    expect(labels.some(l => l.includes('T-14'))).toBe(false);
  });

  it('skips already-checked items', () => {
    const s = mk({
      status: 'scheduled' as SpeakerStatus,
      date: '2026-06-06',
      edition_code: 'MRG-1',
      runbook_progress: {
        'scheduled/T-14/zoom-link': true,
      },
    });
    const rows = deriveInbox([s], 'alice', 'organizer', '2026-05-23');
    const labels = rows.map(r => r.label);
    expect(labels.some(l => l.includes('Zoom link'))).toBe(false);
  });

  it('sorts past-due (negative T) before future items', () => {
    const past = mk({
      id: 'past',
      status: 'scheduled' as SpeakerStatus,
      date: '2026-05-20',
      edition_code: 'MRG-1',
    });
    const future = mk({
      id: 'future',
      status: 'scheduled' as SpeakerStatus,
      date: '2026-06-15',
      edition_code: 'MRG-2',
    });
    const rows = deriveInbox([past, future], 'alice', 'organizer', '2026-05-23');
    const actions = rows.filter(r => r.kind === 'action');
    expect(actions.length).toBeGreaterThan(0);
    // first action should be on the past-due speaker (smaller urgency)
    expect(actions[0].speaker.id).toBe('past');
  });
});

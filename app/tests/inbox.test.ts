import { describe, it, expect } from 'vitest';
import { deriveInbox } from '../src/state/inbox';
import type { Config, Speaker, SpeakerStatus } from '../src/data/types';
import { speaker as double } from './data-doubles';

/** Four active members, so `thresholdFor(4)` is 3. */
const CFG: Config = {
  season: 2026,
  vw_counter: 1,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board: ['alice', 'bob', 'carol', 'dan'].map(login => ({
    login,
    joined_on: '2024-01-01',
    status: 'active' as const,
    unavailable_until: '',
  })),
  nominations: [],
  board_min: 3,
  board_max: 9,
  vote_window_days: 14,
  objection_window_working_days: 3,
  inactivity_months: 6,
  balance_window_months: 12,
  view_count_window_days: 30,
  sla_days: {
    invitation_follow_up: 7,
    summary_after_delivery: 5,
    recording_after_delivery: 10,
  },
  channels: [],
};

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
const baseSpk: Speaker = double({
  id: 's',
  name: 'S',
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
  host_1: 'alice',
  host_2: 'bob',
  status: 'lead',
  selection: { ballots: [], opened_on: '2026-05-01', decided_on: '' },
  publication: { consent: 'pending', approved_by: '', approved_on: '', objections: [], outcome: '' },
  edition_code: '',
  date: '',
  time: '',
  zoom_link: '',
  youtube_url: '',
  forum_thread: '',
  runbook_progress: {},
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
});

const mk = (o: Partial<Speaker>): Speaker => ({ ...baseSpk, ...o });

describe('deriveInbox v2', () => {
  it('shows pending votes to board who have not voted', () => {
    const rows = deriveInbox([baseSpk], CFG, 'alice', 'board', '2026-05-23');
    expect(rows.some(r => r.kind === 'vote')).toBe(true);
  });

  it('hides votes from organizers', () => {
    const rows = deriveInbox([baseSpk], CFG, 'alice', 'organizer', '2026-05-23');
    expect(rows.some(r => r.kind === 'vote')).toBe(false);
  });

  it('the assigned owner sees their lead through approved/invited even if not host', () => {
    const s = mk({ status: 'approved', host_1: '', host_2: '', assigned_to: 'alice' });
    const rows = deriveInbox([s], CFG, 'alice', 'organizer', '2026-05-23');
    expect(rows.some(r => r.label === 'Assign Host 1')).toBe(true);
  });

  it('does not treat a self-reported proposer as the owner', () => {
    // `proposed_by` holds whatever the public form's submitter typed, which
    // may coincide with a login without meaning this is that person's lead.
    // Ownership lives in `assigned_to` alone.
    const s = mk({ status: 'approved', host_1: '', host_2: '', proposed_by: 'alice', assigned_to: '' });
    const rows = deriveInbox([s], CFG, 'alice', 'organizer', '2026-05-23');
    expect(rows).toEqual([]);
  });

  it('approved surfaces host_1 then host_2 then invitation (board sees all)', () => {
    const s = mk({ status: 'approved' as SpeakerStatus, host_1: '', host_2: '' });
    const r1 = deriveInbox([s], CFG, 'alice', 'board', '2026-05-23');
    expect(r1[0].label).toBe('Assign Host 1');

    const s2 = mk({ status: 'approved' as SpeakerStatus, host_1: 'alice', host_2: '' });
    const r2 = deriveInbox([s2], CFG, 'alice', 'board', '2026-05-23');
    expect(r2[0].label).toBe('Assign Host 2');

    const s3 = mk({ status: 'approved' as SpeakerStatus, host_1: 'alice', host_2: 'bob' });
    const r3 = deriveInbox([s3], CFG, 'alice', 'board', '2026-05-23');
    expect(r3[0].label).toBe('Send invitation');
  });

  it('confirmed asks for title, abstract, lock-date', () => {
    const s = mk({ status: 'confirmed' as SpeakerStatus });
    const labels = deriveInbox([s], CFG, 'alice', 'organizer', '2026-05-23').map(r => r.label);
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
    const labels = deriveInbox([s], CFG, 'alice', 'organizer', '2026-05-23').map(r => r.label);
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
    const labels = deriveInbox([s], CFG, 'alice', 'organizer', '2026-05-23').map(r => r.label);
    expect(labels).toContain('Fill Registrations');
    expect(labels).toContain('Fill Live peak');
    expect(labels).toContain('Forum summary posted');
    expect(labels).toContain('Thank-you email sent to speaker');
  });

  it('archived speakers do not generate rows', () => {
    const s = mk({ status: 'archived' as SpeakerStatus, edition_code: 'MRG-1', date: '2026-04-01' });
    expect(deriveInbox([s], CFG, 'alice', 'board', '2026-05-23')).toEqual([]);
  });

  it('surfaces a lead whose ballots already clear the threshold', () => {
    // The state the v3 migration produced: enough yes ballots to be approved,
    // still `status: lead`, and nothing downstream able to move it --
    // `expire_votes` skips a decided vote so it never parks, and `ballot-cast`
    // is the only writer of `approved` so it never advances.
    const cast = (voter: string) => ({
      voter,
      value: 'yes' as const,
      comment: '',
      coi_reason: '',
      date: '2026-05-01',
    });
    const s = mk({
      selection: {
        ballots: [cast('bob'), cast('carol'), cast('dan')],
        opened_on: '2026-05-01',
        decided_on: '',
      },
    });
    const rows = deriveInbox([s], CFG, 'alice', 'board', '2026-05-23');
    expect(rows.map(r => r.label)).toContain('Threshold already reached, still open: S');

    // And to a member who already voted, who would otherwise see nothing.
    const seen = deriveInbox([s], CFG, 'bob', 'board', '2026-05-23');
    expect(seen.map(r => r.label)).toContain('Threshold already reached, still open: S');
  });

  it('sorts a lead the board has already agreed on above the votes still open', () => {
    const cast = (voter: string) => ({
      voter,
      value: 'yes' as const,
      comment: '',
      coi_reason: '',
      date: '2026-05-01',
    });
    const settled = mk({
      id: 'settled',
      name: 'Settled',
      selection: {
        ballots: [cast('bob'), cast('carol'), cast('dan')],
        opened_on: '2026-05-01',
        decided_on: '',
      },
    });
    const rows = deriveInbox([baseSpk, settled], CFG, 'alice', 'board', '2026-05-23');
    expect(rows[0].speaker.id).toBe('settled');
  });

  it('says nothing about a lead the board has not agreed on yet', () => {
    const s = mk({
      selection: {
        ballots: [
          { voter: 'bob', value: 'yes', comment: '', coi_reason: '', date: '2026-05-01' },
        ],
        opened_on: '2026-05-01',
        decided_on: '',
      },
    });
    const labels = deriveInbox([s], CFG, 'alice', 'board', '2026-05-23').map(r => r.label);
    expect(labels).not.toContain('Threshold already reached, still open: S');
    expect(labels).toContain('Vote on lead: S');
  });

  it('decides nothing itself: no config, no claim about a threshold', () => {
    const cast = (voter: string) => ({
      voter,
      value: 'yes' as const,
      comment: '',
      coi_reason: '',
      date: '2026-05-01',
    });
    const s = mk({
      selection: {
        ballots: [cast('bob'), cast('carol'), cast('dan')],
        opened_on: '2026-05-01',
        decided_on: '',
      },
    });
    const labels = deriveInbox([s], null, 'alice', 'board', '2026-05-23').map(r => r.label);
    expect(labels).not.toContain('Threshold already reached, still open: S');
  });

  it('leaves the record exactly as it found it', () => {
    const before = JSON.stringify(baseSpk);
    deriveInbox([baseSpk], CFG, 'alice', 'board', '2026-05-23');
    expect(JSON.stringify(baseSpk)).toBe(before);
  });
});

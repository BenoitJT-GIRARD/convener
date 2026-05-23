import { describe, it, expect } from 'vitest';
import { canTransition, applyTransition } from '../src/state/transitions';
import type { Speaker } from '../src/data/types';

const base: Speaker = {
  id: 'x',
  name: 'X',
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
  host_1: '',
  host_2: '',
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

describe('transitions v2', () => {
  it('allows board to vote on a lead; refuses organizer', () => {
    expect(canTransition(base, 'lead-vote', 'board')).toBe(true);
    expect(canTransition(base, 'lead-vote', 'organizer')).toBe(false);
  });

  it('promotes lead to approved when vote threshold reached', () => {
    const s: Speaker = { ...base, selection: { votes_for: ['a', 'b'], decided_on: '' } };
    const next = applyTransition(s, 'lead-vote', 'c', 3, '2026-05-23');
    expect(next.status).toBe('approved');
    expect(next.selection.votes_for).toContain('c');
    expect(next.selection.decided_on).toBe('2026-05-23');
  });

  it('does not promote below threshold', () => {
    const s: Speaker = { ...base, selection: { votes_for: ['a'], decided_on: '' } };
    const next = applyTransition(s, 'lead-vote', 'b', 3, '2026-05-23');
    expect(next.status).toBe('lead');
    expect(next.selection.votes_for).toEqual(['a', 'b']);
  });

  it('does not double-count repeat votes from same actor', () => {
    const s: Speaker = { ...base, selection: { votes_for: ['a', 'b'], decided_on: '' } };
    const next = applyTransition(s, 'lead-vote', 'a', 3, '2026-05-23');
    expect(next.selection.votes_for).toEqual(['a', 'b']);
    expect(next.status).toBe('lead');
  });

  it('withdraw vote removes login', () => {
    const s: Speaker = { ...base, selection: { votes_for: ['a', 'b'], decided_on: '' } };
    const next = applyTransition(s, 'lead-vote-withdraw', 'a', 3, '2026-05-23');
    expect(next.selection.votes_for).toEqual(['b']);
  });

  it('park / decline-board are board only and only from lead', () => {
    expect(canTransition(base, 'lead-park', 'organizer')).toBe(false);
    expect(canTransition(base, 'lead-park', 'board')).toBe(true);
    expect(canTransition({ ...base, status: 'approved' }, 'lead-park', 'board')).toBe(false);
  });

  it('reactivate goes from parked or decline-board back to lead', () => {
    const parked: Speaker = { ...base, status: 'parked' };
    expect(applyTransition(parked, 'reactivate', '', 3, '2026-05-23').status).toBe('lead');
    const declined: Speaker = { ...base, status: 'decline-board' };
    expect(applyTransition(declined, 'reactivate', '', 3, '2026-05-23').status).toBe('lead');
  });

  it('send-invitation requires host_1 and host_2 set', () => {
    const noHosts: Speaker = { ...base, status: 'approved' };
    expect(canTransition(noHosts, 'send-invitation', 'organizer')).toBe(false);
    const withHosts: Speaker = { ...noHosts, host_1: 'a', host_2: 'b' };
    expect(canTransition(withHosts, 'send-invitation', 'organizer')).toBe(true);
  });

  it('send-invitation moves approved → invited and ticks the gate', () => {
    const s: Speaker = { ...base, status: 'approved', host_1: 'a', host_2: 'b' };
    const next = applyTransition(s, 'send-invitation', '', 3, '2026-05-23');
    expect(next.status).toBe('invited');
    expect(next.runbook_progress['approved/invitation-sent']).toBe(true);
  });

  it('invited-accept → confirmed; invited-decline → decline-speaker', () => {
    const s: Speaker = { ...base, status: 'invited' };
    expect(applyTransition(s, 'invited-accept', '', 3, '2026-05-23').status).toBe('confirmed');
    expect(applyTransition(s, 'invited-decline', '', 3, '2026-05-23').status).toBe('decline-speaker');
  });

  it('lock-date locks date + time + edition', () => {
    const s: Speaker = { ...base, status: 'confirmed' };
    const next = applyTransition(s, 'lock-date', '', 3, '2026-05-23', {
      date: '2026-08-01',
      edition_code: 'MRG-07',
      time: '14:30',
    });
    expect(next.status).toBe('scheduled');
    expect(next.date).toBe('2026-08-01');
    expect(next.edition_code).toBe('MRG-07');
    expect(next.time).toBe('14:30');
  });

  it('finalize-archive moves delivered → archived', () => {
    const s: Speaker = { ...base, status: 'delivered' };
    expect(canTransition(s, 'finalize-archive', 'organizer')).toBe(true);
    expect(applyTransition(s, 'finalize-archive', '', 3, '2026-05-23').status).toBe('archived');
  });

  it('override is board only', () => {
    expect(canTransition(base, 'override', 'organizer')).toBe(false);
    expect(canTransition(base, 'override', 'board')).toBe(true);
  });
});

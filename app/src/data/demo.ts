import type { Speaker, Config } from './types';

const FLAG = 'convener.demo';

export function isDemoMode(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get('demo') === '1' || window.location.hash.includes('demo=1')) {
      localStorage.setItem(FLAG, '1');
      return true;
    }
    return localStorage.getItem(FLAG) === '1';
  } catch {
    return false;
  }
}
export function activateDemoMode(): void {
  try {
    localStorage.setItem(FLAG, '1');
  } catch {
    /* ignore */
  }
}
export function exitDemoMode(): void {
  try {
    localStorage.removeItem(FLAG);
    localStorage.removeItem('convener.token');
  } catch {
    /* ignore */
  }
}

export const DEMO_USER = { login: 'demo' };

export const DEMO_CONFIG: Config = {
  season: 2026,
  vw_counter: 6,
  vote_threshold: 3,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board_members: ['alice', 'bob', 'carol', 'demo'],
};

const blankMetrics = {
  registrations: null,
  live_peak: null,
  youtube_views_30d: null,
  forum_replies: null,
};

export const DEMO_SPEAKERS: Speaker[] = [
  {
    id: 'spk-d01',
    name: 'Alice Martin',
    gender: 'F',
    email: 'alice@example.org',
    affiliation: 'Centre for Neuroscience',
    country: 'FR',
    title: 'Reward learning in semi-naturalistic settings',
    abstract: '',
    conflicts_of_interest: '',
    source: 'form',
    proposed_by: 'community member',
    links: [],
    host_1: '',
    host_2: '',
    status: 'lead',
    selection: { votes_for: ['demo'], decided_on: '' },
    edition_code: '',
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    metrics: blankMetrics,
    notes: '',
  },
  {
    id: 'spk-d02',
    name: 'Anonymous Hernandez',
    gender: 'M',
    email: 'Anonymous@example.org',
    affiliation: 'IDIBAPS Barcelona',
    country: 'ES',
    title: 'Sleep-behaviour coupling in rodents',
    abstract: '',
    conflicts_of_interest: '',
    source: 'outreach',
    proposed_by: 'Anonymous',
    links: [],
    host_1: 'demo',
    host_2: '',
    status: 'invited',
    selection: { votes_for: ['alice', 'bob', 'carol'], decided_on: '2026-05-02' },
    edition_code: '',
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: { 'approved/invitation-sent': true },
    metrics: blankMetrics,
    notes: '',
  },
  {
    id: 'spk-d03',
    name: 'Mei Tanaka',
    gender: 'F',
    email: 'mei@example.org',
    affiliation: 'University of Tokyo',
    country: 'JP',
    title: 'Decision dynamics and prefrontal circuits',
    abstract: 'How prefrontal circuits implement adaptive choice.',
    conflicts_of_interest: '',
    source: 'organizer',
    proposed_by: 'demo',
    links: [],
    host_1: 'demo',
    host_2: 'alice',
    status: 'scheduled',
    selection: { votes_for: ['alice', 'bob', 'carol'], decided_on: '2026-04-10' },
    edition_code: 'MRG-05',
    date: '2026-07-09',
    time: '12:30',
    zoom_link: 'https://zoom.us/REPLACE',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {
      'approved/invitation-sent': true,
      'scheduled/T-30/visuals': true,
      'scheduled/T-21/linkedin': true,
    },
    metrics: blankMetrics,
    notes: '',
  },
  {
    id: 'spk-d04',
    name: 'Aisha Patel',
    gender: 'F',
    email: 'aisha@example.org',
    affiliation: 'University of Edinburgh',
    country: 'UK',
    title: 'Behavioural variability across the estrous cycle',
    abstract: '',
    conflicts_of_interest: '',
    source: 'form',
    proposed_by: 'community member',
    links: [],
    host_1: '',
    host_2: '',
    status: 'parked',
    selection: { votes_for: [], decided_on: '' },
    edition_code: '',
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    metrics: blankMetrics,
    notes: 'Strong fit; revisit next season',
  },
  {
    id: 'spk-d05',
    name: 'Anonymous',
    gender: 'M',
    email: 'Anonymous@example.org',
    affiliation: 'Anonymous',
    country: 'Germany',
    title: 'Depressive-like behaviours in rodents',
    abstract: '',
    conflicts_of_interest: '',
    source: 'organizer',
    proposed_by: 'Anonymous',
    links: [],
    host_1: 'demo',
    host_2: 'carol',
    status: 'archived',
    selection: { votes_for: ['alice', 'bob', 'carol'], decided_on: '2026-01-12' },
    edition_code: 'MRG-02',
    date: '2026-03-12',
    time: '12:30',
    zoom_link: '',
    youtube_url: 'https://youtube.com/watch?v=def',
    forum_thread: '',
    runbook_progress: {
      'approved/invitation-sent': true,
      'delivered/forum-summary': true,
      'delivered/thank-you': true,
    },
    metrics: { registrations: 52, live_peak: 41, youtube_views_30d: 108, forum_replies: 8 },
    notes: '',
  },
];

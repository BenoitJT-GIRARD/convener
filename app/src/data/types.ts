export type SpeakerStatus =
  | 'lead' | 'approved' | 'invited' | 'confirmed'
  | 'scheduled' | 'delivered' | 'wrapped' | 'archived'
  | 'parked' | 'decline-board' | 'decline-speaker';

export type Gender = 'M' | 'F' | 'NB' | 'undisclosed';

export interface SpeakerMetrics {
  registrations: number | null;
  live_peak: number | null;
  youtube_views_30d: number | null;
  forum_replies: number | null;
}

export interface SpeakerSelection {
  votes_for: string[];
  decided_on: string;
}

export interface Speaker {
  id: string;
  name: string;
  gender: Gender;
  email: string;
  affiliation: string;
  country: string;

  title: string;
  abstract: string;

  source: 'form' | 'outreach' | 'organizer';
  proposed_by: string;
  links: string[];

  host: string;
  co_hosts: string[];

  status: SpeakerStatus;
  selection: SpeakerSelection;

  edition_code: string;
  date: string;

  zoom_link: string;
  youtube_url: string;
  forum_thread: string;

  runbook_progress: Record<string, boolean>;
  metrics: SpeakerMetrics;
  notes: string;
}

export interface Config {
  season: number;
  vw_counter: number;
  vote_threshold: number;
  overlap_window_days: number;
  board_members: string[];
}

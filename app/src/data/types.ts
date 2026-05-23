export type SpeakerStatus =
  | 'lead' | 'approved' | 'invited' | 'confirmed'
  | 'scheduled' | 'delivered' | 'archived'
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
  conflicts_of_interest: string;

  source: 'form' | 'outreach' | 'organizer';
  proposed_by: string;
  links: string[];

  host_1: string;
  host_2: string;

  status: SpeakerStatus;
  selection: SpeakerSelection;

  edition_code: string;
  date: string;
  time: string;

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
  seminar_duration_minutes: number;
  board_members: string[];
}

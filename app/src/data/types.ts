export type SpeakerStatus =
  | 'lead' | 'approved' | 'invited' | 'confirmed' | 'scheduled'
  | 'parking-lot' | 'declined';
export type EventStatus = 'upcoming' | 'delivered' | 'wrapped' | 'archived';

export interface Speaker {
  id: string;
  name: string;
  status: SpeakerStatus;
  owner: string;
  email: string;
  affiliation: string;
  country: string;
  topic: string;
  source: 'form' | 'outreach' | 'organizer';
  proposed_by: string;
  links: string[];
  selection: { votes_for: string[]; decided_on: string };
  next_action: string;
  next_action_date: string;
  event_id: string;
  notes: string;
}

export interface EventMetrics {
  registrations: number | null;
  live_peak: number | null;
  youtube_views_30d: number | null;
  forum_replies: number | null;
}

export interface VwsEvent {
  id: string;
  speaker_id: string;
  title: string;
  date: string;
  status: EventStatus;
  season: number;
  event_owner: string;
  co_hosts: string[];
  zoom_link: string;
  youtube_url: string;
  forum_thread: string;
  metrics: EventMetrics;
  /** progress of the T-minus runbook: map of step key -> checked */
  runbook_progress?: Record<string, boolean>;
}

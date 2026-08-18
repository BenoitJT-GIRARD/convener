export type SpeakerStatus =
  | 'lead' | 'approved' | 'invited' | 'confirmed'
  | 'scheduled' | 'delivered' | 'archived'
  | 'parked' | 'decline-board' | 'decline-speaker';

export type Gender = 'M' | 'F' | 'NB' | 'undisclosed';

export const CAREER_STAGES = [
  'phd', 'postdoc', 'independent', 'group-leader', 'other', 'undisclosed',
] as const;
export type CareerStage = (typeof CAREER_STAGES)[number];
export function isCareerStage(v: string): v is CareerStage {
  return (CAREER_STAGES as readonly string[]).includes(v);
}

export interface SpeakerMetrics {
  registrations: number | null;
  live_peak: number | null;
  youtube_views_30d: number | null;
  forum_replies: number | null;
}

export const BALLOT_VALUES = ['yes', 'abstain', 'recused'] as const;
export type BallotValue = (typeof BALLOT_VALUES)[number];
export function isBallotValue(v: string): v is BallotValue {
  return (BALLOT_VALUES as readonly string[]).includes(v);
}

export interface Ballot {
  voter: string;
  value: BallotValue;
  /** Optional on every ballot. Asked for by the Board so a decision can be read
   *  years later without asking whoever cast it. */
  comment: string;
  /** Required when value is 'recused'. A recusal without a written reason is
   *  not recorded — see governance.ts. */
  coi_reason: string;
  date: string;
}

export interface SpeakerSelection {
  ballots: Ballot[];
  opened_on: string;
  decided_on: string;
}

export type PublicationConsent = 'granted' | 'refused' | 'pending';

export interface PublicationObjection {
  member: string;
  reason: string;
  date: string;
}

export interface Publication {
  consent: PublicationConsent;
  approved_by: string;
  approved_on: string;
  objections: PublicationObjection[];
  outcome: 'published' | 'withheld' | '';
}

export interface BoardMember {
  login: string;
  joined_on: string;
  status: 'active' | 'inactive';
  /** Inclusive end date of a declared absence. Empty when available. */
  unavailable_until: string;
}

export interface Nomination {
  candidate: string;
  sponsor: string;
  opened_on: string;
  objections: PublicationObjection[];
  outcome: 'accepted' | 'deferred' | 'waiting' | '';
}

export interface Speaker {
  id: string;
  name: string;
  gender: Gender;
  career_stage: CareerStage;
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
  publication: Publication;

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
  overlap_window_days: number;
  seminar_duration_minutes: number;
  /** Replaces the flat board_members list. */
  board: BoardMember[];
  nominations: Nomination[];
  board_min: number;
  board_max: number;
  vote_window_days: number;
  objection_window_working_days: number;
  inactivity_months: number;
  balance_window_months: number;
  sla_days: {
    lead_decision: number;
    invitation_follow_up: number;
    summary_after_delivery: number;
    recording_after_delivery: number;
  };
}

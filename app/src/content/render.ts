import { publishedAlwaysWording, publishedOnConsentWording } from '../state/consent';
import type { Speaker } from '../data/types';

export interface SubstitutionContext {
  speaker?: Speaker;
  host?: string;
  today?: string;
}

const MISSING = (path: string) => `«missing: ${path}»`;

interface Resolved {
  /** What this repository publishes, composed from the field classification
   *  in `state/consent.ts` rather than restated in prose. A template that
   *  tells a speaker what would go online reads it from here, so the message
   *  and the gate cannot drift: adding a field to `PUBLISHABLE_ON_CONSENT`
   *  changes the sentence the next speaker is sent. */
  consent?: { published_always: string; published_on_consent: string };
  speaker?: Record<string, string>;
  host_1?: { name: string };
  host_2?: { name: string };
  proposed_by?: { name: string };
  today?: string;
}

function buildContext(ctx: SubstitutionContext): Resolved {
  const r: Resolved = {
    consent: {
      published_always: publishedAlwaysWording(),
      published_on_consent: publishedOnConsentWording(),
    },
  };
  if (ctx.speaker) {
    const s = ctx.speaker;
    const first_name = (s.name || '').split(' ')[0];
    r.speaker = {
      id: s.id,
      name: s.name,
      first_name,
      email: s.email,
      affiliation: s.affiliation,
      country: s.country,
      gender: s.gender,
      title: s.title,
      abstract: s.abstract,
      edition_code: s.edition_code,
      date: s.date,
      time: s.time,
      zoom_link: s.zoom_link,
      youtube_url: s.youtube_url,
      forum_thread: s.forum_thread,
    };
    r.host_1 = { name: s.host_1 };
    r.host_2 = { name: s.host_2 };
    r.proposed_by = { name: s.proposed_by };
  }
  if (ctx.today) r.today = ctx.today;
  return r;
}

type ResolvedValue =
  | Resolved
  | Record<string, string>
  | { name: string }
  | string
  | undefined;

export function substitute(text: string, ctx: SubstitutionContext): string {
  const resolved = buildContext(ctx);
  return text.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, path) => {
    const parts = path.split('.');
    let cur: ResolvedValue = resolved;
    for (const p of parts) {
      if (cur && typeof cur === 'object' && p in cur) cur = (cur as Record<string, ResolvedValue>)[p];
      else return MISSING(path);
    }
    if (cur === null || cur === undefined || cur === '') return MISSING(path);
    return String(cur);
  });
}

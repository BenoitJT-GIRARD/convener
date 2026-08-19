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
      // The introduction script reads this out. It is the speaker's own
      // sentences, kept as they wrote them: a biography this repository
      // rephrased would be a biography nobody had agreed to.
      bio: s.bio,
      title: s.title,
      abstract: s.abstract,
      edition_code: s.edition_code,
      date: s.date,
      time: s.time,
      zoom_link: s.zoom_link,
      youtube_url: s.youtube_url,
      forum_thread: s.forum_thread,
      // The one wrap-up number a message quotes back to the speaker. It is
      // recorded on the delivered checklist above the thank-you that reads
      // it, so an empty one is a line not yet filled in rather than a value
      // to invent: it renders as the missing marker, and nothing here
      // substitutes a plausible-looking zero for it.
      live_peak: s.metrics.live_peak === null ? '' : String(s.metrics.live_peak),
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
    // A path that stops on a branch rather than a leaf -- `{{speaker}}`, the
    // vocabulary four toolkit pages were written in before this -- used to
    // reach `String(cur)` and put the literal text "[object Object]" in front
    // of a speaker. It is the same failure as a name nobody feeds, so it gets
    // the same visible marker: a template written against a vocabulary the
    // renderer does not have must look broken, not merely read oddly.
    if (typeof cur === 'object') return MISSING(path);
    return String(cur);
  });
}

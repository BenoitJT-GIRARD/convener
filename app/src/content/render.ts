import {
  publishedAlwaysWording,
  publishedOnConsentWording,
  spokenRecordingNotice,
  toPublicFields,
  type PublicSpeakerFields,
} from '../state/consent';
import { dateLine } from '../state/derived';
import type { Speaker } from '../data/types';

export interface SubstitutionContext {
  speaker?: Speaker;
  host?: string;
  today?: string;
}

const MISSING = (path: string) => `«missing: ${path}»`;

/**
 * The public signup address, mirrored byte-for-byte against Python's
 * `tools/convener_ops/registration.SIGNUP_BASE` -- pinned by
 * `tools/tests/fixtures/signup-link.json`'s own `signup_base`, the D-14
 * discipline `certificate-verification.json` and `governance-cases.json`
 * already use.
 *
 * Task 6: this used to be a `HashRouter` fragment
 * (`App.tsx`'s `path="/signup/:eventId"`, the convention
 * `survey_invite.SURVEY_BASE` still uses for its own address --
 * `certificate.VERIFICATION_BASE` used to as well, until task 7 moved
 * certificate verification onto its own island too, keeping the fragment
 * for a reason this address does not share: see that constant's own
 * comment) -- registration left that route for an island mounted on the
 * public event page, so this now points at that page's own address
 * instead: `site/src/event.njk`'s permalink, `/events/<event id>/`
 * (D-19).
 */
const SIGNUP_BASE = 'https://example-instance.github.io/example-showcase/events/';

/**
 * The R-5 rule (`tools/convener_ops/platform.py::find_speaker`) computed here
 * rather than left for a volunteer to fill in: "`event_id` is
 * `edition_code`, lower-cased. Nothing else." A hand-filled event id in a
 * *public* announcement is exactly the shape this project refuses
 * everywhere else -- it depends on somebody remembering, and getting it
 * right -- and getting it wrong publishes a dead registration link under
 * the organisation's name. `''` (never a URL with nothing after the base)
 * when `editionCode` is blank, so an incomplete Speaker record still
 * renders the `«missing: speaker.signup_link»` marker, the same as every
 * other derived field on this record.
 */
function signupLink(editionCode: string): string {
  if (!editionCode) return '';
  return `${SIGNUP_BASE}${encodeURIComponent(editionCode.toLowerCase())}/`;
}

interface Resolved {
  /** What this repository publishes, composed from the field classification
   *  in `state/consent.ts` rather than restated in prose. A template that
   *  tells a speaker what would go online reads it from here, so the message
   *  and the gate cannot drift: adding a field to `PUBLISHABLE_ON_CONSENT`
   *  changes the sentence the next speaker is sent. */
  consent?: {
    published_always: string;
    published_on_consent: string;
    spoken_recording: string;
  };
  speaker?: Record<string, string>;
  /** The gated projection (`state/consent.ts::toPublicFields`), for a
   *  template that drafts something meant to leave the team -- see that
   *  function's own docstring. Never built from `speaker` directly: every
   *  field here has already passed the publication gate, so a template
   *  reading `{{ public.… }}` cannot quote a withheld biography or link an
   *  unconsented profile whatever it asks for. */
  public?: PublicSpeakerFields & { signup_link: string; when: string };
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
      spoken_recording: spokenRecordingNotice(),
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
      signup_link: signupLink(s.edition_code),
      // "Thursday, 12 March 2026 at 12:30 CET" -- the real Europe/Paris
      // offset for this edition's own date, computed rather than a hand-typed
      // zone label (`state/derived.ts::dateLine`'s own docstring). Every
      // template stating a date and time together reads this rather than
      // pasting `{{ speaker.date }}` beside a literal "CET": the reference
      // poster's own defect, hard-typing the zone regardless of season, was
      // wrong for three of this project's own five fixture editions.
      when: dateLine(s.date),
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
    r.public = { ...toPublicFields(s), signup_link: signupLink(s.edition_code), when: dateLine(s.date) };
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

/** The `{{ consent.… }}` group, and only it. */
const CONSENT_ONLY = /\{\{\s*consent\.(\w+)\s*\}\}/g;

/**
 * Resolve what the classification composes, with no speaker in hand.
 *
 * `substitute` is given a speaker at the point of action and leaves the raw
 * `{{ speaker.name }}` placeholders alone everywhere else, so that the
 * Templates screen shows a volunteer a template rather than a page of missing
 * markers. The `consent.…` group does not depend on a speaker -- it is read
 * off `state/consent.ts` -- and one of its phrases is a sentence a host reads
 * out loud. A host reading the intro script on the Templates screen must see
 * the sentence, not the token: a placeholder in the middle of spoken prose is
 * either read aloud or improvised around, and both are worse than the drift
 * this replaced.
 */
export function substituteConsent(text: string): string {
  const resolved = buildContext({}).consent!;
  return text.replace(CONSENT_ONLY, (whole, leaf: string) =>
    leaf in resolved ? resolved[leaf as keyof typeof resolved] : whole,
  );
}

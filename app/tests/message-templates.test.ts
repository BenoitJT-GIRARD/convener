/**
 * The messages the series sends, and the vocabulary they are written in.
 *
 * Three claims, all made against the real files under `docs/` rather than
 * against a fixture of what they are supposed to say.
 *
 * 1. **Every substitution in every page the app serves resolves.** This is
 *    checked over the whole served tree, walked with the build's own rule
 *    (`scripts/handbook-files.mjs`), and not over a list of the files that
 *    were broken on the day this was written. Four toolkit pages had drifted
 *    into a vocabulary the renderer never had -- `{{speaker}}` resolved to an
 *    object, `{{registration_link}}` to nothing -- and nothing failed, because
 *    a Markdown file has no way of failing. It has one now: a page added
 *    tomorrow with a token nobody feeds fails here rather than in a volunteer's
 *    outbox.
 *
 * 2. **Each of the three new messages is attached to the step it belongs to.**
 *    A template a volunteer has to go looking for in a folder is a template
 *    nobody uses, so the assertion is not that the file exists but that the
 *    journey hands it over at the moment the work is due.
 *
 * 3. **No message announces the publication of a recording that nobody has
 *    agreed to.** The thank-you used to promise every speaker that their
 *    recording would go up on YouTube, before the question had been asked;
 *    the publication gate says that is not ours to announce. The promise is
 *    gone from the thank-you, and the message that does announce a published
 *    video says out loud that it cannot be sent until the answer is recorded.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, beforeAll } from 'vitest';
import { CONTENT_REGISTRY } from '../src/content/registry';
import { substitute } from '../src/content/render';
import { PHASES, itemByKey } from '../src/state/phases';
import type { Speaker } from '../src/data/types';
import { speaker as double } from './data-doubles';
// The rule the build actually applies, so the sweep below covers exactly the
// pages a volunteer can open and no more.
import { walk } from '../scripts/handbook-files.mjs';

const DOCS = resolve(__dirname, '../../docs');

const PROPOSAL_KEY = 'toolkit/emails/proposal-received';
const PROMOTION_KEY = 'toolkit/emails/promotion-starting';
const VIDEO_KEY = 'toolkit/emails/video-online';
const THANKS_KEY = 'toolkit/emails/thank-you';

/** The three, with the journey step each one is attached to. */
const ATTACHED: readonly [string, string][] = [
  [PROPOSAL_KEY, 'lead/acknowledge-proposal'],
  [PROMOTION_KEY, 'scheduled/T-21/promotion-starting'],
  [VIDEO_KEY, 'delivered/video-online'],
];

function page(relative: string): string {
  return readFileSync(resolve(DOCS, relative), 'utf-8');
}

function source(key: string): string {
  return page(CONTENT_REGISTRY[key].file);
}

/** A record with every field filled, so that a token left unresolved can only
 *  be a token the renderer does not know -- never a blank on the record. */
function invented(): Speaker {
  return double({
    id: 'sp-x',
    name: 'Wren Ashgrove',
    email: 'wren@example.org',
    affiliation: 'Institute of Invented Things',
    country: 'Estonia',
    title: 'Counting what nobody counted',
    abstract: 'An abstract about counting what nobody counted.',
    bio: 'Wren studies things nobody has counted.',
    proposed_by: 'Robin Wexford',
    edition_code: 'MRG-999',
    date: '2026-11-12',
    time: '12:30',
    zoom_link: 'https://zoom.example.org/j/999',
    youtube_url: 'https://youtu.be/invented',
    forum_thread: 'https://forum.example.org/t/999',
    host_1: 'alice',
    host_2: 'bob',
    metrics: { registrations: 120, live_peak: 64, youtube_views_30d: 300, forum_replies: 12 },
  });
}

let servedPages: string[];
beforeAll(async () => {
  servedPages = (await walk(DOCS))
    .map((p: string) => p.split('\\').join('/'))
    .filter((p: string) => p.endsWith('.md'));
});

describe('every page the app serves is written in a vocabulary the app resolves', () => {
  it('walks a tree with the toolkit in it, so an empty walk cannot pass this suite', () => {
    expect(servedPages).toContain('toolkit/index.md');
    expect(servedPages.filter(p => p.startsWith('toolkit/emails/')).length).toBeGreaterThan(10);
  });

  it('leaves no unresolved substitution anywhere under docs/', () => {
    // Two ways a token fails, and both are checked: a name nobody feeds shows
    // the missing marker, and a name that stops on a branch of the context
    // rather than a value -- `{{speaker}}` -- used to render as the literal
    // text "[object Object]". The second is the one that had gone unnoticed
    // in four pages, because it reads as content rather than as a failure.
    const broken = servedPages.filter(p => {
      const out = substitute(page(p), { speaker: invented(), today: '2026-11-12' });
      return /«missing: [\w.]/.test(out) || out.includes('[object Object]');
    });
    expect(broken).toEqual([]);
  });

  it('says in the index how a value that is filled in by hand is written', () => {
    // Square brackets, not braces: a hand-filled blank that looks like a
    // substitution is a substitution the workspace appears to have failed at.
    const index = page('toolkit/index.md');
    expect(index).toMatch(/square\s+\*\*brackets\*\*|\*\*square\s+brackets\*\*/);
    expect(index).not.toContain('{{speaker}}');
  });
});

describe('the three missing messages', () => {
  it.each(ATTACHED)('%s is a handbook page like every other template', key => {
    expect(CONTENT_REGISTRY[key]).toEqual({ file: `${key}.md`, anchor: null });
    expect(source(key).length).toBeGreaterThan(400);
  });

  it.each(ATTACHED)('%s is handed over by the step it belongs to (%s)', (key, itemKey) => {
    const item = itemByKey(itemKey);
    expect(item).toBeDefined();
    expect(item!.contentKey).toBe(key);
  });

  it.each(ATTACHED)('%s is listed on the templates index page', key => {
    expect(page('toolkit/index.md')).toContain(`(emails/${key.slice('toolkit/emails/'.length)}.md)`);
  });

  it('names every step of the journey that carries a template in the registry', () => {
    // A `contentKey` pointing at nothing renders as "Missing" inside the
    // checklist, where the volunteer has no way to tell whether the template
    // was never written or the key was mistyped.
    for (const phase of PHASES) {
      for (const item of phase.items) {
        if (item.contentKey === undefined) continue;
        expect(CONTENT_REGISTRY[item.contentKey]).toBeDefined();
      }
    }
  });
});

describe('the acknowledgement is the first thing an outside person receives', () => {
  it('is addressed to whoever sent the proposal, not to the speaker', () => {
    expect(source(PROPOSAL_KEY)).toContain('{{ proposed_by.name }}');
  });

  it('says what happens next and roughly when, and that an answer comes either way', () => {
    const text = source(PROPOSAL_KEY);
    expect(text).toMatch(/what happens next/i);
    expect(text).toMatch(/two to three weeks/i);
    expect(text).toMatch(/either way/i);
  });

  it('promises a window rather than a date, so a change of configuration cannot make it a lie', () => {
    // The board's target lives in `sla_days.lead_decision`, which is
    // configuration and can be edited. A message naming a day would be a
    // promise the record never made.
    expect(source(PROPOSAL_KEY)).not.toMatch(/\bwithin 14 days\b/i);
  });
});

describe('nothing announces a publication nobody agreed to', () => {
  it('the thank-you no longer tells a speaker their recording is going on YouTube', () => {
    const text = source(THANKS_KEY);
    expect(text).not.toMatch(/recording will go up/i);
    // It announces the question instead of its answer, and points at the one
    // message that asks it properly.
    expect(text).toMatch(/ask whether we may publish/i);
    expect(text).toContain('consent-request.md');
  });

  it('the video message says it cannot be sent before the answer is recorded', () => {
    const text = source(VIDEO_KEY);
    expect(text).toContain('consent-request.md');
    expect(text).toMatch(/permission/i);
  });

  it('the step that hands the video message over carries the same warning', () => {
    const item = itemByKey('delivered/video-online');
    expect(item!.note).toMatch(/agreed/i);
  });

  it('the promotion message leaves the recording alone entirely', () => {
    // Three weeks before the talk there is no recording, and a sentence about
    // one in a promotion e-mail is an answer collected by ambush.
    const body = source(PROMOTION_KEY).split('## Notes for the volunteer')[0];
    expect(body).not.toMatch(/YouTube|recording/i);
  });
});

describe('the discussion summary is written from notes, not from a tool', () => {
  const SUMMARY_KEY = 'toolkit/forum-post-summary';

  it('no page the app serves promises an automatic transcript', () => {
    // The transcript came from a paid feature of a meeting platform the
    // series no longer has. A half-removed procedure is worse than the old
    // one: it sends a volunteer looking for a tool that is not there. The
    // sweep is over the whole served tree, not over the two pages that
    // mentioned it, so a page written next month cannot bring it back.
    const promising = servedPages.filter(p => /transcript|transcription|auto-?caption/i.test(page(p)));
    expect(promising).toEqual([]);
  });

  it('tells the note-taker what to write down while co-hosting', () => {
    const after = page('workflow/4-after.md');
    expect(after).toMatch(/who holds the notes/i);
    expect(after).toMatch(/forum/i);
  });

  it('keeps the draft going to the speaker before it is posted', () => {
    expect(source(SUMMARY_KEY)).toMatch(/before posting it|before you post it/i);
    expect(page('workflow/4-after.md')).toMatch(/shown to the speaker/i);
  });

  it('puts the assistant after the procedure ends, never inside it', () => {
    // Placement is the requirement, not the wording: a volunteer who wants
    // nothing to do with an assistant must be able to read the procedure to
    // its end without meeting one as a step. So the only mention sits below
    // the final checks, under a heading that says it is optional.
    const text = source(SUMMARY_KEY);
    const [procedure, optional] = text.split(/^## Optional/m);
    expect(optional).toBeDefined();
    expect(procedure).not.toMatch(/\bAI\b|assistant|prompt/i);
    expect(optional).toMatch(/no account|nothing here needs an account/i);
    expect(optional).toMatch(/complete without this section/i);
  });
});

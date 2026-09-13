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
import { CONTENT_REGISTRY } from '../../src/content/registry';
import { substitute } from '../../src/content/render';
import { PHASES, itemByKey } from '../../src/state/phases';
import {
  config as configDouble,
  filledSpeaker as invented,
  speaker as double,
} from '../helpers/data-doubles';
import type { Speaker } from '../../src/data/types';
// The rule the build actually applies, so the sweep below covers exactly the
// pages a volunteer can open and no more.
import { walk } from '../../scripts/handbook-files.mjs';

const DOCS = resolve(__dirname, '../../../docs');

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

let servedPages: string[];
beforeAll(async () => {
  servedPages = (await walk(DOCS))
    .map((p: string) => p.split('\\').join('/'))
    .filter((p: string) => p.endsWith('.md'));
});

describe('every page the app serves is written in a vocabulary the app resolves', () => {
  it('walks a tree with the toolkit in it, so an empty walk cannot pass this suite', () => {
    expect(servedPages).toContain('handbook/toolkit/index.md');
    expect(servedPages.filter(p => p.startsWith('handbook/toolkit/emails/')).length).toBeGreaterThan(10);
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
    const index = page('handbook/toolkit/index.md');
    expect(index).toMatch(/square\s+\*\*brackets\*\*|\*\*square\s+brackets\*\*/);
    expect(index).not.toContain('{{speaker}}');
  });
});

describe('the three missing messages', () => {
  it.each(ATTACHED)('%s is a handbook page like every other template', key => {
    expect(CONTENT_REGISTRY[key]).toEqual({ file: `handbook/${key}.md`, anchor: null });
    expect(source(key).length).toBeGreaterThan(400);
  });

  it.each(ATTACHED)('%s is handed over by the step it belongs to (%s)', (key, itemKey) => {
    const item = itemByKey(itemKey);
    expect(item).toBeDefined();
    expect(item!.contentKey).toBe(key);
  });

  it.each(ATTACHED)('%s is listed on the templates index page', key => {
    expect(page('handbook/toolkit/index.md')).toContain(`(emails/${key.slice('toolkit/emails/'.length)}.md)`);
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
  it('greets whoever sent the proposal generically, because the record rarely names them', () => {
    // `{{ proposed_by.name }}` stood here and put a *login* in front of a
    // stranger on every record a board member had entered by hand -- "Dear
    // example-alba". The form asks for the speaker's details and not the
    // sender's, so there is often no name at all, and a salutation a
    // volunteer can overwrite in a second beats a placeholder that reads as
    // a fault.
    const text = source(PROPOSAL_KEY);
    expect(text).toContain('Dear colleague,');
    expect(text).not.toContain('{{ proposed_by.name }}');
    // Still about the proposal that was sent in, and not addressed to the
    // speaker.
    expect(text).toContain('Thank you for proposing {{ speaker.name }}');
    expect(text).not.toContain('{{ speaker.first_name }}');
  });

  it('signs for the series, because no host is named this early', () => {
    // Hosts are chosen once the board has approved a speaker, a whole status
    // later, so `{{ host_1.name }}` here rendered as a visible missing
    // marker above the organisation's own name.
    const text = source(PROPOSAL_KEY);
    expect(text).toContain('The {{ instance.organisation }} team');
    expect(text).not.toContain('{{ host_1.name }}');
  });

  it('says what happens next, and promises nothing it cannot keep', () => {
    // The message itself, not the notes below it: the notes name the promise
    // that was removed, so that the next person to reword this does not put
    // it back.
    const text = source(PROPOSAL_KEY).split('## Notes for the volunteer')[0];
    expect(text).toMatch(/what happens next/i);
    // The three promises that went: an answer either way, a turnaround, and
    // an invitation to chase for one.
    expect(text).not.toMatch(/either way/i);
    expect(text).not.toMatch(/two to three weeks/i);
    expect(text).not.toMatch(/chase us/i);
    // And the policy that replaced them.
    expect(text).toMatch(/more good proposals/i);
    expect(text).toMatch(/than we have slots/i);
    expect(text).toMatch(/it is the speaker we approach/i);
    expect(text).toMatch(/propose again/i);
  });

  it('names no date, so a change of configuration cannot make it a lie', () => {
    // The board's target lives in `vote_window_days`, which is
    // configuration and can be edited. A message naming a day would be a
    // promise the record never made.
    expect(source(PROPOSAL_KEY)).not.toMatch(/\bwithin 14 days\b/i);
  });

  it('is a step the journey offers where it is possible, never a duty on every record', () => {
    // The form gives the sender no address on most records, and the line
    // used to be worded as though one always existed.
    const item = itemByKey('lead/acknowledge-proposal')!;
    expect(item.required).toBeUndefined();
    expect(item.label).toMatch(/where the record gives an address/i);
  });

  it('says the same thing on the page a volunteer plans from', () => {
    // The manual and the message are one policy. A page still promising an
    // answer either way would describe a series this one is not.
    const page = readFileSync(resolve(DOCS, 'handbook/workflow/1-sourcing-selection.md'), 'utf-8');
    expect(page).not.toMatch(/Every candidate gets an answer/);
    expect(page).toMatch(/hears nothing further/i);
    expect(page).toMatch(/proposal-received\.md/);
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
    //
    // `docs/engineering/decisions/` is excluded from this particular sweep, not from the
    // suite: an architecture decision record is reference material about
    // what was built and what was not (see D-12), never an instruction or a
    // message a volunteer acts on -- the genre this check exists to guard.
    // Excluding a whole genre of page is not the same narrow, page-by-page
    // allowlist the comment above warns against; a workflow, toolkit or
    // handbook page that mentioned a transcript would still fail here.
    const promising = servedPages
      .filter(p => !p.startsWith('engineering/decisions/'))
      .filter(p => /transcript|transcription|auto-?caption/i.test(page(p)));
    expect(promising).toEqual([]);
  });

  it('tells the note-taker what to write down while co-hosting', () => {
    const after = page('handbook/workflow/4-after.md');
    expect(after).toMatch(/who holds the notes/i);
    expect(after).toMatch(/forum/i);
  });

  it('keeps the draft going to the speaker before it is posted', () => {
    expect(source(SUMMARY_KEY)).toMatch(/before posting it|before you post it/i);
    expect(page('handbook/workflow/4-after.md')).toMatch(/shown to the speaker/i);
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

describe('the drafts that name an evening follow the negotiation', () => {
  const INVITATION_KEY = 'toolkit/emails/invitation';
  const DETAILS_KEY = 'toolkit/emails/talk-details';

  /** A record part-way through the negotiation: approved, with whatever has
   *  been put to the speaker so far and nothing else. */
  function offering(candidate_dates: Speaker['candidate_dates']): Speaker {
    return double({
      status: 'approved',
      title: 'A talk',
      date: '',
      time: '',
      edition_code: '',
      candidate_dates,
    });
  }

  it('reads as unfinished while no evening has been offered', () => {
    // Which is what it is: the invitation's whole question is "would one of
    // these suit you", and there is nothing yet to ask about.
    const out = substitute(source(INVITATION_KEY), { speaker: offering([]) });
    expect(out).toContain('«missing: speaker.dates_offered»');
  });

  it('names the evening as soon as one is offered, hour and zone included', () => {
    const out = substitute(
      source(INVITATION_KEY),
      { speaker: offering([{ date: '2026-11-05', time: '18:00', answer: '' }]) },
    );
    expect(out).toContain('Thursday, 5 November 2026 at 18:00 CET');
  });

  it('grows with the offer, one evening at a time', () => {
    // The defect R34 records: the placeholders never moved, whatever was
    // added. Each of the three renders is the draft a volunteer would copy
    // at that moment.
    const one = [{ date: '2026-11-05', time: '18:00', answer: '' as const }];
    const two = [...one, { date: '2026-11-12', time: '18:00', answer: '' as const }];
    const three = [...two, { date: '2026-11-19', time: '18:00', answer: '' as const }];
    const draft = (dates: Speaker['candidate_dates']) =>
      substitute(source(INVITATION_KEY), { speaker: offering(dates) });

    expect(draft(one)).toContain('**Thursday, 5 November 2026 at 18:00 CET**?');
    expect(draft(two)).toContain(
      'Thursday, 5 November 2026 at 18:00 CET or Thursday, 12 November 2026 at 18:00 CET',
    );
    expect(draft(three)).toContain(
      'Thursday, 5 November 2026 at 18:00 CET, Thursday, 12 November 2026 at 18:00 CET or ' +
        'Thursday, 19 November 2026 at 18:00 CET',
    );
  });

  it('writes the talk-details message from the evening that was agreed', () => {
    // A confirmed record has no `date` yet -- that is written when the date
    // is locked, a status later -- so this message named a missing field at
    // exactly the moment it is sent.
    const agreed = double({
      status: 'confirmed',
      date: '',
      time: '',
      host_1: 'ada',
      candidate_dates: [
        { date: '2026-11-05', time: '18:00', answer: 'declined' },
        { date: '2026-11-12', time: '18:00', answer: 'accepted' },
      ],
    });
    const out = substitute(source(DETAILS_KEY), { speaker: agreed });
    expect(out).toContain('talk on 2026-11-12');
    expect(out).toContain('Thursday, 12 November 2026 at 18:00 CET');
    expect(out).not.toContain('«missing');
  });
});

describe('the room, and the one message that carries it', () => {
  const REMINDER_KEY = 'toolkit/emails/reminder';
  const PROMOTION = 'toolkit/emails/promotion-starting';

  const SERIES_ROOM = configDouble({
    instructions: 'Join online: https://join.example.test/series\nAccess code: 8842798',
  });

  /** Everything above the volunteer's own notes. A template's notes talk
   *  *about* the message -- naming the registration confirmation it must not
   *  duplicate, for instance -- and a reading about what the speaker is sent
   *  must not be satisfied or broken by them. */
  function bodyOf(rendered: string): string {
    return rendered.split('## Notes for the volunteer')[0];
  }

  function scheduled(overrides: Partial<Speaker> = {}): Speaker {
    return double({
      status: 'scheduled',
      title: 'A talk',
      date: '2027-03-16',
      time: '12:30',
      edition_code: 'MRG-09',
      forum_thread: 'https://forum.example.test/t/1',
      // The reminder signs off as `{{ host_1.name }}`, which resolves from
      // the record rather than from the context's `host`.
      host_1: 'Alice Organiser',
      ...overrides,
    });
  }

  it('gives the speaker the series room when the record carries no link', () => {
    // The gap #96 named: nothing in the journey ever sent the speaker the
    // way into their own seminar. The reminder pointed at "your registration
    // confirmation", which is a message the speaker never receives -- nothing
    // asks them to register for their own talk.
    const out = substitute(source(REMINDER_KEY), {
      speaker: scheduled({ zoom_link: '' }),
      host: 'alice',
      config: SERIES_ROOM,
    });

    expect(out).toContain('https://join.example.test/series');
    expect(out).toContain('Access code: 8842798');
    expect(out).not.toMatch(/«missing: /);
  });

  it('gives the speaker the record’s own link when there is one', () => {
    const out = substitute(source(REMINDER_KEY), {
      speaker: scheduled({ zoom_link: 'https://meet.example.test/j/9' }),
      host: 'alice',
      config: configDouble({ instructions: '' }),
    });

    expect(out).toContain('https://meet.example.test/j/9');
  });

  it('no longer points at a registration confirmation the speaker never gets', () => {
    // Two untruths in one sentence, both removed. The second --
    // "the same room and access code every session uses" -- asserted one
    // instance's room model as though it were a property of the product; it
    // is false of an instance that opens a room per seminar, and the product
    // cannot know which it is talking to. Same shape as the hardcoded
    // "12:30 CET" removed from the line above it.
    const body = bodyOf(source(REMINDER_KEY));

    expect(body).not.toContain('registration confirmation');
    expect(body).not.toContain('every session uses');
  });

  it('keeps the room out of the message written to be forwarded', () => {
    // The promotion says, in its own words, "anything we post is yours to
    // repost". A room link in it is a room anyone can enter without
    // registering -- and this series recognises attendance through
    // registration and nothing else, so such an audience cannot be matched,
    // cannot be certified, and is not covered by the data-protection record.
    const out = substitute(source(PROMOTION), {
      speaker: scheduled({ zoom_link: 'https://meet.example.test/j/9' }),
      host: 'alice',
      config: SERIES_ROOM,
    });

    expect(out).not.toContain('https://meet.example.test/j/9');
    expect(out).not.toContain('https://join.example.test/series');
    expect(out).not.toContain('8842798');
  });

  it('tells the speaker in the promotion that the details are coming', () => {
    // Benoît's own point, and it is not only comfort: a speaker who does not
    // know the details are coming asks for them, and the easiest thing for a
    // volunteer to do then is to paste the room into the reply that is least
    // safe to paste it into.
    const out = substitute(source(PROMOTION), {
      speaker: scheduled(),
      host: 'alice',
      config: SERIES_ROOM,
    });

    expect(out).toMatch(/joining details/i);
    expect(out).toMatch(/few days before|in your reminder/i);
  });

  it('is the reminder, and only the reminder, that carries the token', () => {
    // Non-vacuity in the direction that would be silent. A second template
    // gaining `{{ speaker.room }}` is a second message putting the room in
    // front of somebody, and which messages do that is the whole subject.
    const carrying = Object.keys(CONTENT_REGISTRY)
      .filter(key => key.startsWith('toolkit/emails/'))
      .filter(key => source(key).includes('{{ speaker.room }}'));

    expect(carrying).toEqual([REMINDER_KEY]);
  });
});

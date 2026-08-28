import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { Layout } from '../src/components/Layout';
import { SpeakerPage } from '../src/screens/SpeakerPage';
import { canArchive, standingObjections } from '../src/state/governance';
import { applyTransition, canTransition } from '../src/state/transitions';
import { parseSpeakers, serializeSpeakers, stripHeader } from '../src/data/yaml';
import {
  CONSENT_DECISIONS,
  OBJECTION_RESOLUTIONS,
  type BoardMember,
  type Config,
  type Publication,
  type Speaker,
} from '../src/data/types';
import { speaker as double } from './data-doubles';

/* ------------------------------------------------------------------ *
 * Fixtures
 * ------------------------------------------------------------------ */

function member(login: string): BoardMember {
  return { login, joined_on: '2020-01-01', status: 'active', unavailable_until: '' };
}

function config(overrides: Partial<Config> = {}): Config {
  return {
    season: 2026,
    next_edition_number: 6,
    overlap_window_days: 7,
    seminar_duration_minutes: 90,
    eligibility_share: 0.6666666666666666,
    board: [member('alice'), member('bob'), member('carol')],
    nominations: [],
    board_min: 3,
    board_max: 9,
    vote_window_days: 14,
    // The value instance/data/config.yml carries, and the one G-10 states:
    // three *working* days.
    objection_window_working_days: 3,
    inactivity_months: 6,
    balance_window_months: 12,
    view_count_window_days: 30,
    sla_days: {
      invitation_follow_up: 7,
      summary_after_delivery: 5,
      recording_after_delivery: 10,
    },
    channels: [],
    instructions: '',
    ...overrides,
  };
}

function publication(overrides: Partial<Publication> = {}): Publication {
  return {
    consent: 'pending',
    approved_by: '',
    approved_on: '',
    objections: [],
    outcome: '',
    ...overrides,
  };
}

/** A delivered seminar with the delivered-phase checklist already satisfied,
 *  so the only thing standing between it and the archive is this gate. */
function speaker(overrides: Partial<Speaker> = {}): Speaker {
  return double({
    name: 'Dr Ada Lovelace',
    gender: 'F',
    career_stage: 'independent',
    email: 'ada@example.org',
    affiliation: 'Somewhere',
    country: 'UK',
    title: 'A talk',
    abstract: 'An abstract',
    source: 'outreach',
    proposed_by: 'bob',
    assigned_to: 'bob',
    host_1: 'alice',
    host_2: 'bob',
    status: 'delivered',
    selection: { ballots: [], opened_on: '2025-11-01', decided_on: '2025-11-10' },
    publication: publication(),
    edition_code: 'MRG-05',
    date: '2026-01-05',
    time: '12:30',
    youtube_url: 'https://youtu.be/x',
    forum_thread: 'https://forum/x',
    runbook_progress: {
      // Three weeks before this talk, somebody checked that the speaker was
      // on the forum and signed up to their own seminar. A record where that
      // was never done does not reach the archive at all -- which is the
      // subject of its own test below, not of these.
      'scheduled/T-14/speaker_registered': true,
      'delivered/forum-summary': true,
      'delivered/thank-you': true,
    },
    metrics: { registrations: 40, live_peak: 22, youtube_views_30d: 5, forum_replies: 2 },
    ...overrides,
  });
}

/** Far enough in the past that the objection window has run under any clock
 *  the suite may be running on -- these tests never depend on today's date. */
const LONG_AGO = '2020-01-06';

/* ------------------------------------------------------------------ *
 * canArchive -- the rule itself
 * ------------------------------------------------------------------ */

describe('canArchive', () => {
  const cfg = config();

  it('refuses when no board member has approved', () => {
    const s = speaker({ publication: publication({ consent: 'granted' }) });
    const gate = canArchive(s, cfg, '2026-08-18');
    expect(gate.allowed).toBe(false);
    expect(gate.reason).toMatch(/No board member has approved/);
  });

  it('refuses while the three-working-day objection window is still open', () => {
    // Approved on Thursday 13 August 2026. Three working days later is
    // Tuesday the 18th, so on Monday the 17th the window has not run.
    const s = speaker({
      publication: publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: '2026-08-13',
      }),
    });
    const gate = canArchive(s, cfg, '2026-08-17');
    expect(gate.allowed).toBe(false);
    expect(gate.reason).toContain('2026-08-18');
    expect(canArchive(s, cfg, '2026-08-18').allowed).toBe(true);
  });

  it('counts the window in working days, not calendar days', () => {
    // Approved on Friday 14 August 2026: the weekend does not count, so the
    // window closes on Wednesday the 19th, not Monday the 17th.
    const s = speaker({
      publication: publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: '2026-08-14',
      }),
    });
    expect(canArchive(s, cfg, '2026-08-17').allowed).toBe(false);
    expect(canArchive(s, cfg, '2026-08-18').allowed).toBe(false);
    expect(canArchive(s, cfg, '2026-08-19').allowed).toBe(true);
  });

  it('refuses while an objection stands, however long ago the approval was', () => {
    const s = speaker({
      publication: publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: LONG_AGO,
        objections: [
          { member: 'carol', reason: 'the slides show unpublished data', date: '2020-01-07', resolved_on: '' },
        ],
      }),
    });
    const gate = canArchive(s, cfg, '2026-08-18');
    expect(gate.allowed).toBe(false);
    expect(gate.reason).toContain('carol');
    expect(gate.reason).toContain('unpublished data');
  });

  it('treats an objection with no resolved_on key at all as standing', () => {
    // A hand-edited file that omits the key must read as "still open", never
    // as "settled": the safe direction leaves the talk offline.
    const raw = { member: 'carol', reason: 'wait', date: '2020-01-07' } as unknown as {
      member: string;
      reason: string;
      date: string;
      resolved_on: string;
    };
    const p = publication({ consent: 'granted', approved_by: 'alice', approved_on: LONG_AGO, objections: [raw] });
    expect(standingObjections(p)).toHaveLength(1);
    expect(canArchive(speaker({ publication: p }), cfg, '2026-08-18').allowed).toBe(false);
  });

  it('stops publishing once an objection has been resolved and the rest is in order', () => {
    const s = speaker({
      publication: publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: LONG_AGO,
        objections: [
          { member: 'carol', reason: 'wait', date: '2020-01-07', resolved_on: '2020-01-09' },
        ],
      }),
    });
    expect(canArchive(s, cfg, '2026-08-18').allowed).toBe(true);
  });

  it('refuses when the speaker refused consent', () => {
    const s = speaker({
      publication: publication({ consent: 'refused', approved_by: 'alice', approved_on: LONG_AGO }),
    });
    const gate = canArchive(s, cfg, '2026-08-18');
    expect(gate.allowed).toBe(false);
    expect(gate.reason).toMatch(/refused permission/);
  });

  it('refuses on silence from the speaker, however old the approval is', () => {
    // The heart of the rule. The board's silence becomes permission once the
    // window has run; the speaker's silence never does, at any distance.
    for (const consent of ['pending', ''] as const) {
      const s = speaker({
        publication: publication({ consent, approved_by: 'alice', approved_on: LONG_AGO }),
      });
      for (const today of ['2020-01-07', '2026-08-18', '2099-01-01']) {
        const gate = canArchive(s, cfg, today);
        expect(gate.allowed).toBe(false);
        expect(gate.reason).toMatch(/not given permission/);
      }
    }
  });

  it('allows only when both permissions are in hand', () => {
    const s = speaker({
      publication: publication({ consent: 'granted', approved_by: 'alice', approved_on: LONG_AGO }),
    });
    const gate = canArchive(s, cfg, '2026-08-18');
    expect(gate.allowed).toBe(true);
    expect(gate.reason).toBe('');
  });

  it('always gives a reason a volunteer can read when it refuses', () => {
    // `reason` is displayed beside the disabled button, so an empty one would
    // leave a volunteer with a dead control and no explanation.
    const cases: Publication[] = [
      publication(),
      publication({ consent: 'granted' }),
      publication({ consent: 'refused' }),
      publication({ consent: '' }),
      publication({ consent: 'granted', approved_by: 'alice', approved_on: '2026-08-18' }),
      publication({ consent: 'granted', approved_by: 'alice', approved_on: LONG_AGO, outcome: 'withheld' }),
      publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: LONG_AGO,
        objections: [{ member: 'bob', reason: 'no', date: LONG_AGO, resolved_on: '' }],
      }),
    ];
    for (const p of cases) {
      const gate = canArchive(speaker({ publication: p }), cfg, '2026-08-18');
      if (gate.allowed) continue;
      expect(gate.reason.length).toBeGreaterThan(20);
      expect(gate.reason.trim()).not.toBe('');
    }
  });
});

/* ------------------------------------------------------------------ *
 * The transitions
 * ------------------------------------------------------------------ */

describe('publication transitions', () => {
  const cfg = config();

  it('has no vocabulary for assuming consent', () => {
    // The ambiguous value is not guarded, it is
    // absent. Nothing a transition can carry means "pending", so no code
    // path -- and no elapsed delay -- can arrive at one.
    expect([...CONSENT_DECISIONS]).toEqual(['granted', 'refused']);
    expect(CONSENT_DECISIONS as readonly string[]).not.toContain('pending');
    expect(CONSENT_DECISIONS as readonly string[]).not.toContain('');
  });

  it('has no resolution that publishes', () => {
    expect([...OBJECTION_RESOLUTIONS]).toEqual(['lift', 'withhold']);
    expect(OBJECTION_RESOLUTIONS as readonly string[]).not.toContain('published');
  });

  it('refuses to archive when the gate is shut, with the gate sentence', () => {
    const s = speaker();
    expect(() => applyTransition(s, 'finalize-archive', 'alice', cfg, '2026-08-18')).toThrowError(
      /not given permission/,
    );
  });

  it('publishes and archives when the gate is open', () => {
    const s = speaker({
      publication: publication({ consent: 'granted', approved_by: 'alice', approved_on: LONG_AGO }),
    });
    const next = applyTransition(s, 'finalize-archive', 'alice', cfg, '2026-08-18');
    expect(next.status).toBe('archived');
    expect(next.publication.outcome).toBe('published');
  });

  it('records an approval against the acting member and the day', () => {
    const next = applyTransition(speaker(), 'publication-approve', 'bob', cfg, '2026-08-18');
    expect(next.publication.approved_by).toBe('bob');
    expect(next.publication.approved_on).toBe('2026-08-18');
    // An approval on its own publishes nothing.
    expect(next.publication.outcome).toBe('');
  });

  it('refuses an objection with no written reason', () => {
    expect(() =>
      applyTransition(speaker(), 'publication-object', 'carol', cfg, '2026-08-18', { reason: '  ' }),
    ).toThrowError(/needs a written reason/);
  });

  it('replaces a member’s own standing objection rather than stacking one', () => {
    const s = speaker({
      publication: publication({
        objections: [{ member: 'carol', reason: 'first', date: '2026-08-17', resolved_on: '' }],
      }),
    });
    const next = applyTransition(s, 'publication-object', 'carol', cfg, '2026-08-18', {
      reason: 'second',
    });
    expect(next.publication.objections).toHaveLength(1);
    expect(next.publication.objections[0].reason).toBe('second');
  });

  it('takes a published recording down the moment a member objects', () => {
    // The one ordering the gate cannot cover: publication first, objection
    // after. Leaving `published` standing here would be exactly the
    // contradictory shape the validator used to have to catch.
    const s = speaker({
      status: 'archived',
      publication: publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: LONG_AGO,
        outcome: 'published',
      }),
    });
    const next = applyTransition(s, 'publication-object', 'carol', cfg, '2026-08-18', {
      reason: 'the speaker asked me to check something',
    });
    // Un-published, not `withheld`: one member objecting is not the board
    // resolving to hold a recording back, and the objection recorded
    // alongside is what says why it is offline.
    expect(next.publication.outcome).toBe('');
    const gate = canArchive(next, cfg, '2026-08-18');
    expect(gate.allowed).toBe(false);
    expect(gate.reason).toContain('carol objected');
    expect(gate.reason).not.toContain('The board decided');
  });

  it('keeps the original objection wording when resolving, and stamps the day', () => {
    const s = speaker({
      publication: publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: LONG_AGO,
        objections: [{ member: 'carol', reason: 'unpublished data', date: '2026-08-17', resolved_on: '' }],
      }),
    });
    const next = applyTransition(s, 'publication-resolve', 'alice', cfg, '2026-08-18', {
      resolution: 'lift',
      note: 'speaker replaced the slide',
    });
    expect(next.publication.objections[0].resolved_on).toBe('2026-08-18');
    expect(next.publication.objections[0].reason).toContain('unpublished data');
    expect(next.publication.objections[0].reason).toContain('speaker replaced the slide');
    // Lifting an objection returns the record to the gate; it does not
    // publish anything by itself.
    expect(next.publication.outcome).toBe('');
    expect(next.status).toBe('delivered');
  });

  it('withholds on the other resolution, and lets a later one lift it', () => {
    const s = speaker({
      publication: publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: LONG_AGO,
        objections: [{ member: 'carol', reason: 'no', date: '2026-08-17', resolved_on: '' }],
      }),
    });
    const held = applyTransition(s, 'publication-resolve', 'alice', cfg, '2026-08-18', {
      resolution: 'withhold',
      note: 'board decided not to publish',
    });
    expect(held.publication.outcome).toBe('withheld');
    expect(canArchive(held, cfg, '2026-08-18').allowed).toBe(false);
    expect(canTransition(held, 'publication-resolve', 'board')).toBe(true);

    const lifted = applyTransition(held, 'publication-resolve', 'alice', cfg, '2026-08-20', {
      resolution: 'lift',
      note: 'reconsidered',
    });
    expect(lifted.publication.outcome).toBe('');
    expect(canArchive(lifted, cfg, '2026-08-20').allowed).toBe(true);
  });

  it('makes a consent withdrawn after archiving visible rather than silent', () => {
    const archived = applyTransition(
      speaker({
        publication: publication({ consent: 'granted', approved_by: 'alice', approved_on: LONG_AGO }),
      }),
      'finalize-archive',
      'alice',
      cfg,
      '2026-08-18',
    );
    expect(archived.publication.outcome).toBe('published');

    const withdrawn = applyTransition(archived, 'consent-set', 'alice', cfg, '2026-08-19', {
      consent: 'refused',
    });
    // The refusal is not merely recorded next to a `published` outcome, which
    // would leave the file saying the recording is online with the speaker's
    // blessing. It takes it down, and the gate says so out loud.
    expect(withdrawn.publication.consent).toBe('refused');
    expect(withdrawn.publication.outcome).toBe('');
    const gate = canArchive(withdrawn, cfg, '2026-08-19');
    expect(gate.allowed).toBe(false);
    expect(gate.reason).toMatch(/taken down/);
    // And it does not put words in the board's mouth: the board decided
    // nothing here, so nothing this screen says may claim it did.
    expect(gate.reason).not.toContain('The board decided');
  });

  it('lets a speaker change their mind back without the board having to act', () => {
    // Refusal, then a later grant. The record has to return to the gate, not
    // sit behind a board decision nobody took: `publication-resolve` is the
    // only way to clear a `withheld`, its vocabulary is "resolve the
    // objections", and there are no objections here to resolve.
    const archived = applyTransition(
      speaker({
        publication: publication({ consent: 'granted', approved_by: 'alice', approved_on: LONG_AGO }),
      }),
      'finalize-archive',
      'alice',
      cfg,
      '2026-08-18',
    );
    const withdrawn = applyTransition(archived, 'consent-set', 'alice', cfg, '2026-08-19', {
      consent: 'refused',
    });
    const regranted = applyTransition(withdrawn, 'consent-set', 'alice', cfg, '2026-08-20', {
      consent: 'granted',
    });
    expect(regranted.publication.outcome).toBe('');
    const gate = canArchive(regranted, cfg, '2026-08-20');
    expect(gate.reason).not.toContain('The board decided');
    expect(gate.allowed).toBe(true);
    const republished = applyTransition(regranted, 'finalize-archive', 'alice', cfg, '2026-08-20');
    expect(republished.publication.outcome).toBe('published');
  });

  it('says the board decided only where the board actually decided', () => {
    // `withheld` has one writer left: a board member resolving to withhold.
    const objected = speaker({
      publication: publication({
        consent: 'granted',
        approved_by: 'alice',
        approved_on: LONG_AGO,
        objections: [{ member: 'carol', reason: 'unpublished data', date: LONG_AGO, resolved_on: '' }],
      }),
    });
    const withheld = applyTransition(objected, 'publication-resolve', 'carol', cfg, '2026-08-18', {
      resolution: 'withhold',
      note: 'the board agreed to keep this offline',
    });
    expect(withheld.publication.outcome).toBe('withheld');
    expect(canArchive(withheld, cfg, '2026-08-18').reason).toContain('The board decided');
  });

  it('keeps consent-set, approval, objection and resolution off the organizer path', () => {
    const s = speaker({
      publication: publication({ objections: [{ member: 'carol', reason: 'x', date: LONG_AGO, resolved_on: '' }] }),
    });
    for (const t of ['consent-set', 'publication-approve', 'publication-object', 'publication-resolve'] as const) {
      expect(canTransition(s, t, 'organizer')).toBe(false);
      expect(canTransition(s, t, 'board')).toBe(true);
    }
  });
});

/* ------------------------------------------------------------------ *
 * The screen
 * ------------------------------------------------------------------ */

function encodeUtf8(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function decodeUtf8(b64: string): string {
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, c => c.charCodeAt(0));
  return new TextDecoder('utf-8').decode(bytes);
}

/** A stand-in for the Contents API that enforces the sha precondition on
 *  speakers.yml, like the real one. */
function makeBackend(cfg: Config, initial: Speaker[]) {
  let server = initial;
  let sha = 'spk-0';
  let counter = 0;

  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('memberships')) {
      return Promise.resolve({ ok: true, json: async () => ({ state: 'active' }) });
    }
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      if (opts?.method === 'PUT') {
        const body = JSON.parse(opts.body as string);
        if (body.sha !== sha) {
          return Promise.resolve({ ok: false, status: 409, text: async () => 'stale sha' });
        }
        server = parseSpeakers(stripHeader(decodeUtf8(body.content)));
        sha = `spk-${++counter}`;
        return Promise.resolve({ ok: true, json: async () => ({ content: { sha } }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: encodeUtf8(serializeSpeakers(server)), sha }),
      });
    }
    if (url.includes('config.yml')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: encodeUtf8(JSON.stringify(cfg)), sha: 'cfg-0' }),
      });
    }
    return Promise.resolve({ ok: false, status: 404, text: async () => 'no' });
  });

  return {
    fetchMock,
    /** Somebody else's write landing straight on the remote, behind this
     *  component's back. */
    interlope(next: Speaker[]) {
      server = next;
      sha = `spk-other-${++counter}`;
    },
    current: () => server,
  };
}

function renderSpeaker(backend: { fetchMock: ReturnType<typeof vi.fn> }) {
  vi.stubGlobal('fetch', backend.fetchMock);
  render(
    <MemoryRouter initialEntries={['/speakers/spk-001']}>
      <AuthProvider>
        <DataProvider>
          {/* Layout, not just the screen: the save-error banner lives there,
              and a governance rule firing inside a `mutate` transformation is
              only useful if the volunteer can read it. */}
          <Routes>
            <Route element={<Layout />}>
              <Route path="/speakers/:id" element={<SpeakerPage />} />
            </Route>
          </Routes>
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const PUBLISH = 'Publish the recording and archive';

describe('PublicationGate on the speaker page', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('keeps the publish button disabled and says why, rather than failing on submit', async () => {
    const backend = makeBackend(config(), [
      speaker({
        publication: publication({ consent: 'pending', approved_by: 'alice', approved_on: LONG_AGO }),
      }),
    ]);
    renderSpeaker(backend);

    expect(await screen.findByRole('button', { name: PUBLISH })).toBeDisabled();
    expect(screen.getByText(/not given permission/)).toBeInTheDocument();
    // Nothing was written, and in particular nothing was published.
    expect(backend.current()[0].publication.outcome).toBe('');
  });

  it('names the step in the way, including one from three weeks before the talk', async () => {
    // The volunteer is on the wrap-up screen. What is missing is not on it:
    // pointing at "the required fields of the delivered checklist" would have
    // sent them looking through fields that are all filled in.
    const backend = makeBackend(config(), [
      speaker({
        publication: publication({ consent: 'granted', approved_by: 'alice', approved_on: LONG_AGO }),
        runbook_progress: { 'delivered/forum-summary': true, 'delivered/thank-you': true },
      }),
    ]);
    renderSpeaker(backend);

    expect(await screen.findByRole('button', { name: PUBLISH })).toBeDisabled();
    expect(
      screen.getByText(/Speaker registered on the forum and to their own talk is not ticked\./),
    ).toBeInTheDocument();
    expect(backend.current()[0].publication.outcome).toBe('');
  });

  it('offers no control for recording a silence', async () => {
    // There is a radio for "they agreed" and one for "they refused", and
    // deliberately none for "no answer yet": leaving the field alone is what
    // a volunteer who has not heard back should do.
    const backend = makeBackend(config(), [speaker()]);
    renderSpeaker(backend);

    expect(await screen.findByLabelText(/They agreed/)).toBeInTheDocument();
    expect(screen.getByLabelText(/They refused/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/no answer/i)).toBeNull();
  });

  it('publishes once the speaker has agreed and the board window has run', async () => {
    const backend = makeBackend(config(), [
      speaker({
        publication: publication({ consent: 'pending', approved_by: 'alice', approved_on: LONG_AGO }),
      }),
    ]);
    renderSpeaker(backend);

    fireEvent.click(await screen.findByLabelText(/They agreed/));
    fireEvent.click(screen.getByRole('button', { name: /Record the speaker/ }));
    await waitFor(() => expect(backend.current()[0].publication.consent).toBe('granted'));

    await waitFor(() => expect(screen.getByRole('button', { name: PUBLISH })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: PUBLISH }));

    await waitFor(() => expect(backend.current()[0].status).toBe('archived'));
    expect(backend.current()[0].publication.outcome).toBe('published');
  });

  it('does not publish when the speaker withdraws consent between the read and the write', async () => {
    // The guarantee, under the condition that actually threatens it. The
    // volunteer's screen says the gate is open; while they are looking at it
    // the speaker emails another member and withdraws. The transformation
    // runs against `current`, not against the row this component rendered
    // with, so the withdrawal is what decides -- and the volunteer reads the
    // governance sentence, not a network error.
    const ready = speaker({
      publication: publication({ consent: 'granted', approved_by: 'alice', approved_on: LONG_AGO }),
    });
    const backend = makeBackend(config(), [ready]);
    renderSpeaker(backend);

    await waitFor(() => expect(screen.getByRole('button', { name: PUBLISH })).not.toBeDisabled());

    backend.interlope([
      speaker({ publication: publication({ consent: 'refused', approved_by: 'alice', approved_on: LONG_AGO }) }),
    ]);

    fireEvent.click(screen.getByRole('button', { name: PUBLISH }));

    await waitFor(() => expect(screen.getByText(/refused permission/)).toBeInTheDocument());
    expect(backend.current()[0].status).toBe('delivered');
    expect(backend.current()[0].publication.outcome).not.toBe('published');
  });

  it('flags an archived recording the speaker has since refused', async () => {
    const backend = makeBackend(config(), [
      speaker({
        status: 'archived',
        publication: publication({
          consent: 'refused',
          approved_by: 'alice',
          approved_on: LONG_AGO,
          outcome: 'published',
        }),
      }),
    ]);
    renderSpeaker(backend);

    expect(
      await screen.findByText(/This recording is online and should not be/),
    ).toBeInTheDocument();
  });
});

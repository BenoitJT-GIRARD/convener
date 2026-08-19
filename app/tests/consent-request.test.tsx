/**
 * The screen that asks thirty-one people a question nobody has asked them.
 *
 * The suite is organised around the three things the screen must not do, and
 * the central one is first: there is no control anywhere on it for recording
 * an answer nobody gave. That test is not a description of the current
 * markup -- adding a "no answer yet" button to `Consent.tsx` makes it fail,
 * which is exactly the mutation this task ran.
 *
 * The message is exercised through the real file on disk and the real
 * template mechanism, never through a fixture of what the file is supposed to
 * say. A message whose truth is asserted against a copy of itself is not
 * checked at all.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { Layout } from '../src/components/Layout';
import { Consent } from '../src/screens/Consent';
import { CONTENT_REGISTRY } from '../src/content/registry';
import { substitute } from '../src/content/render';
import {
  CONSENT_ASKABLE_FROM,
  FIELD_WORDING,
  NEVER_PUBLISHED,
  PUBLISHABLE_ALWAYS,
  PUBLISHABLE_ON_CONSENT,
  answeredList,
  awaitingAnswer,
  awaitingAnswerList,
  isAnswer,
} from '../src/state/consent';
import { applyTransition, canTransition } from '../src/state/transitions';
import { parseSpeakers, serializeSpeakers, stripHeader } from '../src/data/yaml';
import { CONSENT_DECISIONS, type Config, type Speaker, type SpeakerStatus } from '../src/data/types';
import { config as configDouble, speaker as double } from './data-doubles';

const MESSAGE_KEY = 'toolkit/emails/consent-request';

const MESSAGE_PATH = resolve(__dirname, '../../docs', CONTENT_REGISTRY[MESSAGE_KEY].file);

/** The template as it actually sits in the repository. */
function messageSource(): string {
  return readFileSync(MESSAGE_PATH, 'utf-8');
}

const ALL_STATUSES: SpeakerStatus[] = [
  'lead',
  'approved',
  'invited',
  'confirmed',
  'scheduled',
  'delivered',
  'archived',
  'parked',
  'decline-board',
  'decline-speaker',
];

function speaker(id: string, overrides: Partial<Speaker> = {}): Speaker {
  return double({
    id,
    name: `Speaker ${id}`,
    status: 'delivered',
    edition_code: `MRG-${id}`,
    date: '2026-01-05',
    title: 'A talk',
    host_1: 'alice',
    ...overrides,
  });
}

beforeEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  localStorage.setItem('convener.token', 'tok');
});

/* ------------------------------------------------------------------ *
 * 1. The list is derived, never authored
 * ------------------------------------------------------------------ */

describe('who still owes an answer', () => {
  it('is computed from the records: a talk given, and no answer on file', () => {
    const rows = [
      speaker('a', { status: 'delivered', publication: pub('') }),
      speaker('b', { status: 'archived', publication: pub('pending') }),
      speaker('c', { status: 'delivered', publication: pub('granted') }),
      speaker('d', { status: 'archived', publication: pub('refused') }),
      speaker('e', { status: 'lead', publication: pub('') }),
      speaker('f', { status: 'scheduled', publication: pub('') }),
    ];
    expect(awaitingAnswerList(rows).map(s => s.id)).toEqual(['a', 'b']);
    // Both answers leave the waiting list, and neither leaves the record.
    expect(answeredList(rows).map(s => s.id)).toEqual(['c', 'd']);
  });

  it('treats every value that is not one of the two answers as silence', () => {
    for (const value of ['', 'pending'] as const) {
      expect(isAnswer(value)).toBe(false);
      expect(awaitingAnswer(speaker('x', { publication: pub(value) }))).toBe(true);
    }
    for (const value of CONSENT_DECISIONS) {
      expect(isAnswer(value)).toBe(true);
      expect(awaitingAnswer(speaker('x', { publication: pub(value) }))).toBe(false);
    }
  });

  it('asks about exactly the records the transition can be applied to', () => {
    // The screen's notion of "there is a recording to ask about" and
    // `transitions.ts`'s notion of it are two statements of one rule. Pinned
    // over every status so the two cannot drift: a status added to one side
    // and not the other fails here.
    for (const status of ALL_STATUSES) {
      const s = speaker('x', { status, publication: pub('') });
      expect((CONSENT_ASKABLE_FROM as readonly string[]).includes(status)).toBe(
        canTransition(s, 'consent-set', 'board'),
      );
    }
  });

  it('shows the waiting speakers on screen, most recent talk first', async () => {
    const backend = makeBackend(configDouble({ board: [] }), [
      speaker('old', { name: 'Older Talk', date: '2025-03-01', publication: pub('') }),
      speaker('new', { name: 'Newer Talk', date: '2026-03-01', publication: pub('pending') }),
      speaker('done', { name: 'Already Agreed', date: '2026-04-01', publication: pub('granted') }),
    ]);
    renderConsent(backend);

    await screen.findByText('Newer Talk');
    const body = document.body.textContent ?? '';
    expect(body.indexOf('Newer Talk')).toBeLessThan(body.indexOf('Older Talk'));
    expect(body).toContain('2 speakers');
    // The one who answered is not on the waiting list, and has not vanished.
    expect(body).toContain('Already Agreed');
    expect(body).toContain('agreed');
  });
});

/* ------------------------------------------------------------------ *
 * 2. No control records a consent nobody gave -- the central test
 * ------------------------------------------------------------------ */

describe('the answers the screen can record', () => {
  it('offers no way to record consent nobody gave', async () => {
    const backend = makeBackend(configDouble({ board: [] }), [
      speaker('a', { publication: pub('') }),
      speaker('b', { publication: pub('pending') }),
    ]);
    renderConsent(backend);
    await screen.findAllByText('Record their answer');

    expect(screen.queryByRole('button', { name: /assume|no answer|pending/i })).toBeNull();
  });

  it('offers no control that answers for more than one speaker at once', async () => {
    const backend = makeBackend(configDouble({ board: [] }), [
      speaker('a', { publication: pub('') }),
      speaker('b', { publication: pub('') }),
    ]);
    renderConsent(backend);
    await screen.findAllByText('Record their answer');

    expect(screen.queryByRole('button', { name: /all|bulk|everyone|remaining/i })).toBeNull();
    // One submit per speaker, and each one names a single record.
    expect(screen.getAllByRole('button', { name: 'Record their answer' })).toHaveLength(2);
  });

  it('writes nothing at all until somebody chooses one of the two answers', async () => {
    const backend = makeBackend(configDouble({ board: [] }), [speaker('a', { publication: pub('') })]);
    renderConsent(backend);

    const submit = await screen.findByRole('button', { name: 'Record their answer' });
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    expect(backend.current()[0].publication.consent).toBe('');
  });

  it('leaves the record untouched when the speaker has not replied', async () => {
    // The whole screen rendered, every control on it read, and nothing
    // pressed: the state of a speaker who has not answered is the state they
    // started in. There is no idle path to a stored decision.
    const backend = makeBackend(configDouble({ board: [] }), [speaker('a', { publication: pub('') })]);
    renderConsent(backend);
    await screen.findByRole('button', { name: 'Record their answer' });
    expect(backend.current()[0].publication).toEqual(pub(''));
  });
});

/* ------------------------------------------------------------------ *
 * 3. A refusal is as easy to record as an agreement
 * ------------------------------------------------------------------ */

describe('recording what the speaker answered', () => {
  it('offers the two answers as one pair of equals', async () => {
    const backend = makeBackend(configDouble({ board: [] }), [speaker('a', { publication: pub('') })]);
    renderConsent(backend);

    const yes = await screen.findByRole('radio', { name: /They agreed/ });
    const no = screen.getByRole('radio', { name: /They would rather we did not/ });
    // Same control, same submit, neither pre-selected: the volunteer says
    // which of the two happened before anything can be written.
    expect(yes).not.toBeChecked();
    expect(no).not.toBeChecked();
    expect(no).toBeEnabled();
    expect(document.body.textContent).toContain('Both answers are outcomes; neither is a failure');
  });

  /** One radio, one button, one write -- stated once and run for each of the
   *  two answers, so a refusal that took an extra step would fail here. */
  async function recordAnswer(name: RegExp): Promise<Speaker[]> {
    const backend = makeBackend(configDouble(), [speaker('a', { publication: pub('') })]);
    renderConsent(backend);
    fireEvent.click(await screen.findByRole('radio', { name }));
    fireEvent.click(screen.getByRole('button', { name: 'Record their answer' }));
    await waitFor(() => expect(backend.current()[0].publication.consent).not.toBe(''));
    return backend.current();
  }

  it('records an agreement in one choice and one press', async () => {
    const after = await recordAnswer(/They agreed/);
    expect(after[0].publication.consent).toBe('granted');
  });

  it('records a refusal in exactly the same one choice and one press', async () => {
    const after = await recordAnswer(/They would rather we did not/);
    expect(after[0].publication.consent).toBe('refused');
  });

  it('takes a published recording out of the feed when a speaker withdraws', () => {
    // The promise the message makes -- "write to us and it comes down" -- is
    // the one the transition keeps. A recording already in the feed does not
    // wait for a board decision to leave it: the refusal un-publishes on the
    // spot, which is what makes the sentence in the template true.
    const published = speaker('a', {
      status: 'archived',
      publication: {
        consent: 'granted',
        approved_by: 'alice',
        approved_on: '2026-01-10',
        objections: [],
        outcome: 'published',
      },
    });
    const after = applyTransition(published, 'consent-set', 'alice', configDouble(), '2026-05-01', {
      consent: 'refused',
    });
    expect(after.publication.consent).toBe('refused');
    expect(after.publication.outcome).toBe('');
  });

  it('hands the write to mutate, which re-reads the row rather than the render', async () => {
    const backend = makeBackend(configDouble({ board: [] }), [
      speaker('a', { publication: pub('') }),
      speaker('b', { publication: pub('') }),
    ]);
    renderConsent(backend);
    await screen.findAllByRole('button', { name: 'Record their answer' });

    // Somebody else edits `b` behind this screen's back, between its read and
    // its write. The answer recorded for `a` must not carry the stale `b`
    // back over the remote.
    backend.interlope([
      backend.current()[0],
      { ...backend.current()[1], notes: 'edited elsewhere' },
    ]);

    fireEvent.click(screen.getAllByRole('radio', { name: /They agreed/ })[0]);
    fireEvent.click(screen.getAllByRole('button', { name: 'Record their answer' })[0]);

    await waitFor(() => expect(backend.current()[0].publication.consent).toBe('granted'));
    expect(backend.current()[1].notes).toBe('edited elsewhere');
  });

  it('shows no control, and says who does, when the reader is not on the board', async () => {
    const backend = makeBackend(configDouble({ board: [] }), [speaker('a', { publication: pub('') })], {
      role: 'organizer',
    });
    renderConsent(backend);

    expect(await screen.findByText(/A board member records what the speaker answers/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Record their answer' })).toBeNull();
    // The message is still there: sending it is not a board job.
    expect(screen.getByRole('button', { name: 'Show the message' })).toBeTruthy();
  });
});

/* ------------------------------------------------------------------ *
 * 4. The message says what is actually published
 * ------------------------------------------------------------------ */

describe('the message asking for permission', () => {
  it('reaches the screen through the fragment mechanism, like every other template', () => {
    expect(CONTENT_REGISTRY[MESSAGE_KEY]).toEqual({
      file: 'toolkit/emails/consent-request.md',
      anchor: null,
    });
  });

  it('names every publishable field, composed rather than typed out', () => {
    const rendered = substitute(messageSource(), { speaker: speaker('a') });
    for (const field of PUBLISHABLE_ON_CONSENT) {
      expect(rendered).toContain(FIELD_WORDING[field]);
    }
    for (const field of PUBLISHABLE_ALWAYS) {
      expect(rendered).toContain(FIELD_WORDING[field]);
    }
    expect(rendered).not.toContain('«missing');
  });

  it('is composed from the classification, so the two cannot drift', () => {
    // The claim under test is that the wording is *derived*. If it were typed
    // into the Markdown, the source file would already contain the phrases;
    // it contains the tokens instead, and the phrases appear only once the
    // classification has been read.
    const source = messageSource();
    expect(source).toContain('{{ consent.published_on_consent }}');
    expect(source).toContain('{{ consent.published_always }}');
    for (const field of PUBLISHABLE_ON_CONSENT) {
      expect(source).not.toContain(FIELD_WORDING[field]);
    }
  });

  it('has a phrase for every publishable field and for no other', () => {
    // The compiler already refuses an unlabelled publishable field (the
    // `Record` key type is the union of the two sets). This states the other
    // half at runtime: nothing that is never published is described here as
    // though it might be.
    const publishable = new Set<string>([...PUBLISHABLE_ALWAYS, ...PUBLISHABLE_ON_CONSENT]);
    expect(new Set(Object.keys(FIELD_WORDING))).toEqual(publishable);
    for (const field of NEVER_PUBLISHED) {
      expect(Object.keys(FIELD_WORDING)).not.toContain(field);
    }
  });

  it('promises only what the code keeps: a refusal costs nothing, and can come later', () => {
    // Line breaks in the Markdown are not part of the sentence.
    const prose = messageSource().replace(/\s+/g, ' ');
    expect(prose).toMatch(/no consequence of any kind/i);
    expect(prose).toMatch(/you do not owe us a reason/i);
    expect(prose).toMatch(/change your mind/i);
    expect(prose).toMatch(/write to us and it comes down/i);
    // `email` is in NEVER_PUBLISHED, so the sentence saying so is true.
    expect(NEVER_PUBLISHED).toContain('email');
    expect(prose).toMatch(/e-mail address is never published/i);
  });

  it('says where, not just what', () => {
    const prose = messageSource().replace(/\s+/g, ' ');
    expect(prose).toContain('forum.example.test');
    expect(prose).toMatch(/YouTube channel/);
  });

  it('renders on the row through the real template, addressed to the real speaker', async () => {
    const backend = makeBackend(configDouble({ board: [] }), [
      speaker('a', { name: 'Ada Lovelace', title: 'On engines', publication: pub('') }),
    ]);
    renderConsent(backend);
    fireEvent.click(await screen.findByRole('button', { name: 'Show the message' }));

    await screen.findByText(/Dear Ada,/);
    const body = document.body.textContent ?? '';
    expect(body).toContain(FIELD_WORDING.youtube_url);
    expect(body).toContain(FIELD_WORDING.bio);
  });
});

/* ------------------------------------------------------------------ *
 * Harness
 * ------------------------------------------------------------------ */

function pub(consent: Speaker['publication']['consent']): Speaker['publication'] {
  return { consent, approved_by: '', approved_on: '', objections: [], outcome: '' };
}

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

/** A stand-in for the Contents API, plus the static handbook path the
 *  template is fetched from. */
function makeBackend(
  cfg: Config,
  initial: Speaker[],
  opts: { role?: 'board' | 'organizer' } = {},
) {
  let server = initial;
  let sha = 'spk-0';
  let counter = 0;
  const template = messageSource();

  const fetchMock = vi.fn((url: string, opts2?: RequestInit) => {
    if (url.includes('handbook/')) {
      return Promise.resolve({ ok: true, text: async () => template });
    }
    if (url.includes('memberships')) {
      return Promise.resolve(
        opts.role === 'organizer'
          ? { ok: false, status: 404, text: async () => 'not a member' }
          : { ok: true, json: async () => ({ state: 'active' }) },
      );
    }
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      if (opts2?.method === 'PUT') {
        const body = JSON.parse(opts2.body as string);
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
    interlope(next: Speaker[]) {
      server = next;
      sha = `spk-other-${++counter}`;
    },
    current: () => server,
  };
}

function renderConsent(backend: { fetchMock: ReturnType<typeof vi.fn> }) {
  vi.stubGlobal('fetch', backend.fetchMock);
  return render(
    <MemoryRouter initialEntries={['/consent']}>
      <AuthProvider>
        <DataProvider>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/consent" element={<Consent />} />
            </Route>
          </Routes>
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}


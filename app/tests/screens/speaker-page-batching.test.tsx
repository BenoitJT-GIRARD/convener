/**
 * How many commits a volunteer's work actually makes.
 *
 * Every write to `instance/data/speakers.yml` is a commit, and every commit is
 * a push that wakes the repository's workflows. On the instance this product
 * was derived for, one operator's runbook session made 53 commits in 47
 * minutes and spent 1175 billed Actions minutes — more than half of a GitHub
 * Free month. Narrowing what a push wakes fixed most of it
 * (`docs/operating/what-the-automation-costs.md`); the floor that remained was
 * the number of commits.
 *
 * The worst of it was not the ticking. `Checklist`'s fields fire `onChange` on
 * every keystroke, and each one wrote — **one commit per character typed**. It
 * had gone unnoticed because the values a volunteer reaches for first are a
 * GitHub login or a URL, and those get pasted; a paste is one change event.
 * Measured before the fix, three change events made three commits.
 *
 * What must not be batched is held here too, because that is the half a
 * measurement cannot argue for: a transition changes a status, and a status
 * change publishes an edition, mints a key, opens registration or sends
 * somebody a message.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../../src/auth/AuthContext';
import { DataProvider } from '../../src/data/DataContext';
import { SpeakerPage } from '../../src/screens/SpeakerPage';
import { parseSpeakers, serializeSpeakers } from '../../src/data/yaml';
import { configYaml, speaker as double } from '../helpers/data-doubles';
import type { Speaker } from '../../src/data/types';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/** The provider's own source, for the one claim below that is about how the
 *  timer is managed rather than about what a volunteer sees. */
const DataContextSource = readFileSync(
  resolve(__dirname, '../../src/data/DataContext.tsx'),
  'utf-8',
);

function encodeUtf8(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function decodeUtf8(b64: string): string {
  const bin = atob(b64);
  return new TextDecoder('utf-8').decode(Uint8Array.from(bin, c => c.charCodeAt(0)));
}

/** The Contents API, enough of it to count commits and read their subjects. */
function backend(initial: Speaker[]) {
  let server = initial;
  let sha = 'sha-0';
  let counter = 0;
  const messages: string[] = [];
  const cfg = configYaml();
  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      if (opts?.method === 'PUT') {
        const body = JSON.parse(opts.body as string);
        messages.push(body.message as string);
        server = parseSpeakers(decodeUtf8(body.content));
        sha = `sha-${++counter}`;
        return Promise.resolve({ ok: true, json: async () => ({ content: { sha } }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ content: encodeUtf8(serializeSpeakers(server)), sha }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ content: encodeUtf8(cfg), sha: 'cfgsha' }),
    });
  });
  return { fetchMock, messages, current: () => server };
}

function show(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/speakers/${id}`]}>
      <AuthProvider>
        <DataProvider>
          <Routes>
            <Route path="/speakers/:id" element={<SpeakerPage />} />
          </Routes>
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const delivered = (id = 'spk-001') =>
  double({
    id,
    name: 'A Speaker',
    status: 'delivered',
    date: '2026-05-01',
    time: '12:30',
    edition_code: id === 'spk-001' ? 'MRG-1' : 'MRG-2',
    host_1: 'alice',
  });

async function tickTheForumSummary() {
  const label = await screen.findByText(/Forum summary posted/);
  const box = label.closest('div.border')!.querySelector('input[type="checkbox"]');
  if (!(box instanceof HTMLInputElement)) throw new Error('no checkbox found');
  fireEvent.click(box);
  return box;
}

describe('how many commits the work makes', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('writes one commit for a field typed into, not one per keystroke', async () => {
    // The defect, and the reason this whole change is not only about
    // minutes. Measured before the fix: three change events, three commits.
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    show('spk-001');

    const input = await screen.findByLabelText(/Registrations/i);
    for (const value of ['1', '12', '128']) {
      fireEvent.change(input, { target: { value } });
    }

    expect(b.messages).toHaveLength(0);
    fireEvent.click(await screen.findByRole('button', { name: 'Save now' }));
    await waitFor(() => expect(b.messages).toHaveLength(1));

    expect(b.messages[0]).toBe('data: spk-001 3 checklist lines');
    expect(b.current()[0].metrics.registrations).toBe(128);
  });

  it('shows the work as done before it is written', async () => {
    // Held work a volunteer cannot see is work they do not know they can
    // lose — and a box that un-ticks itself until the next write is worse
    // than a commit per tick. The screen draws from the same function the
    // write transforms with.
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    show('spk-001');

    const box = await tickTheForumSummary();

    await waitFor(() => expect(box.checked).toBe(true));
    expect(b.messages).toHaveLength(0);
    expect(await screen.findByText(/1 change not saved yet/)).toBeTruthy();
  });

  it('says how many are waiting', async () => {
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    show('spk-001');

    await tickTheForumSummary();
    fireEvent.change(await screen.findByLabelText(/Registrations/i), {
      target: { value: '128' },
    });

    expect(await screen.findByText(/2 changes not saved yet/)).toBeTruthy();
  });

  it('writes what is held before any other write, in a commit of its own', async () => {
    // The rule that protects everything the batching must not reorder. Every
    // other write goes through `mutateSpeakers`, and that is where the queue
    // is emptied — once, at the chokepoint, rather than at each call site
    // that would have to remember.
    //
    // Its own commit, not folded in: the other write's subject may be a line
    // of the decision register, and bookkeeping merged into it would make
    // that line describe two different things.
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    show('spk-001');

    await tickTheForumSummary();
    expect(b.messages).toHaveLength(0);

    const label = await screen.findByText(/Forum summary posted/);
    const owner = label.closest('div.border')!.parentElement!.querySelector('select');
    if (!(owner instanceof HTMLSelectElement)) throw new Error('no owner select found');
    fireEvent.change(owner, { target: { value: 'alice' } });

    await waitFor(() => expect(b.messages).toHaveLength(2));
    expect(b.messages[0]).toBe('data: spk-001 runbook delivered/forum-summary=true');
    expect(b.messages[1]).toBe('data: spk-001 owner for delivered/forum-summary');
  });

  it('writes what is held when the volunteer leaves the record', async () => {
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    const { unmount } = show('spk-001');

    await tickTheForumSummary();
    expect(b.messages).toHaveLength(0);

    unmount();

    await waitFor(() => expect(b.messages).toHaveLength(1));
    expect(b.messages[0]).toBe('data: spk-001 runbook delivered/forum-summary=true');
  });

  it('writes what is held on its own, once the volunteer has stopped', async () => {
    // The backstop: a volunteer who ticks a box and walks away has their
    // work written without touching anything. It is the last of the four
    // ways a queue is emptied and the only one nobody performs, which is why
    // it can afford to be as long as it is.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const b = backend([delivered()]);
    vi.stubGlobal('fetch', b.fetchMock);
    show('spk-001');

    await tickTheForumSummary();
    expect(b.messages).toHaveLength(0);

    // Still held a second short of the window. Without this the reading
    // above would pass for any timer at all, including one that wrote
    // immediately -- and the length of this wait is the whole thing being
    // decided, because it is how much work a dead machine would take.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(119_000);
    });
    expect(b.messages).toHaveLength(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    await waitFor(() => expect(b.messages).toHaveLength(1));
    expect(b.messages[0]).toBe('data: spk-001 runbook delivered/forum-summary=true');
  });

  it('starts the wait again at each edit, so a run of ticks is one commit', () => {
    // What a window means: it is time since the *last* edit, not since the
    // first. A volunteer working down a phase never has a batch cut in half
    // because they happened to start two minutes ago.
    //
    // Read off the provider's own constant rather than performed, because
    // performing it would mean advancing the clock between two ticks and
    // asserting a negative about a timer that has been replaced.
    expect(DataContextSource).toContain('if (timerRef.current !== null) clearTimeout(timerRef.current);');
  });
});

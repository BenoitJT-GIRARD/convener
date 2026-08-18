import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../src/auth/AuthContext';
import { DataProvider } from '../src/data/DataContext';
import { ActionButtons } from '../src/components/ActionButtons';
import { parseSpeakers, serializeSpeakers } from '../src/data/yaml';
import type { Ballot, BallotValue, Speaker } from '../src/data/types';

function ballot(voter: string, value: BallotValue = 'yes'): Ballot {
  return { voter, value, comment: '', coi_reason: '', date: '2026-05-20' };
}

function lead(ballots: Ballot[] = []): Speaker {
  return {
    id: 'spk-001',
    name: 'Lead One',
    gender: 'undisclosed',
    career_stage: 'undisclosed',
    email: '',
    affiliation: '',
    country: '',
    title: '',
    abstract: '',
    conflicts_of_interest: '',
    source: 'organizer',
    proposed_by: '',
    assigned_to: '',
    links: [],
    host_1: '',
    host_2: '',
    status: 'lead',
    selection: { ballots, opened_on: '2026-05-01', decided_on: '' },
    publication: {
      consent: 'pending',
      approved_by: '',
      approved_on: '',
      objections: [],
      outcome: '',
    },
    edition_code: '',
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
    notes: '',
  };
}

/** Four active members, so `thresholdFor(4)` is 3 yes votes. */
const BOARD_YAML = `season: 2026
board:
  - login: alice
    joined_on: '2024-01-01'
    status: active
    unavailable_until: ''
  - login: bob
    joined_on: '2024-01-01'
    status: active
    unavailable_until: ''
  - login: carol
    joined_on: '2024-01-01'
    status: active
    unavailable_until: ''
  - login: dan
    joined_on: '2024-01-01'
    status: active
    unavailable_until: ''
`;

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

/** A stand-in for the GitHub Contents API that enforces the sha precondition,
 *  so a write goes through the same path the real one does. */
function makeBackend(initial: Speaker[]) {
  let server = initial;
  let sha = 'sha-0';
  let counter = 0;

  const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
    if (url.includes('/user')) {
      return Promise.resolve({ ok: true, json: async () => ({ login: 'alice' }) });
    }
    if (url.includes('speakers.yml')) {
      if (opts?.method === 'PUT') {
        const body = JSON.parse(opts.body as string);
        if (body.sha !== sha) {
          return Promise.resolve({ ok: false, status: 409, text: async () => 'stale sha' });
        }
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
      json: async () => ({ content: encodeUtf8(BOARD_YAML), sha: 'cfgsha' }),
    });
  });

  return { fetchMock, current: () => server };
}

function renderFor(speaker: Speaker, backend: { fetchMock: unknown }) {
  vi.stubGlobal('fetch', backend.fetchMock);
  render(
    <MemoryRouter>
      <AuthProvider>
        <DataProvider>
          <ActionButtons speaker={speaker} role="board" />
        </DataProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

/** The board arrives with config.yml, and every control stays disabled until
 *  it does -- so a test that clicks before then would click a no-op. */
async function waitForBoard() {
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Submit ballot' })).not.toBeDisabled(),
  );
}

describe('ActionButtons ballot form', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    localStorage.setItem('convener.token', 'tok');
  });

  it('offers all three ballot values, not just yes', async () => {
    // `abstain` and `recused` are the two values that move the denominator.
    // A UI that only offers "yes" makes the recusal rule unusable.
    const speaker = lead();
    renderFor(speaker, makeBackend([speaker]));

    expect(await screen.findByRole('radio', { name: /Yes/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Abstain/ })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Recuse myself/ })).toBeInTheDocument();
  });

  it('asks for the recusal reason up front instead of rejecting the save', async () => {
    const speaker = lead();
    const backend = makeBackend([speaker]);
    renderFor(speaker, backend);

    await waitForBoard();
    fireEvent.click(screen.getByRole('radio', { name: /Recuse myself/ }));

    expect(screen.getByRole('button', { name: 'Submit ballot' })).toBeDisabled();
    expect(screen.getByText(/Required: a recusal changes/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Reason for the conflict of interest/), {
      target: { value: 'former co-author' },
    });

    const submit = screen.getByRole('button', { name: 'Submit ballot' });
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);

    await waitFor(() => expect(backend.current()[0].selection.ballots).toHaveLength(1));
    const written = backend.current()[0].selection.ballots[0];
    expect(written.value).toBe('recused');
    expect(written.coi_reason).toBe('former co-author');
  });

  it('records an abstention as such, and it does not decide the vote', async () => {
    const speaker = lead([ballot('bob'), ballot('carol')]);
    const backend = makeBackend([speaker]);
    renderFor(speaker, backend);

    await waitForBoard();
    fireEvent.click(screen.getByRole('radio', { name: /Abstain/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Submit ballot' }));

    await waitFor(() => expect(backend.current()[0].selection.ballots).toHaveLength(3));
    expect(backend.current()[0].selection.ballots[2].value).toBe('abstain');
    // Two yes out of four eligible: the bar is three, and an abstention does
    // not lower it.
    expect(backend.current()[0].status).toBe('lead');
  });

  it('decides the vote inside the write, from the board and the ballots at write time', async () => {
    const speaker = lead([ballot('bob'), ballot('carol')]);
    const backend = makeBackend([speaker]);
    renderFor(speaker, backend);

    await waitForBoard();
    fireEvent.click(screen.getByRole('button', { name: 'Submit ballot' }));

    await waitFor(() => expect(backend.current()[0].status).toBe('approved'));
    expect(backend.current()[0].selection.ballots).toHaveLength(3);
    expect(backend.current()[0].selection.decided_on).not.toBe('');
  });
});
